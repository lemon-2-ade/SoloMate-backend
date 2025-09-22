from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import statistics
import logging
import asyncio
from geopy.distance import geodesic

from app.core.database import get_db
from app.core.config import settings
from app.api.routes.auth import get_current_user
from app.services.news_scraping_agent import news_agent
from app.services.news_analysis_ai import news_analysis_ai
from app.models.schemas import (
    SafetyReportCreate,
    SafetyReportResponse,
    SafetyReportType,
    MessageResponse,
    # NewsScrapingJobCreate,
    # NewsScrapingJobResponse,
    # NewsSafetyAnalysis
)

router = APIRouter()

class SafetyIndexCalculator:
    """Calculate live safety index for cities and areas"""
    
    @staticmethod
    def calculate_time_factor(hour: int) -> float:
        """Calculate time-based safety factor (0-1)"""
        # Lower safety during late night hours (22:00 - 06:00)
        if 22 <= hour or hour <= 6:
            return 0.6
        # Peak safety during day hours (08:00 - 18:00)
        elif 8 <= hour <= 18:
            return 1.0
        # Medium safety during evening (18:00 - 22:00) and early morning (06:00 - 08:00)
        else:
            return 0.8
    
    @staticmethod
    def calculate_density_factor(active_users_count: int) -> float:
        """Calculate density-based safety factor based on active users"""
        if active_users_count >= 20:
            return 1.0  # High density = safer
        elif active_users_count >= 10:
            return 0.8
        elif active_users_count >= 5:
            return 0.6
        else:
            return 0.4  # Low density = less safe
    
    @staticmethod
    def calculate_reports_factor(reports: List[Dict]) -> float:
        """Calculate safety factor based on recent safety reports"""
        if not reports:
            return 0.5  # Neutral when no data
        
        positive_types = [
            SafetyReportType.WELL_LIT,
            SafetyReportType.POLICE_PRESENCE,
            SafetyReportType.CROWDED_AREA,
            SafetyReportType.EMERGENCY_SERVICES,
            SafetyReportType.SAFE_TRANSPORT
        ]
        
        negative_types = [
            SafetyReportType.UNSAFE_AREA,
            SafetyReportType.UNSAFE_TRANSPORT,
            SafetyReportType.TOURIST_SCAM,
            SafetyReportType.PICKPOCKET_RISK
        ]
        
        weighted_score = 0
        total_weight = 0
        
        for report in reports:
            # More recent reports have higher weight
            days_old = (datetime.utcnow() - report['reported_at']).days
            weight = max(0.1, 1 - (days_old / 30))  # Decay over 30 days
            
            if report['type'] in positive_types:
                score = (report['severity'] / 10.0)  # Positive impact
            elif report['type'] in negative_types:
                score = 1 - (report['severity'] / 10.0)  # Negative impact
            else:
                score = 0.5  # Neutral
            
            weighted_score += score * weight
            total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.5
    
    @staticmethod
    async def calculate_news_factor(city_id: str, latitude: float, longitude: float, db) -> float:
        """Calculate news-based safety factor"""
        try:
            # Get recent news articles for the city (last 7 days)
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            news_articles = await db.newsarticle.find_many(
                where={
                    "OR": [
                        {"cityId": city_id},
                        {
                            "AND": [
                                {"latitude": {"not": None}},
                                {"longitude": {"not": None}},
                                {"locationRadius": {"not": None}}
                            ]
                        }
                    ],
                    "processedAt": {"gte": seven_days_ago},
                    "isRelevant": True,
                    "isProcessed": True
                }
            )
            
            if not news_articles:
                return 1.0  # Neutral if no news data
            
            # Filter articles by geographic proximity if lat/lng available
            relevant_articles = []
            target_location = (latitude, longitude)
            
            for article in news_articles:
                if article.latitude and article.longitude:
                    article_location = (article.latitude, article.longitude)
                    distance_km = geodesic(target_location, article_location).kilometers
                    
                    # Include if within location radius or 50km default
                    max_distance = article.locationRadius or 50.0
                    if distance_km <= max_distance:
                        relevant_articles.append(article)
                elif article.cityId == city_id:
                    # Include if directly associated with city
                    relevant_articles.append(article)
            
            if not relevant_articles:
                return 1.0  # Neutral if no geographically relevant articles
            
            # Calculate weighted news impact
            total_impact = 0.0
            total_weight = 0.0
            
            for article in relevant_articles:
                # Get news safety impacts
                impacts = await db.newssafetyimpact.find_many(
                    where={
                        "newsArticleId": article.id,
                        "isActive": True
                    }
                )
                
                if impacts:
                    # Use calculated impact factors
                    for impact in impacts:
                        weight = impact.weightFactor * impact.decayFactor
                        total_impact += impact.impactFactor * weight
                        total_weight += weight
                else:
                    # Fallback: use article-level analysis
                    # Convert threat level (1-10) to safety factor
                    threat_level = article.threatLevel
                    confidence = article.confidence
                    
                    if threat_level <= 3:
                        safety_factor = 1.0 + (3 - threat_level) * 0.1  # 1.0 to 1.2
                    elif threat_level <= 6:
                        safety_factor = 1.0  # Neutral
                    else:
                        safety_factor = 1.0 - (threat_level - 6) * 0.1  # 1.0 to 0.6
                    
                    # Adjust for sentiment
                    sentiment_adjustment = article.sentimentPolarity * 0.05
                    safety_factor += sentiment_adjustment
                    
                    # Weight by confidence and recency
                    days_old = (datetime.utcnow() - article.processedAt).days if article.processedAt else 7
                    recency_weight = max(0.1, 1.0 - (days_old / 7.0))  # 7-day decay
                    weight = confidence * recency_weight
                    
                    total_impact += safety_factor * weight
                    total_weight += weight
            
            # Calculate final news factor
            if total_weight > 0:
                news_factor = total_impact / total_weight
                # Clamp to reasonable range [0.3, 1.5]
                return max(0.3, min(1.5, news_factor))
            else:
                return 1.0  # Neutral
                
        except Exception as e:
            logging.warning(f"News factor calculation failed: {e}")
            return 1.0  # Neutral on error
    
    @classmethod
    async def calculate_city_safety_index(cls, city_id: str, db) -> float:
        """Calculate comprehensive safety index for a city"""
        
        # Get recent safety reports (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        reports = await db.safetyreport.find_many(
            where={
                "cityId": city_id,
                "reportedAt": {"gte": thirty_days_ago},
                "isVerified": True
            }
        )
        
        # Get active users in the city (users with recent activity)
        recent_activity = datetime.utcnow() - timedelta(hours=24)
        active_users = await db.user.count(
            where={
                "lastActiveAt": {"gte": recent_activity},
                "questProgresses": {
                    "some": {
                        "quest": {"cityId": city_id}
                    }
                }
            }
        )
        
        # Calculate factors
        current_hour = datetime.utcnow().hour
        time_factor = cls.calculate_time_factor(current_hour)
        density_factor = cls.calculate_density_factor(active_users)
        
        # Convert reports to dict format for compatibility
        reports_data = [
            {
                "type": report.type,
                "severity": report.severity,
                "reported_at": report.reportedAt
            }
            for report in reports
        ]
        reports_factor = cls.calculate_reports_factor(reports_data)
        
        # Get city coordinates for news analysis
        city = await db.city.find_unique(where={"id": city_id})
        if city:
            news_factor = await cls.calculate_news_factor(
                city_id, city.latitude, city.longitude, db
            )
        else:
            news_factor = 1.0  # Neutral if city not found
        
        # Enhanced weighted average including news data
        # Adjust weights to include news factor (reduce other weights proportionally)
        reports_weight = settings.SAFETY_INDEX_WEIGHT_REPORTS * 0.8
        time_weight = settings.SAFETY_INDEX_WEIGHT_TIME * 0.8  
        density_weight = settings.SAFETY_INDEX_WEIGHT_DENSITY * 0.8
        news_weight = 0.2  # 20% weight for news data
        
        safety_index = (
            reports_factor * reports_weight +
            time_factor * time_weight +
            density_factor * density_weight
        ) * news_factor  # News factor as multiplier
        
        # Apply news weight if significantly different from neutral
        if abs(news_factor - 1.0) > 0.1:
            news_contribution = (news_factor - 1.0) * news_weight
            safety_index += news_contribution
        
        # Ensure safety_index stays within bounds [0, 1]
        safety_index = max(0.0, min(1.0, safety_index))
        
        # Scale to 0-10
        return round(safety_index * 10, 2)
    
    @classmethod
    async def calculate_area_safety_index(
        cls, latitude: float, longitude: float, radius_km: float, db
    ) -> Dict[str, Any]:
        """Calculate safety index for a specific area"""
        
        # Get recent safety reports in the area
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        all_reports = await db.safetyreport.find_many(
            where={
                "reportedAt": {"gte": thirty_days_ago},
                "isVerified": True
            }
        )
        
        # Filter reports by distance
        area_reports = []
        center_location = (latitude, longitude)
        radius_meters = radius_km * 1000
        
        for report in all_reports:
            report_location = (report.latitude, report.longitude)
            distance = geodesic(center_location, report_location).meters
            
            if distance <= radius_meters:
                area_reports.append({
                    "type": report.type,
                    "severity": report.severity,
                    "reported_at": report.reportedAt,
                    "distance": distance
                })
        
        # Get recent location proofs in the area (indicates activity)
        recent_proofs = await db.locationproof.find_many(
            where={
                "timestamp": {"gte": datetime.utcnow() - timedelta(hours=24)},
                "isVerified": True
            }
        )
        
        # Filter proofs by distance
        area_activity = 0
        for proof in recent_proofs:
            proof_location = (proof.latitude, proof.longitude)
            distance = geodesic(center_location, proof_location).meters
            
            if distance <= radius_meters:
                area_activity += 1
        
        # Calculate factors
        current_hour = datetime.utcnow().hour
        time_factor = cls.calculate_time_factor(current_hour)
        density_factor = cls.calculate_density_factor(area_activity)
        reports_factor = cls.calculate_reports_factor(area_reports)
        
        # Calculate news factor for the area
        # Find the closest city for news context
        closest_city = await db.city.find_first(
            order={"latitude": "asc"}  # This is simplified; ideally calculate actual distance
        )
        
        if closest_city:
            news_factor = await cls.calculate_news_factor(
                closest_city.id, latitude, longitude, db
            )
        else:
            news_factor = 1.0
        
        # Enhanced weighted average including news data
        reports_weight = settings.SAFETY_INDEX_WEIGHT_REPORTS * 0.8
        time_weight = settings.SAFETY_INDEX_WEIGHT_TIME * 0.8
        density_weight = settings.SAFETY_INDEX_WEIGHT_DENSITY * 0.8
        
        safety_index = (
            reports_factor * reports_weight +
            time_factor * time_weight +
            density_factor * density_weight
        ) * news_factor
        
        # Apply news adjustment if significant
        if abs(news_factor - 1.0) > 0.1:
            news_contribution = (news_factor - 1.0) * 0.2
            safety_index += news_contribution
        
        # Clamp to valid range
        safety_index = max(0.0, min(1.0, safety_index))
        
        return {
            "safety_index": round(safety_index * 10, 2),
            "factors": {
                "time_factor": round(time_factor, 2),
                "density_factor": round(density_factor, 2),
                "reports_factor": round(reports_factor, 2),
                "news_factor": round(news_factor, 3)
            },
            "data": {
                "total_reports": len(area_reports),
                "recent_activity": area_activity,
                "current_hour": current_hour,
                "analysis_radius_km": radius_km,
                "news_articles_considered": "integrated"
            }
        }

@router.post("/report", response_model=SafetyReportResponse)
async def create_safety_report(
    report_data: SafetyReportCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new safety report"""
    
    # Verify city exists
    city = await db.city.find_unique(where={"id": report_data.city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Create safety report
    report = await db.safetyreport.create(
        data={
            "userId": current_user.id,
            "cityId": report_data.city_id,
            "latitude": report_data.latitude,
            "longitude": report_data.longitude,
            "type": report_data.type,
            "severity": report_data.severity,
            "description": report_data.description
        }
    )
    
    # Award tokens for contributing safety data
    await db.user.update(
        where={"id": current_user.id},
        data={"tokens": {"increment": 5}}  # 5 tokens for safety report
    )
    
    # Recalculate city safety index
    new_safety_index = await SafetyIndexCalculator.calculate_city_safety_index(
        report_data.city_id, db
    )
    
    # Update city safety index
    await db.city.update(
        where={"id": report_data.city_id},
        data={"safetyIndex": new_safety_index}
    )
    
    return SafetyReportResponse(
        id=report.id,
        city_id=report.cityId,
        latitude=report.latitude,
        longitude=report.longitude,
        type=report.type,
        severity=report.severity,
        description=report.description,
        is_verified=report.isVerified,
        reported_at=report.reportedAt
    )

@router.get("/reports", response_model=List[SafetyReportResponse])
async def get_safety_reports(
    city_id: Optional[str] = Query(None, description="Filter by city"),
    latitude: Optional[float] = Query(None, description="Center latitude for area search"),
    longitude: Optional[float] = Query(None, description="Center longitude for area search"),
    radius_km: Optional[float] = Query(None, description="Search radius in kilometers"),
    report_type: Optional[SafetyReportType] = Query(None, description="Filter by report type"),
    days: int = Query(7, description="Number of days to look back"),
    verified_only: bool = Query(True, description="Only show verified reports"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db = Depends(get_db)
):
    """Get safety reports with filtering"""
    
    # Build where clause
    since_date = datetime.utcnow() - timedelta(days=days)
    where_clause = {
        "reportedAt": {"gte": since_date},
        "isActive": True
    }
    
    if city_id:
        where_clause["cityId"] = city_id
    
    if report_type:
        where_clause["type"] = report_type
    
    if verified_only:
        where_clause["isVerified"] = True
    
    reports = await db.safetyreport.find_many(
        where=where_clause,
        skip=offset,
        take=limit,
        order={"reportedAt": "desc"}
    )
    
    # Filter by distance if location provided
    if latitude is not None and longitude is not None and radius_km is not None:
        center_location = (latitude, longitude)
        radius_meters = radius_km * 1000
        
        filtered_reports = []
        for report in reports:
            report_location = (report.latitude, report.longitude)
            distance = geodesic(center_location, report_location).meters
            
            if distance <= radius_meters:
                filtered_reports.append(report)
        
        reports = filtered_reports
    
    return [
        SafetyReportResponse(
            id=report.id,
            city_id=report.cityId,
            latitude=report.latitude,
            longitude=report.longitude,
            type=report.type,
            severity=report.severity,
            description=report.description,
            is_verified=report.isVerified,
            reported_at=report.reportedAt
        )
        for report in reports
    ]

@router.get("/index/city/{city_id}")
async def get_city_safety_index(city_id: str, db = Depends(get_db)):
    """Get current safety index for a city"""
    
    city = await db.city.find_unique(where={"id": city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Calculate fresh safety index
    safety_index = await SafetyIndexCalculator.calculate_city_safety_index(city_id, db)
    
    # Update city safety index
    await db.city.update(
        where={"id": city_id},
        data={"safetyIndex": safety_index}
    )
    
    # Get recent trend (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_reports = await db.safetyreport.find_many(
        where={
            "cityId": city_id,
            "reportedAt": {"gte": seven_days_ago},
            "isVerified": True
        }
    )
    
    return {
        "city": {
            "id": city.id,
            "name": city.name,
            "country": city.country
        },
        "safety_index": safety_index,
        "safety_level": get_safety_level(safety_index),
        "last_updated": datetime.utcnow().isoformat(),
        "trend": {
            "recent_reports": len(recent_reports),
            "report_types": {
                report.type: len([r for r in recent_reports if r.type == report.type])
                for report in recent_reports
            } if recent_reports else {}
        }
    }

@router.get("/index/area")
async def get_area_safety_index(
    latitude: float = Query(..., description="Center latitude"),
    longitude: float = Query(..., description="Center longitude"),
    radius_km: float = Query(1.0, description="Analysis radius in kilometers"),
    db = Depends(get_db)
):
    """Get safety index for a specific area"""
    
    result = await SafetyIndexCalculator.calculate_area_safety_index(
        latitude, longitude, radius_km, db
    )
    
    result["safety_level"] = get_safety_level(result["safety_index"])
    result["location"] = {
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km
    }
    result["last_updated"] = datetime.utcnow().isoformat()
    
    return result

@router.get("/heatmap/{city_id}")
async def get_safety_heatmap(
    city_id: str,
    grid_size: float = Query(0.01, description="Grid cell size in degrees"),
    days: int = Query(30, description="Days to analyze"),
    db = Depends(get_db)
):
    """Get safety heatmap data for a city"""
    
    city = await db.city.find_unique(where={"id": city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Get recent reports in the city
    since_date = datetime.utcnow() - timedelta(days=days)
    reports = await db.safetyreport.find_many(
        where={
            "cityId": city_id,
            "reportedAt": {"gte": since_date},
            "isVerified": True
        }
    )
    
    # Create grid and calculate safety scores
    grid_data = {}
    
    for report in reports:
        # Snap to grid
        grid_lat = round(report.latitude / grid_size) * grid_size
        grid_lon = round(report.longitude / grid_size) * grid_size
        grid_key = f"{grid_lat},{grid_lon}"
        
        if grid_key not in grid_data:
            grid_data[grid_key] = {
                "latitude": grid_lat,
                "longitude": grid_lon,
                "reports": [],
                "safety_score": 0
            }
        
        grid_data[grid_key]["reports"].append({
            "type": report.type,
            "severity": report.severity,
            "reported_at": report.reportedAt
        })
    
    # Calculate safety score for each grid cell
    for grid_key, cell_data in grid_data.items():
        cell_data["safety_score"] = SafetyIndexCalculator.calculate_reports_factor(
            cell_data["reports"]
        ) * 10
        cell_data["report_count"] = len(cell_data["reports"])
        del cell_data["reports"]  # Remove detailed reports from response
    
    return {
        "city": {
            "id": city.id,
            "name": city.name,
            "center": {
                "latitude": city.latitude,
                "longitude": city.longitude
            }
        },
        "heatmap_data": list(grid_data.values()),
        "grid_size": grid_size,
        "analysis_period_days": days,
        "total_cells": len(grid_data),
        "generated_at": datetime.utcnow().isoformat()
    }

@router.post("/verify/{report_id}", response_model=MessageResponse)
async def verify_safety_report(
    report_id: str,
    verification_data: Dict[str, Any],
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Verify a safety report (moderator only)"""
    
    # TODO: Add moderator role check
    
    report = await db.safetyreport.find_unique(where={"id": report_id})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Safety report not found"
        )
    
    # Update report verification status
    await db.safetyreport.update(
        where={"id": report_id},
        data={
            "isVerified": verification_data.get("verified", True),
            "verifiedAt": datetime.utcnow() if verification_data.get("verified", True) else None
        }
    )
    
    # Recalculate city safety index
    new_safety_index = await SafetyIndexCalculator.calculate_city_safety_index(
        report.cityId, db
    )
    
    await db.city.update(
        where={"id": report.cityId},
        data={"safetyIndex": new_safety_index}
    )
    
    return MessageResponse(message="Safety report verification updated")

@router.post("/news/scrape")
async def scrape_location_news(
    latitude: float = Query(..., description="Location latitude"),
    longitude: float = Query(..., description="Location longitude"),
    city_name: Optional[str] = Query(None, description="City name for context"),
    country: Optional[str] = Query(None, description="Country name for context"),
    radius_km: float = Query(50.0, description="Search radius in kilometers"),
    days_back: int = Query(7, description="Days to search back", ge=1, le=30),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Scrape and analyze news articles for a specific location"""
    
    try:
        # Import the news scraping agent
        from app.services.news_scraping_agent import NewsScrapingAgent
        
        # Default city/country if not provided
        if not city_name or not country:
            # Try to find nearest city in database
            cities = await db.city.find_many(
                where={"isActive": True},
                take=10
            )
            
            if cities:
                # Find closest city by distance
                min_distance = float('inf')
                closest_city = None
                
                for city in cities:
                    distance = geodesic(
                        (latitude, longitude), 
                        (city.latitude, city.longitude)
                    ).kilometers
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_city = city
                
                if closest_city and min_distance <= 100:  # Within 100km
                    city_name = city_name or closest_city.name
                    country = country or closest_city.country
            
            # Fallback defaults
            city_name = city_name or "Local Area"
            country = country or "Global"
        
        # Initialize and use news scraping agent
        async with NewsScrapingAgent() as news_agent:
            articles = await news_agent.scrape_location_news(
                latitude=latitude,
                longitude=longitude,
                city_name=city_name,
                country=country,
                radius_km=radius_km,
                days_back=days_back
            )
        
        # Process articles for safety analysis
        safety_relevant = []
        total_articles = len(articles)
        
        for article in articles:
            # Basic safety relevance check
            safety_score = article.get('safety_score', 0.0)
            if safety_score > 0.3:  # Only include relevant articles
                safety_relevant.append({
                    "title": article.get('title', ''),
                    "summary": article.get('summary', ''),
                    "url": article.get('url', ''),
                    "source": article.get('source', ''),
                    "published": article.get('published'),
                    "safety_score": safety_score,
                    "threat_level": article.get('threat_level', 5),
                    "concern_type": article.get('concern_type', 'UNKNOWN'),
                    "sentiment": article.get('sentiment', {}),
                    "location_relevance": article.get('location_relevance', 0.0)
                })
        
        # Calculate overall safety assessment
        if safety_relevant:
            avg_threat_level = sum(a['threat_level'] for a in safety_relevant) / len(safety_relevant)
            avg_safety_score = sum(a['safety_score'] for a in safety_relevant) / len(safety_relevant)
            
            # Determine overall safety impact
            if avg_threat_level >= 7:
                safety_assessment = "High Risk - Multiple serious incidents reported"
            elif avg_threat_level >= 5:
                safety_assessment = "Moderate Risk - Some safety concerns identified"
            elif avg_threat_level >= 3:
                safety_assessment = "Low Risk - Minor safety incidents reported"
            else:
                safety_assessment = "Generally Safe - Positive safety indicators"
        else:
            avg_threat_level = 5.0
            avg_safety_score = 0.0
            safety_assessment = "No significant safety news found"
        
        return {
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "city_name": city_name,
                "country": country,
                "radius_km": radius_km
            },
            "search_parameters": {
                "days_back": days_back,
                "total_articles_found": total_articles,
                "safety_relevant_articles": len(safety_relevant)
            },
            "safety_analysis": {
                "overall_assessment": safety_assessment,
                "average_threat_level": round(avg_threat_level, 2),
                "average_safety_score": round(avg_safety_score, 3) + 0.35,
                "safety_index_impact": round(1.0 - (avg_threat_level - 5) * 0.1, 2)
            },
            "articles": safety_relevant[:10],  # Return top 10 most relevant
            "scraped_at": datetime.utcnow().isoformat(),
            "requested_by": current_user.username
        }
        
    except Exception as e:
        logging.error(f"News scraping failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News scraping failed: {str(e)}"
        )

def get_safety_level(safety_index: float) -> str:
    """Convert numeric safety index to descriptive level"""
    if safety_index >= 8.0:
        return "Very Safe"
    elif safety_index >= 6.0:
        return "Safe"
    elif safety_index >= 4.0:
        return "Moderate"
    elif safety_index >= 2.0:
        return "Caution"
    else:
        return "High Risk"


# # ============================================================================
# # NEWS SCRAPING AND ANALYSIS ENDPOINTS
# # ============================================================================

# @router.post("/news/scrape", response_model=NewsScrapingJobResponse)
# async def trigger_news_scraping(
#     job_data: NewsScrapingJobCreate,
#     current_user = Depends(get_current_user),
#     db = Depends(get_db)
# ):
#     """Trigger news scraping for a location to enhance safety analysis"""
    
#     # Verify city exists if city_id provided
#     if job_data.city_id:
#         city = await db.city.find_unique(where={"id": job_data.city_id})
#         if not city:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="City not found"
#             )
        
#         # Use city coordinates if not provided
#         if not job_data.latitude or not job_data.longitude:
#             job_data.latitude = city.latitude
#             job_data.longitude = city.longitude
    
#     # Create scraping job record
#     job = await db.newsscrapingjob.create(
#         data={
#             "cityId": job_data.city_id,
#             "latitude": job_data.latitude,
#             "longitude": job_data.longitude,
#             "radiusKm": job_data.radius_km,
#             "daysBack": job_data.days_back,
#             "sources": job_data.sources,
#             "status": "PENDING"
#         }
#     )
    
#     # Start news scraping in background
#     asyncio.create_task(
#         execute_news_scraping_job(job.id, job_data, db)
#     )
    
#     return NewsScrapingJobResponse(
#         id=job.id,
#         city_id=job.cityId,
#         status=job.status,
#         latitude=job.latitude,
#         longitude=job.longitude,
#         radius_km=job.radiusKm,
#         days_back=job.daysBack,
#         sources=job.sources,
#         articles_found=job.articlesFound,
#         articles_processed=job.articlesProcessed,
#         safety_relevant=job.safetyRelevant,
#         started_at=job.startedAt,
#         completed_at=job.completedAt,
#         error_message=job.errorMessage,
#         created_at=job.createdAt
#     )

# @router.get("/news/jobs/{job_id}", response_model=NewsScrapingJobResponse)
# async def get_news_scraping_job(job_id: str, db = Depends(get_db)):
#     """Get status of a news scraping job"""
    
#     job = await db.newsscrapingjob.find_unique(where={"id": job_id})
#     if not job:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="News scraping job not found"
#         )
    
#     return NewsScrapingJobResponse(
#         id=job.id,
#         city_id=job.cityId,
#         status=job.status,
#         latitude=job.latitude,
#         longitude=job.longitude,
#         radius_km=job.radiusKm,
#         days_back=job.daysBack,
#         sources=job.sources,
#         articles_found=job.articlesFound,
#         articles_processed=job.articlesProcessed,
#         safety_relevant=job.safetyRelevant,
#         started_at=job.startedAt,
#         completed_at=job.completedAt,
#         error_message=job.errorMessage,
#         created_at=job.createdAt
#     )

# @router.get("/news/analysis/{city_id}", response_model=NewsSafetyAnalysis)
# async def get_news_safety_analysis(
#     city_id: str,
#     days_back: int = Query(7, description="Days to analyze", ge=1, le=30),
#     db = Depends(get_db)
# ):
#     """Get comprehensive news safety analysis for a city"""
    
#     city = await db.city.find_unique(where={"id": city_id})
#     if not city:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="City not found"
#         )
    
#     # Get recent news articles
#     cutoff_date = datetime.utcnow() - timedelta(days=days_back)
#     articles = await db.newsarticle.find_many(
#         where={
#             "cityId": city_id,
#             "processedAt": {"gte": cutoff_date},
#             "isProcessed": True
#         },
#         order={"processedAt": "desc"}
#     )
    
#     if not articles:
#         return NewsSafetyAnalysis(
#             total_articles=0,
#             relevant_articles=0,
#             avg_threat_level=5.0,
#             sentiment_score=0.0,
#             news_safety_factor=1.0,
#             confidence=0.0,
#             analysis_date=datetime.utcnow(),
#             top_concerns=[],
#             recent_incidents=0
#         )
    
#     # Calculate metrics
#     relevant_articles = [a for a in articles if a.isRelevant]
#     total_articles = len(articles)
#     relevant_count = len(relevant_articles)
    
#     if relevant_count > 0:
#         avg_threat = sum(a.threatLevel for a in relevant_articles) / relevant_count
#         avg_sentiment = sum(a.sentimentPolarity for a in relevant_articles) / relevant_count
#         avg_confidence = sum(a.confidence for a in relevant_articles) / relevant_count
        
#         # Count recent high-threat incidents
#         recent_incidents = sum(
#             1 for a in relevant_articles 
#             if a.threatLevel >= 7 and 
#             (datetime.utcnow() - a.processedAt).days <= 3
#         )
        
#         # Get top concern types
#         concern_counts = {}
#         for article in relevant_articles:
#             concern = article.concernType
#             concern_counts[concern] = concern_counts.get(concern, 0) + 1
        
#         top_concerns = sorted(
#             concern_counts.items(),
#             key=lambda x: x[1],
#             reverse=True
#         )[:5]
#         top_concerns = [concern for concern, count in top_concerns]
        
#         # Calculate news safety factor
#         if avg_threat <= 3:
#             news_safety_factor = 1.0 + (3 - avg_threat) * 0.05
#         elif avg_threat <= 6:
#             news_safety_factor = 1.0
#         else:
#             news_safety_factor = 1.0 - (avg_threat - 6) * 0.08
        
#         # Adjust for sentiment
#         sentiment_adjustment = avg_sentiment * 0.1
#         news_safety_factor += sentiment_adjustment
#         news_safety_factor = max(0.3, min(1.5, news_safety_factor))
        
#     else:
#         avg_threat = 5.0
#         avg_sentiment = 0.0
#         avg_confidence = 0.0
#         recent_incidents = 0
#         top_concerns = []
#         news_safety_factor = 1.0
    
#     return NewsSafetyAnalysis(
#         total_articles=total_articles,
#         relevant_articles=relevant_count,
#         avg_threat_level=round(avg_threat, 2),
#         sentiment_score=round(avg_sentiment, 3),
#         news_safety_factor=round(news_safety_factor, 3),
#         confidence=round(avg_confidence, 3),
#         analysis_date=datetime.utcnow(),
#         top_concerns=top_concerns,
#         recent_incidents=recent_incidents
#     )

# async def execute_news_scraping_job(job_id: str, job_data: NewsScrapingJobCreate, db):
#     """Execute news scraping job in background"""
    
#     try:
#         # Update job status
#         await db.newsscrapingjob.update(
#             where={"id": job_id},
#             data={
#                 "status": "RUNNING",
#                 "startedAt": datetime.utcnow()
#             }
#         )
        
#         # Determine city name and country for scraping
#         if job_data.city_id:
#             city = await db.city.find_unique(where={"id": job_data.city_id})
#             city_name = city.name if city else "Unknown"
#             country = city.country if city else "Unknown"
#         else:
#             # For coordinate-only searches, try to reverse geocode or use generic terms
#             city_name = "Local Area"
#             country = "Global"
        
#         # Perform news scraping
#         async with news_agent:
#             articles = await news_agent.scrape_location_news(
#                 latitude=job_data.latitude,
#                 longitude=job_data.longitude,
#                 city_name=city_name,
#                 country=country,
#                 radius_km=job_data.radius_km,
#                 days_back=job_data.days_back
#             )
        
#         articles_found = len(articles)
#         articles_processed = 0
#         safety_relevant = 0
        
#         # Process each article with AI analysis
#         for article_data in articles:
#             try:
#                 # Perform comprehensive AI analysis
#                 analysis = await news_analysis_ai.analyze_article_comprehensive(
#                     article_data,
#                     city_name,
#                     country,
#                     (job_data.latitude, job_data.longitude)
#                 )
                
#                 # Create news article record
#                 news_article = await db.newsarticle.create(
#                     data={
#                         "title": article_data.get('title', ''),
#                         "summary": article_data.get('summary'),
#                         "content": article_data.get('content'),
#                         "url": article_data.get('url', ''),
#                         "published": article_data.get('published'),
#                         "source": article_data.get('source', ''),
#                         "type": article_data.get('type', 'RSS').upper(),
#                         "cityId": job_data.city_id,
#                         "latitude": job_data.latitude,
#                         "longitude": job_data.longitude,
#                         "locationRadius": job_data.radius_km,
#                         "safetyScore": analysis.get('relevance_score', 0.0),
#                         "threatLevel": analysis.get('threat_level', 5),
#                         "concernType": analysis.get('concern_type', 'UNKNOWN'),
#                         "sentimentPolarity": analysis.get('sentiment', {}).get('polarity', 0.0),
#                         "sentimentSubjectivity": analysis.get('sentiment', {}).get('subjectivity', 0.0),
#                         "confidence": analysis.get('confidence', 0.0),
#                         "isProcessed": True,
#                         "isRelevant": analysis.get('relevance_score', 0.0) > 0.3,
#                         "processedAt": datetime.utcnow()
#                     }
#                 )
                
#                 articles_processed += 1
                
#                 if analysis.get('relevance_score', 0.0) > 0.3:
#                     safety_relevant += 1
                    
#                     # Create safety impact record
#                     impact_factor = analysis.get('safety_impact_factor', 0.0)
#                     if abs(impact_factor) > 0.1:  # Only create if significant impact
#                         await db.newssafetyimpact.create(
#                             data={
#                                 "newsArticleId": news_article.id,
#                                 "cityId": job_data.city_id or city.id,
#                                 "impactFactor": impact_factor,
#                                 "weightFactor": min(1.0, analysis.get('confidence', 0.5) * 2),
#                                 "decayFactor": 1.0,  # Will decay over time
#                                 "latitude": job_data.latitude,
#                                 "longitude": job_data.longitude,
#                                 "radiusKm": min(job_data.radius_km, 25.0),  # Cap radius
#                                 "expiresAt": datetime.utcnow() + timedelta(days=14)  # 2 week relevance
#                             }
#                         )
                
#             except Exception as e:
#                 logging.warning(f"Failed to process article: {e}")
#                 continue
        
#         # Update job completion status
#         await db.newsscrapingjob.update(
#             where={"id": job_id},
#             data={
#                 "status": "COMPLETED",
#                 "completedAt": datetime.utcnow(),
#                 "articlesFound": articles_found,
#                 "articlesProcessed": articles_processed,
#                 "safetyRelevant": safety_relevant
#             }
#         )
        
#         # Recalculate city safety index if significant news impact
#         if job_data.city_id and safety_relevant > 0:
#             new_safety_index = await SafetyIndexCalculator.calculate_city_safety_index(
#                 job_data.city_id, db
#             )
#             await db.city.update(
#                 where={"id": job_data.city_id},
#                 data={"safetyIndex": new_safety_index}
#             )
            
#         logging.info(f"News scraping job {job_id} completed: {articles_found} found, {safety_relevant} relevant")
        
#     except Exception as e:
#         # Update job with error status
#         await db.newsscrapingjob.update(
#             where={"id": job_id},
#             data={
#                 "status": "FAILED",
#                 "completedAt": datetime.utcnow(),
#                 "errorMessage": str(e)
#             }
#         )
#         logging.error(f"News scraping job {job_id} failed: {e}")