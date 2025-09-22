from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import UserResponse, MessageResponse

router = APIRouter()

class UserPreferencesModel(BaseModel):
    """User travel preferences model"""
    travel_style: str = Field(..., description="solo_adventurer, cultural_explorer, foodie, nature_lover, urban_explorer, history_buff")
    food_preferences: List[str] = Field(default=[], description="List of food preferences: vegetarian, vegan, halal, kosher, local_cuisine, street_food, fine_dining, etc.")
    activity_types: List[str] = Field(default=[], description="hiking, museums, nightlife, shopping, photography, art, music, sports, etc.")
    budget_range: str = Field(..., description="budget, mid_range, luxury")
    risk_tolerance: str = Field(..., description="low, medium, high")
    fitness_level: str = Field(..., description="low, moderate, high")
    transportation_preference: List[str] = Field(default=[], description="walking, public_transport, taxi, bicycle, car_rental")
    accommodation_type: str = Field(..., description="hostel, hotel, airbnb, luxury_resort")
    social_preference: str = Field(..., description="solo, small_groups, large_groups, locals")
    time_preference: str = Field(..., description="early_bird, night_owl, flexible")
    quest_difficulty_preference: str = Field(..., description="easy, medium, hard, mixed")
    safety_priority: str = Field(..., description="low, medium, high")
    cultural_immersion: str = Field(..., description="low, medium, high")
    language_comfort: List[str] = Field(default=[], description="List of languages user is comfortable with")
    interests: List[str] = Field(default=[], description="List of specific interests")

class PreferencesResponse(BaseModel):
    """Response model for user preferences"""
    user_id: str
    preferences: Dict[str, Any]
    updated_at: str
    message: str

@router.post("/setup", response_model=PreferencesResponse)
async def setup_user_preferences(
    preferences: UserPreferencesModel,
    current_user: UserResponse = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Set up or update user travel preferences
    
    This endpoint captures user preferences during onboarding or when updating profile.
    These preferences will be used for AI-powered itinerary and quest generation.
    """
    try:
        # Convert preferences to dict for JSON storage
        preferences_dict = preferences.dict()
        
        # Add metadata
        preferences_dict["last_updated"] = str(datetime.utcnow())
        preferences_dict["setup_completed"] = True
        
        # Update user preferences in database
        updated_user = await db.user.update(
            where={"id": current_user.id},
            data={"preferences": preferences_dict}
        )
        
        return PreferencesResponse(
            user_id=updated_user.id,
            preferences=preferences_dict,
            updated_at=preferences_dict["last_updated"],
            message="Preferences updated successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {str(e)}"
        )

@router.get("/", response_model=Dict[str, Any])
async def get_user_preferences(
    current_user: UserResponse = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current user preferences"""
    try:
        user = await db.user.find_unique(
            where={"id": current_user.id},
            select={"preferences": True}
        )
        
        if not user or not user.preferences:
            return {
                "user_id": current_user.id,
                "preferences": {},
                "setup_completed": False,
                "message": "No preferences set. Please complete preference setup."
            }
        
        return {
            "user_id": current_user.id,
            "preferences": user.preferences,
            "setup_completed": user.preferences.get("setup_completed", False),
            "message": "Preferences retrieved successfully"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve preferences: {str(e)}"
        )

@router.put("/update", response_model=PreferencesResponse)
async def update_specific_preferences(
    preference_updates: Dict[str, Any],
    current_user: UserResponse = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Update specific preference fields without replacing all preferences
    """
    try:
        # Get current preferences
        user = await db.user.find_unique(
            where={"id": current_user.id},
            select={"preferences": True}
        )
        
        current_preferences = user.preferences if user and user.preferences else {}
        
        # Merge with updates
        updated_preferences = {**current_preferences, **preference_updates}
        updated_preferences["last_updated"] = str(datetime.utcnow())
        
        # Update in database
        updated_user = await db.user.update(
            where={"id": current_user.id},
            data={"preferences": updated_preferences}
        )
        
        return PreferencesResponse(
            user_id=updated_user.id,
            preferences=updated_preferences,
            updated_at=updated_preferences["last_updated"],
            message="Preferences updated successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {str(e)}"
        )

@router.delete("/reset", response_model=MessageResponse)
async def reset_preferences(
    current_user: UserResponse = Depends(get_current_user),
    db = Depends(get_db)
):
    """Reset user preferences to empty state"""
    try:
        await db.user.update(
            where={"id": current_user.id},
            data={"preferences": {}}
        )
        
        return MessageResponse(message="Preferences reset successfully")
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset preferences: {str(e)}"
        )