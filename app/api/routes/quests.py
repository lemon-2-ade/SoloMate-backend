from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from geopy.distance import geodesic
import math

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    QuestCreate,
    QuestResponse,
    QuestType,
    QuestDifficulty,
    LocationProofCreate,
    LocationProofResponse,
    MessageResponse
)

router = APIRouter()

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula"""
    R = 6371000  # Earth's radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2) * math.sin(delta_lat/2) + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * \
        math.sin(delta_lon/2) * math.sin(delta_lon/2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

@router.get("/", response_model=List[QuestResponse])
async def get_quests(
    city_id: Optional[str] = Query(None, description="Filter by city ID"),
    quest_type: Optional[QuestType] = Query(None, description="Filter by quest type"),
    difficulty: Optional[QuestDifficulty] = Query(None, description="Filter by difficulty"),
    latitude: Optional[float] = Query(None, description="User latitude for distance filtering"),
    longitude: Optional[float] = Query(None, description="User longitude for distance filtering"),
    radius_km: Optional[float] = Query(None, description="Search radius in kilometers"),
    user_level: Optional[int] = Query(None, description="Filter by user level requirement"),
    available_only: bool = Query(True, description="Only show available quests"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get quests with filtering options"""
    
    # Build where clause
    where_clause = {"isActive": True}
    
    if city_id:
        where_clause["cityId"] = city_id
    
    if quest_type:
        where_clause["type"] = quest_type
    
    if difficulty:
        where_clause["difficulty"] = difficulty
    
    if user_level is not None:
        where_clause["requiredLevel"] = {"lte": user_level}
    else:
        where_clause["requiredLevel"] = {"lte": current_user.level}
    
    if available_only:
        now = datetime.utcnow()
        where_clause["OR"] = [
            {"availableFrom": None, "availableTo": None},
            {"availableFrom": {"lte": now}, "availableTo": None},
            {"availableFrom": None, "availableTo": {"gte": now}},
            {"availableFrom": {"lte": now}, "availableTo": {"gte": now}}
        ]
    
    quests = await db.quest.find_many(
        where=where_clause,
        include={"city": True, "questPoints": True},
        skip=offset,
        take=limit,
        order={"createdAt": "desc"}
    )
    
    # Filter by distance if user location provided
    if latitude is not None and longitude is not None and radius_km is not None:
        user_location = (latitude, longitude)
        radius_meters = radius_km * 1000
        
        filtered_quests = []
        for quest in quests:
            quest_location = (quest.latitude, quest.longitude)
            distance = geodesic(user_location, quest_location).meters
            
            if distance <= radius_meters:
                filtered_quests.append(quest)
        
        quests = filtered_quests
    
    return [
        QuestResponse(
            id=quest.id,
            title=quest.title,
            description=quest.description,
            type=quest.type,
            difficulty=quest.difficulty,
            city_id=quest.cityId,
            latitude=quest.latitude,
            longitude=quest.longitude,
            radius=quest.radius,
            xp_reward=quest.xpReward,
            token_reward=quest.tokenReward,
            required_level=quest.requiredLevel,
            current_completions=quest.currentCompletions,
            max_completions=quest.maxCompletions,
            is_active=quest.isActive,
            created_at=quest.createdAt
        )
        for quest in quests
    ]

@router.get("/{quest_id}", response_model=Dict[str, Any])
async def get_quest_details(
    quest_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get detailed quest information"""
    
    quest = await db.quest.find_unique(
        where={"id": quest_id},
        include={
            "city": True,
            "questPoints": {"order": {"order": "asc"}},
            "questProgresses": {
                "where": {"userId": current_user.id}
            }
        }
    )
    
    if not quest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest not found"
        )
    
    # Get user's progress on this quest
    user_progress = quest.questProgresses[0] if quest.questProgresses else None
    
    return {
        "quest": QuestResponse(
            id=quest.id,
            title=quest.title,
            description=quest.description,
            type=quest.type,
            difficulty=quest.difficulty,
            city_id=quest.cityId,
            latitude=quest.latitude,
            longitude=quest.longitude,
            radius=quest.radius,
            xp_reward=quest.xpReward,
            token_reward=quest.tokenReward,
            required_level=quest.requiredLevel,
            current_completions=quest.currentCompletions,
            max_completions=quest.maxCompletions,
            is_active=quest.isActive,
            created_at=quest.createdAt
        ),
        "city": {
            "id": quest.city.id,
            "name": quest.city.name,
            "country": quest.city.country
        },
        "quest_points": [
            {
                "id": point.id,
                "name": point.name,
                "description": point.description,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "radius": point.radius,
                "order": point.order,
                "is_optional": point.isOptional
            }
            for point in quest.questPoints
        ],
        "hints": quest.hints,
        "time_limit": quest.timeLimit,
        "available_from": quest.availableFrom,
        "available_to": quest.availableTo,
        "requirements": quest.requirements,
        "partner_info": quest.partnerInfo,
        "user_progress": {
            "status": user_progress.status if user_progress else None,
            "points_visited": user_progress.pointsVisited if user_progress else [],
            "started_at": user_progress.startedAt if user_progress else None,
            "completed_at": user_progress.completedAt if user_progress else None
        } if user_progress else None
    }

@router.post("/{quest_id}/start", response_model=MessageResponse)
async def start_quest(
    quest_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Start a quest"""
    
    # Check if quest exists and is available
    quest = await db.quest.find_unique(where={"id": quest_id})
    if not quest or not quest.isActive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest not found or not available"
        )
    
    # Check user level requirement
    if current_user.level < quest.requiredLevel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Required level {quest.requiredLevel}, current level {current_user.level}"
        )
    
    # Check if quest is available (time constraints)
    now = datetime.utcnow()
    if quest.availableFrom and quest.availableFrom > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quest not yet available"
        )
    
    if quest.availableTo and quest.availableTo < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quest no longer available"
        )
    
    # Check if user already has this quest in progress or completed
    existing_progress = await db.questprogress.find_unique(
        where={
            "userId_questId": {
                "userId": current_user.id,
                "questId": quest_id
            }
        }
    )
    
    if existing_progress:
        if existing_progress.status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quest already completed"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quest already in progress"
            )
    
    # Check max completions
    if quest.maxCompletions and quest.currentCompletions >= quest.maxCompletions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quest has reached maximum completions"
        )
    
    # Create quest progress
    await db.questprogress.create(
        data={
            "userId": current_user.id,
            "questId": quest_id,
            "status": "started",
            "pointsVisited": []
        }
    )
    
    return MessageResponse(message="Quest started successfully")

@router.post("/{quest_id}/verify-location", response_model=Dict[str, Any])
async def verify_location(
    quest_id: str,
    location_proof: LocationProofCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Verify user location for quest completion"""
    
    # Get quest and user progress
    quest_progress = await db.questprogress.find_unique(
        where={
            "userId_questId": {
                "userId": current_user.id,
                "questId": quest_id
            }
        },
        include={"quest": {"include": {"questPoints": True}}}
    )
    
    if not quest_progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest not started"
        )
    
    if quest_progress.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quest already completed"
        )
    
    quest = quest_progress.quest
    
    # Determine target location
    if location_proof.quest_point_id:
        # Specific quest point
        quest_point = next(
            (qp for qp in quest.questPoints if qp.id == location_proof.quest_point_id),
            None
        )
        if not quest_point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest point not found"
            )
        
        target_lat, target_lon = quest_point.latitude, quest_point.longitude
        allowed_radius = quest_point.radius
    else:
        # Main quest location
        target_lat, target_lon = quest.latitude, quest.longitude
        allowed_radius = quest.radius
    
    # Calculate distance
    distance = calculate_distance(
        location_proof.latitude, location_proof.longitude,
        target_lat, target_lon
    )
    
    # Check if within allowed radius
    is_within_radius = distance <= allowed_radius
    
    # Create location proof record
    proof = await db.locationproof.create(
        data={
            "userId": current_user.id,
            "questPointId": location_proof.quest_point_id,
            "latitude": location_proof.latitude,
            "longitude": location_proof.longitude,
            "accuracy": location_proof.accuracy,
            "deviceInfo": location_proof.device_info,
            "photoUrl": location_proof.photo_url,
            "isVerified": is_within_radius
        }
    )
    
    unlock_available = False
    quest_completed = False
    
    if is_within_radius:
        # Update quest progress
        points_visited = quest_progress.pointsVisited or []
        
        if location_proof.quest_point_id:
            # Add quest point to visited list
            if location_proof.quest_point_id not in points_visited:
                points_visited.append(location_proof.quest_point_id)
        
        # Check if quest can be completed
        required_points = [qp.id for qp in quest.questPoints if not qp.isOptional]
        all_required_visited = all(point_id in points_visited for point_id in required_points)
        
        if all_required_visited or not quest.questPoints:  # Simple location quest
            # Complete the quest
            await db.questprogress.update(
                where={"id": quest_progress.id},
                data={
                    "status": "completed",
                    "pointsVisited": points_visited,
                    "completedAt": datetime.utcnow(),
                    "proofData": {
                        "final_proof_id": proof.id,
                        "completion_time": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # Update quest completion count
            await db.quest.update(
                where={"id": quest_id},
                data={"currentCompletions": {"increment": 1}}
            )
            
            # Award XP and tokens
            await db.user.update(
                where={"id": current_user.id},
                data={
                    "totalXP": {"increment": quest.xpReward},
                    "tokens": {"increment": quest.tokenReward}
                }
            )
            
            quest_completed = True
            unlock_available = True
        else:
            # Update progress
            await db.questprogress.update(
                where={"id": quest_progress.id},
                data={
                    "status": "in_progress",
                    "pointsVisited": points_visited
                }
            )
            unlock_available = True
    
    return {
        "location_verified": is_within_radius,
        "distance_meters": round(distance, 2),
        "allowed_radius": allowed_radius,
        "unlock_available": unlock_available,
        "quest_completed": quest_completed,
        "proof_id": proof.id,
        "message": "Location verified successfully!" if is_within_radius 
                  else f"Too far from target. Distance: {round(distance, 2)}m, Required: {allowed_radius}m"
    }

@router.post("/", response_model=QuestResponse)
async def create_quest(
    quest_data: QuestCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new quest (admin/partner only)"""
    
    # TODO: Add admin/partner role check
    
    # Verify city exists
    city = await db.city.find_unique(where={"id": quest_data.city_id})
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Create quest
    quest = await db.quest.create(
        data={
            "title": quest_data.title,
            "description": quest_data.description,
            "type": quest_data.type,
            "difficulty": quest_data.difficulty,
            "cityId": quest_data.city_id,
            "latitude": quest_data.latitude,
            "longitude": quest_data.longitude,
            "radius": quest_data.radius,
            "xpReward": quest_data.xp_reward,
            "tokenReward": quest_data.token_reward,
            "requiredLevel": quest_data.required_level,
            "timeLimit": quest_data.time_limit,
            "availableFrom": quest_data.available_from,
            "availableTo": quest_data.available_to,
            "maxCompletions": quest_data.max_completions,
            "requirements": quest_data.requirements,
            "hints": quest_data.hints,
            "partnerInfo": quest_data.partner_info
        }
    )
    
    # Create quest points if provided
    for point_data in quest_data.quest_points:
        await db.questpoint.create(
            data={
                "questId": quest.id,
                "name": point_data.name,
                "description": point_data.description,
                "latitude": point_data.latitude,
                "longitude": point_data.longitude,
                "radius": point_data.radius,
                "order": point_data.order,
                "isOptional": point_data.is_optional
            }
        )
    
    return QuestResponse(
        id=quest.id,
        title=quest.title,
        description=quest.description,
        type=quest.type,
        difficulty=quest.difficulty,
        city_id=quest.cityId,
        latitude=quest.latitude,
        longitude=quest.longitude,
        radius=quest.radius,
        xp_reward=quest.xpReward,
        token_reward=quest.tokenReward,
        required_level=quest.requiredLevel,
        current_completions=quest.currentCompletions,
        max_completions=quest.maxCompletions,
        is_active=quest.isActive,
        created_at=quest.createdAt
    )

@router.get("/nearby", response_model=List[QuestResponse])
async def get_nearby_quests(
    latitude: float,
    longitude: float,
    radius_km: float = Query(5.0, description="Search radius in kilometers"),
    limit: int = Query(10, le=50),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get quests near user's location"""
    
    # Get all active quests
    quests = await db.quest.find_many(
        where={
            "isActive": True,
            "requiredLevel": {"lte": current_user.level}
        },
        include={"city": True}
    )
    
    # Filter by distance
    nearby_quests = []
    user_location = (latitude, longitude)
    radius_meters = radius_km * 1000
    
    for quest in quests:
        quest_location = (quest.latitude, quest.longitude)
        distance = geodesic(user_location, quest_location).meters
        
        if distance <= radius_meters:
            nearby_quests.append((quest, distance))
    
    # Sort by distance and take limited results
    nearby_quests.sort(key=lambda x: x[1])
    nearby_quests = nearby_quests[:limit]
    
    return [
        QuestResponse(
            id=quest.id,
            title=quest.title,
            description=quest.description,
            type=quest.type,
            difficulty=quest.difficulty,
            city_id=quest.cityId,
            latitude=quest.latitude,
            longitude=quest.longitude,
            radius=quest.radius,
            xp_reward=quest.xpReward,
            token_reward=quest.tokenReward,
            required_level=quest.requiredLevel,
            current_completions=quest.currentCompletions,
            max_completions=quest.maxCompletions,
            is_active=quest.isActive,
            created_at=quest.createdAt
        )
        for quest, _ in nearby_quests
    ]