from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import statistics
from geopy.distance import geodesic

from app.core.database import get_db
from app.core.config import settings
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    SafetyReportCreate,
    SafetyReportResponse,
    SafetyReportType,
    MessageResponse
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
        
        # Weighted average
        safety_index = (
            reports_factor * settings.SAFETY_INDEX_WEIGHT_REPORTS +
            time_factor * settings.SAFETY_INDEX_WEIGHT_TIME +
            density_factor * settings.SAFETY_INDEX_WEIGHT_DENSITY
        )
        
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
        
        # Weighted average
        safety_index = (
            reports_factor * settings.SAFETY_INDEX_WEIGHT_REPORTS +
            time_factor * settings.SAFETY_INDEX_WEIGHT_TIME +
            density_factor * settings.SAFETY_INDEX_WEIGHT_DENSITY
        )
        
        return {
            "safety_index": round(safety_index * 10, 2),
            "factors": {
                "time_factor": round(time_factor, 2),
                "density_factor": round(density_factor, 2),
                "reports_factor": round(reports_factor, 2)
            },
            "data": {
                "total_reports": len(area_reports),
                "recent_activity": area_activity,
                "current_hour": current_hour,
                "analysis_radius_km": radius_km
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