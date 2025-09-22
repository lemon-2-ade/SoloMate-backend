from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from datetime import datetime
import json
import random

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    ItineraryCreate,
    ItineraryResponse,
    ItineraryUpdate,
    ItinerarySource,
    MessageResponse,
    UserResponse
)

router = APIRouter()


async def generate_basic_time_slots(itinerary_data: ItineraryCreate):
    """
    Generate basic time slots for user-created itineraries
    """
    basic_activities = [
        {
            "time": "09:00 AM",
            "activity": f"Explore {itinerary_data.destination}",
            "location": itinerary_data.destination,
            "duration": "2 hours",
            "activity_type": "sightseeing",
            "description": f"Start your day exploring the highlights of {itinerary_data.destination}",
            "estimated_cost": "$0-20"
        },
        {
            "time": "11:30 AM",
            "activity": "Local Coffee Break",
            "location": f"Café in {itinerary_data.destination}",
            "duration": "30 minutes",
            "activity_type": "dining",
            "description": "Take a break and enjoy local coffee culture",
            "estimated_cost": "$5-15"
        },
        {
            "time": "12:00 PM",
            "activity": "Lunch at Local Restaurant",
            "location": f"Restaurant in {itinerary_data.destination}",
            "duration": "1 hour",
            "activity_type": "dining",
            "description": "Experience local cuisine",
            "estimated_cost": f"${itinerary_data.budget_per_day // 3 if itinerary_data.budget_per_day else '15-30'}"
        },
        {
            "time": "02:00 PM",
            "activity": "Cultural Activity",
            "location": f"Cultural site in {itinerary_data.destination}",
            "duration": "2 hours",
            "activity_type": "quest",
            "description": "Immerse yourself in local culture and history",
            "estimated_cost": "$10-25"
        }
    ]
    
    return basic_activities


async def generate_quests_for_itinerary(db, itinerary, itinerary_data: ItineraryCreate):
    """
    Automatically generate quests based on the itinerary data
    """
    generated_quests = []
    
    # Quest templates based on itinerary type and content
    quest_templates = [
        {
            "title": f"Discover {itinerary.destination or itinerary.cityName}",
            "description": f"Explore the hidden gems and local culture of {itinerary.destination or itinerary.cityName}",
            "type": "exploration",
            "difficulty": "easy",
            "pointsReward": 50,
            "requirements": ["Visit 3 local landmarks", "Try local food", "Take photos"]
        },
        {
            "title": "Cultural Explorer",
            "description": "Immerse yourself in the local culture and traditions",
            "type": "cultural", 
            "difficulty": "medium",
            "pointsReward": 75,
            "requirements": ["Visit a museum or cultural site", "Learn about local history", "Interact with locals"]
        },
        {
            "title": "Food Adventure",
            "description": "Experience the authentic flavors of the region",
            "type": "dining",
            "difficulty": "easy",
            "pointsReward": 40,
            "requirements": ["Try 2 local dishes", "Visit a local market", "Rate your experience"]
        }
    ]
    
    # Add interest-specific quests if user provided interests
    if itinerary_data.interests:
        for interest in itinerary_data.interests:
            if interest.lower() in ["art", "museums", "culture"]:
                quest_templates.append({
                    "title": "Art & Culture Quest",
                    "description": f"Dive deep into the artistic heritage of {itinerary.destination or itinerary.cityName}",
                    "type": "cultural",
                    "difficulty": "medium",
                    "pointsReward": 80,
                    "requirements": ["Visit art gallery", "Learn about local artists", "Create travel journal entry"]
                })
            elif interest.lower() in ["food", "dining", "cuisine"]:
                quest_templates.append({
                    "title": "Culinary Master",
                    "description": "Become a local food expert",
                    "type": "dining", 
                    "difficulty": "hard",
                    "pointsReward": 100,
                    "requirements": ["Try 5 different local dishes", "Learn a local recipe", "Visit traditional market"]
                })
    
    # Create quests in database
    for template in quest_templates[:3]:  # Limit to 3 quests per itinerary
        try:
            quest = await db.quest.create(
                data={
                    "title": template["title"],
                    "description": template["description"],
                    "type": template["type"],
                    "difficulty": template["difficulty"],
                    "pointsReward": template["pointsReward"],
                    "requirements": template["requirements"],
                    "cityId": itinerary.cityId,
                    "itineraryId": itinerary.id,
                    "isActive": True
                }
            )
            generated_quests.append(quest)
        except Exception as e:
            print(f"Error creating quest: {e}")
            continue
    
    return generated_quests


@router.post("/", response_model=ItineraryResponse)
async def create_itinerary(
    itinerary_data: ItineraryCreate,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Create and save a new itinerary to the database
    
    This endpoint handles both AI-generated and user-created itineraries.
    For user-created itineraries, it will automatically generate quests.
    """
    try:
        # Validate city_id if provided
        city_id = None
        if itinerary_data.city_id:
            city = await db.city.find_unique(where={"id": itinerary_data.city_id})
            if not city:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="City not found"
                )
            city_id = city.id
        
        # Handle different itinerary types
        if itinerary_data.source == ItinerarySource.AI:
            # AI-generated itinerary (existing logic)
            if not itinerary_data.time_slots:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Time slots are required for AI-generated itineraries"
                )
            
            time_slots_json = [slot.dict() for slot in itinerary_data.time_slots]
            total_estimated_time = itinerary_data.total_estimated_time
            
            # Count quest-type activities for questsGenerated field
            quests_generated = sum(1 for slot in itinerary_data.time_slots 
                                 if slot.activity_type == "quest")
        
        else:
            # User-created itinerary
            if not itinerary_data.destination:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Destination is required for user-created itineraries"
                )
            
            # Generate basic time slots for user itinerary
            basic_time_slots = await generate_basic_time_slots(itinerary_data)
            time_slots_json = basic_time_slots
            total_estimated_time = "6-8 hours"
            quests_generated = 0  # Will be generated after itinerary creation
        
        # Prepare common fields
        weather_json = itinerary_data.weather if itinerary_data.weather else None
        preferences_json = itinerary_data.preferences if itinerary_data.preferences else None
        ai_context_json = itinerary_data.ai_context if itinerary_data.ai_context else None
        
        # Create the itinerary in the database
        itinerary = await db.itinerary.create(
            data={
                "userId": current_user.id,
                "cityId": city_id,
                "title": itinerary_data.title,
                "date": itinerary_data.date,
                "cityName": itinerary_data.city_name,
                "timeSlots": time_slots_json,
                "totalEstimatedTime": total_estimated_time,
                "safetyNotes": itinerary_data.safety_notes,
                "weather": weather_json,
                "preferences": preferences_json,
                "aiContext": ai_context_json,
                "source": itinerary_data.source,
                "questsGenerated": quests_generated,
                
                # User itinerary specific fields
                "destination": itinerary_data.destination,
                "startDate": itinerary_data.start_date,
                "endDate": itinerary_data.end_date,
                "budgetPerDay": itinerary_data.budget_per_day,
                "travelStyle": itinerary_data.travel_style,
                "interests": itinerary_data.interests or [],
                "accommodationType": itinerary_data.accommodation_type,
                "accommodationBudgetPerNight": itinerary_data.accommodation_budget_per_night,
                "safetyPriority": itinerary_data.safety_priority,
                "specialRequests": itinerary_data.special_requests,
                "status": itinerary_data.status or "draft",
                
                "isActive": True
            }
        )
        
        # Automatically generate quests for the itinerary
        generated_quests = await generate_quests_for_itinerary(db, itinerary, itinerary_data)
        
        # Update quest count in itinerary
        await db.itinerary.update(
            where={"id": itinerary.id},
            data={"questsGenerated": len(generated_quests)}
        )
        
        # Prepare time slots for response
        if itinerary_data.source == ItinerarySource.AI and itinerary_data.time_slots:
            response_time_slots = itinerary_data.time_slots
        else:
            # Convert JSON back to ItineraryTimeSlot objects for response
            from app.models.schemas import ItineraryTimeSlot
            response_time_slots = [ItineraryTimeSlot(**slot) for slot in time_slots_json]
        
        # Convert back to response format
        return ItineraryResponse(
            id=itinerary.id,
            user_id=itinerary.userId,
            city_id=itinerary.cityId,
            title=itinerary.title,
            date=itinerary.date,
            city_name=itinerary.cityName,
            time_slots=response_time_slots,
            total_estimated_time=total_estimated_time,
            safety_notes=itinerary.safetyNotes,
            weather=itinerary.weather,
            preferences=itinerary.preferences,
            ai_context=itinerary.aiContext,
            quests_generated=len(generated_quests),
            source=itinerary_data.source,
            is_active=itinerary.isActive,
            created_at=itinerary.createdAt,
            updated_at=itinerary.updatedAt
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create itinerary: {str(e)}"
        )


@router.get("/", response_model=List[ItineraryResponse])
async def get_user_itineraries(
    current_user: UserResponse = Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
    active_only: bool = True,
    db=Depends(get_db)
):
    """
    Get all itineraries for the current user
    """
    try:
        where_clause = {"userId": current_user.id}
        if active_only:
            where_clause["isActive"] = True
            
        itineraries = await db.itinerary.find_many(
            where=where_clause,
            order_by={"createdAt": "desc"},
            skip=offset,
            take=limit
        )
        
        # Convert to response format
        response_itineraries = []
        for itinerary in itineraries:
            # Parse time_slots from JSON back to objects
            time_slots = [slot for slot in itinerary.timeSlots] if itinerary.timeSlots else []
            
            response_itineraries.append(ItineraryResponse(
                id=itinerary.id,
                user_id=itinerary.userId,
                city_id=itinerary.cityId,
                title=itinerary.title,
                date=itinerary.date,
                city_name=itinerary.cityName,
                time_slots=time_slots,
                total_estimated_time=itinerary.totalEstimatedTime,
                safety_notes=itinerary.safetyNotes,
                weather=itinerary.weather,
                preferences=itinerary.preferences,
                ai_context=itinerary.aiContext,
                quests_generated=itinerary.questsGenerated,
                source=ItinerarySource(itinerary.source) if itinerary.source else ItinerarySource.AI,
                is_active=itinerary.isActive,
                created_at=itinerary.createdAt,
                updated_at=itinerary.updatedAt
            ))
            
        return response_itineraries
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve itineraries: {str(e)}"
        )


@router.get("/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Get a specific itinerary by ID
    """
    try:
        itinerary = await db.itinerary.find_unique(
            where={"id": itinerary_id}
        )
        
        if not itinerary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Itinerary not found"
            )
            
        # Check if user owns this itinerary
        if itinerary.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this itinerary"
            )
            
        # Parse time_slots from JSON back to objects
        time_slots = [slot for slot in itinerary.timeSlots] if itinerary.timeSlots else []
        
        return ItineraryResponse(
            id=itinerary.id,
            user_id=itinerary.userId,
            city_id=itinerary.cityId,
            title=itinerary.title,
            date=itinerary.date,
            city_name=itinerary.cityName,
            time_slots=time_slots,
            total_estimated_time=itinerary.totalEstimatedTime,
            safety_notes=itinerary.safetyNotes,
            weather=itinerary.weather,
            preferences=itinerary.preferences,
            ai_context=itinerary.aiContext,
            quests_generated=itinerary.questsGenerated,
            source=ItinerarySource(itinerary.source) if itinerary.source else ItinerarySource.AI,
            is_active=itinerary.isActive,
            created_at=itinerary.createdAt,
            updated_at=itinerary.updatedAt
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve itinerary: {str(e)}"
        )


@router.put("/{itinerary_id}", response_model=ItineraryResponse)
async def update_itinerary(
    itinerary_id: str,
    update_data: ItineraryUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Update an existing itinerary
    """
    try:
        # Check if itinerary exists and user owns it
        itinerary = await db.itinerary.find_unique(
            where={"id": itinerary_id}
        )
        
        if not itinerary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Itinerary not found"
            )
            
        if itinerary.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this itinerary"
            )
            
        # Prepare update data
        update_dict = {}
        
        if update_data.title is not None:
            update_dict["title"] = update_data.title
            
        if update_data.is_active is not None:
            update_dict["isActive"] = update_data.is_active
            
        if update_data.time_slots is not None:
            update_dict["timeSlots"] = [slot.dict() for slot in update_data.time_slots]
            # Recalculate quests generated
            update_dict["questsGenerated"] = sum(1 for slot in update_data.time_slots 
                                               if slot.activity_type == "quest")
            
        if update_data.safety_notes is not None:
            update_dict["safetyNotes"] = update_data.safety_notes
            
        # Update the itinerary
        updated_itinerary = await db.itinerary.update(
            where={"id": itinerary_id},
            data=update_dict
        )
        
        # Return updated itinerary
        time_slots = [slot for slot in updated_itinerary.timeSlots] if updated_itinerary.timeSlots else []
        
        return ItineraryResponse(
            id=updated_itinerary.id,
            user_id=updated_itinerary.userId,
            city_id=updated_itinerary.cityId,
            title=updated_itinerary.title,
            date=updated_itinerary.date,
            city_name=updated_itinerary.cityName,
            time_slots=time_slots,
            total_estimated_time=updated_itinerary.totalEstimatedTime,
            safety_notes=updated_itinerary.safetyNotes,
            weather=updated_itinerary.weather,
            preferences=updated_itinerary.preferences,
            ai_context=updated_itinerary.aiContext,
            quests_generated=updated_itinerary.questsGenerated,
            source=ItinerarySource(updated_itinerary.source) if updated_itinerary.source else ItinerarySource.AI,
            is_active=updated_itinerary.isActive,
            created_at=updated_itinerary.createdAt,
            updated_at=updated_itinerary.updatedAt
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update itinerary: {str(e)}"
        )


@router.delete("/{itinerary_id}", response_model=MessageResponse)
async def delete_itinerary(
    itinerary_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Delete an itinerary (soft delete by setting isActive to False)
    """
    try:
        # Check if itinerary exists and user owns it
        itinerary = await db.itinerary.find_unique(
            where={"id": itinerary_id}
        )
        
        if not itinerary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Itinerary not found"
            )
            
        if itinerary.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this itinerary"
            )
            
        # Soft delete by setting isActive to False
        await db.itinerary.update(
            where={"id": itinerary_id},
            data={"isActive": False}
        )
        
        return MessageResponse(message="Itinerary deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete itinerary: {str(e)}"
        )