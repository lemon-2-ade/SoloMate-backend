from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from geopy.distance import geodesic

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    CityCreate,
    CityResponse,
    MessageResponse
)

router = APIRouter()

@router.get("/", response_model=List[CityResponse])
async def get_cities(
    search: Optional[str] = Query(None, description="Search cities by name or country"),
    latitude: Optional[float] = Query(None, description="User latitude for distance sorting"),
    longitude: Optional[float] = Query(None, description="User longitude for distance sorting"),
    radius_km: Optional[float] = Query(None, description="Search radius in kilometers"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db = Depends(get_db)
):
    """Get list of cities with optional search and proximity filtering"""
    
    # Build where clause
    where_clause = {"isActive": True}
    
    if search:
        where_clause["OR"] = [
            {"name": {"contains": search, "mode": "insensitive"}},
            {"country": {"contains": search, "mode": "insensitive"}}
        ]
    
    cities = await db.city.find_many(
        where=where_clause,
        skip=offset,
        take=limit,
        order={"name": "asc"}
    )
    
    # If user location provided, filter by radius and sort by distance
    if latitude is not None and longitude is not None:
        user_location = (latitude, longitude)
        
        # Calculate distances and filter by radius
        cities_with_distance = []
        for city in cities:
            city_location = (city.latitude, city.longitude)
            distance = geodesic(user_location, city_location).kilometers
            
            if radius_km is None or distance <= radius_km:
                cities_with_distance.append((city, distance))
        
        # Sort by distance
        cities_with_distance.sort(key=lambda x: x[1])
        cities = [city for city, _ in cities_with_distance]
    
    return [
        CityResponse(
            id=city.id,
            name=city.name,
            country=city.country,
            latitude=city.latitude,
            longitude=city.longitude,
            description=city.description,
            image_url=city.imageUrl,
            safety_index=city.safetyIndex,
            is_active=city.isActive
        )
        for city in cities
    ]

@router.get("/{city_id}", response_model=CityResponse)
async def get_city(city_id: str, db = Depends(get_db)):
    """Get city details by ID"""
    city = await db.city.find_unique(where={"id": city_id})
    
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    return CityResponse(
        id=city.id,
        name=city.name,
        country=city.country,
        latitude=city.latitude,
        longitude=city.longitude,
        description=city.description,
        image_url=city.imageUrl,
        safety_index=city.safetyIndex,
        is_active=city.isActive
    )

@router.get("/{city_id}/stats")
async def get_city_stats(city_id: str, db = Depends(get_db)):
    """Get city statistics"""
    
    # Verify city exists
    city = await db.city.find_unique(where={"id": city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Get or create city stats
    city_stats = await db.citystats.find_unique(where={"cityId": city_id})
    
    if not city_stats:
        # Calculate stats
        total_quests = await db.quest.count(
            where={"cityId": city_id, "isActive": True}
        )
        
        # Count active users (users who completed at least one quest in this city)
        active_users_query = await db.questprogress.find_many(
            where={
                "status": "completed",
                "quest": {"cityId": city_id}
            },
            distinct=["userId"]
        )
        active_users = len(active_users_query)
        
        # Calculate average safety score from reports
        safety_reports = await db.safetyreport.find_many(
            where={"cityId": city_id, "isVerified": True}
        )
        
        if safety_reports:
            avg_safety = sum(report.severity for report in safety_reports) / len(safety_reports)
        else:
            avg_safety = 5.0  # Default neutral score
        
        # Count badges minted for quests in this city
        badges_minted_query = await db.userbadge.find_many(
            where={
                "badge": {
                    "questRewards": {
                        "some": {"cityId": city_id}
                    }
                }
            }
        )
        total_badges_minted = len(badges_minted_query)
        
        # Create or update city stats
        city_stats = await db.citystats.upsert(
            where={"cityId": city_id},
            data={
                "cityId": city_id,
                "totalQuests": total_quests,
                "activeUsers": active_users,
                "averageSafetyScore": avg_safety,
                "totalBadgesMinted": total_badges_minted
            },
            create={
                "cityId": city_id,
                "totalQuests": total_quests,
                "activeUsers": active_users,
                "averageSafetyScore": avg_safety,
                "totalBadgesMinted": total_badges_minted
            }
        )
    
    return {
        "city_id": city_id,
        "city_name": city.name,
        "total_quests": city_stats.totalQuests,
        "active_users": city_stats.activeUsers,
        "safety_index": city.safetyIndex,
        "average_safety_score": city_stats.averageSafetyScore,
        "total_badges_minted": city_stats.totalBadgesMinted,
        "last_updated": city_stats.lastUpdated
    }

@router.post("/", response_model=CityResponse)
async def create_city(
    city_data: CityCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new city (admin only)"""
    
    # TODO: Add admin role check
    # For now, any authenticated user can create cities (hackathon purposes)
    
    # Check if city already exists
    existing_city = await db.city.find_first(
        where={
            "name": city_data.name,
            "country": city_data.country
        }
    )
    
    if existing_city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="City already exists"
        )
    
    # Create new city
    city = await db.city.create(
        data={
            "name": city_data.name,
            "country": city_data.country,
            "latitude": city_data.latitude,
            "longitude": city_data.longitude,
            "description": city_data.description,
            "imageUrl": city_data.image_url
        }
    )
    
    return CityResponse(
        id=city.id,
        name=city.name,
        country=city.country,
        latitude=city.latitude,
        longitude=city.longitude,
        description=city.description,
        image_url=city.imageUrl,
        safety_index=city.safetyIndex,
        is_active=city.isActive
    )

@router.get("/{city_id}/leaderboard")
async def get_city_leaderboard(
    city_id: str,
    type: str = Query("xp", description="Leaderboard type: xp, badges, quests"),
    period: str = Query("all_time", description="Period: daily, weekly, monthly, all_time"),
    limit: int = Query(10, le=50),
    db = Depends(get_db)
):
    """Get city leaderboard"""
    
    # Verify city exists
    city = await db.city.find_unique(where={"id": city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Get leaderboard based on type
    if type == "xp":
        # Get users with most XP from quests in this city
        users_query = await db.user.find_many(
            where={
                "questProgresses": {
                    "some": {
                        "status": "completed",
                        "quest": {"cityId": city_id}
                    }
                }
            },
            order={"totalXP": "desc"},
            take=limit,
            include={"questProgresses": {"include": {"quest": True}}}
        )
        
        leaderboard = []
        for i, user in enumerate(users_query):
            # Calculate XP from this city specifically
            city_xp = sum(
                qp.quest.xpReward for qp in user.questProgresses 
                if qp.status == "completed" and qp.quest.cityId == city_id
            )
            
            leaderboard.append({
                "rank": i + 1,
                "user": {
                    "id": user.id,
                    "username": user.username or f"User {user.walletAddress[:8]}...",
                    "wallet_address": user.walletAddress,
                    "profile_image_url": user.profileImageUrl
                },
                "score": city_xp,
                "metric": "City XP"
            })
    
    elif type == "badges":
        # Get users with most badges from this city
        users_with_badges = await db.user.find_many(
            where={
                "badges": {
                    "some": {
                        "badge": {
                            "questRewards": {
                                "some": {"cityId": city_id}
                            }
                        }
                    }
                }
            },
            include={
                "badges": {
                    "include": {
                        "badge": {
                            "include": {"questRewards": True}
                        }
                    }
                }
            },
            take=limit
        )
        
        leaderboard = []
        for user in users_with_badges:
            city_badges = sum(
                1 for badge in user.badges
                if any(quest.cityId == city_id for quest in badge.badge.questRewards)
            )
            leaderboard.append({
                "user": user,
                "score": city_badges
            })
        
        # Sort by badge count
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        
        # Format response
        leaderboard = [
            {
                "rank": i + 1,
                "user": {
                    "id": entry["user"].id,
                    "username": entry["user"].username or f"User {entry['user'].walletAddress[:8]}...",
                    "wallet_address": entry["user"].walletAddress,
                    "profile_image_url": entry["user"].profileImageUrl
                },
                "score": entry["score"],
                "metric": "City Badges"
            }
            for i, entry in enumerate(leaderboard[:limit])
        ]
    
    else:  # quests
        # Get users with most completed quests in this city
        quest_completions = await db.questprogress.group_by(
            by=["userId"],
            where={
                "status": "completed",
                "quest": {"cityId": city_id}
            },
            _count={"userId": True},
            order={"_count": {"userId": "desc"}},
            take=limit
        )
        
        leaderboard = []
        for i, completion in enumerate(quest_completions):
            user = await db.user.find_unique(where={"id": completion.userId})
            leaderboard.append({
                "rank": i + 1,
                "user": {
                    "id": user.id,
                    "username": user.username or f"User {user.walletAddress[:8]}...",
                    "wallet_address": user.walletAddress,
                    "profile_image_url": user.profileImageUrl
                },
                "score": completion._count.userId,
                "metric": "Completed Quests"
            })
    
    return {
        "city": {
            "id": city.id,
            "name": city.name,
            "country": city.country
        },
        "leaderboard_type": type,
        "period": period,
        "entries": leaderboard
    }