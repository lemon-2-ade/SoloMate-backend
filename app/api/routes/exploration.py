from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.services.google_maps import google_maps_service
from app.models.schemas import (
    ExplorationCategory,
    ExplorationResponse,
    NearbyPlace,
    DailyItinerary,
    ItineraryTimeSlot,
    DailyChecklist,
    ChecklistItem,
    ChecklistItemType,
    MessageResponse
)

router = APIRouter()

# Category mapping for Google Places API
CATEGORY_PLACE_TYPES = {
    ExplorationCategory.FOOD: ["restaurant", "food", "meal_takeaway", "cafe", "bakery"],
    ExplorationCategory.SHOPS: ["store", "shopping_mall", "clothing_store", "electronics_store", "grocery_or_supermarket"],
    ExplorationCategory.MEDICAL: ["hospital", "pharmacy", "doctor", "health", "dentist"],
    ExplorationCategory.TRAVEL: ["transit_station", "airport", "bus_station", "subway_station", "taxi_stand"],
    ExplorationCategory.TOURISM: ["tourist_attraction", "museum", "amusement_park", "zoo", "aquarium"],
    ExplorationCategory.ENTERTAINMENT: ["movie_theater", "night_club", "bar", "casino", "bowling_alley"],
    ExplorationCategory.SERVICES: ["bank", "atm", "gas_station", "car_rental", "lodging"]
}

@router.get("/nearby/all", response_model=List[ExplorationResponse])
async def get_all_nearby_categories(
    latitude: float = Query(..., description="User's current latitude"),
    longitude: float = Query(..., description="User's current longitude"),
    radius_km: float = Query(2.0, description="Search radius in kilometers", le=50.0),
    limit_per_category: int = Query(5, description="Max places per category", le=20),
    current_user = Depends(get_current_user)
):
    """Get nearby places for all categories (overview for home screen)"""
    
    try:
        all_responses = []
        
        # Get places for each major category
        main_categories = [
            ExplorationCategory.FOOD,
            ExplorationCategory.SHOPS,
            ExplorationCategory.TOURISM,
            ExplorationCategory.MEDICAL
        ]
        
        for category in main_categories:
            try:
                response = await get_nearby_places_by_category(
                    category=category,
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=radius_km,
                    limit=limit_per_category,
                    current_user=current_user
                )
                all_responses.append(response)
            except Exception as e:
                # Continue with other categories if one fails
                print(f"Failed to get places for {category}: {e}")
                continue
        
        return all_responses
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch nearby places overview: {str(e)}"
        )

@router.get("/nearby/{category}", response_model=ExplorationResponse)
async def get_nearby_places_by_category(
    category: ExplorationCategory,
    latitude: float = Query(..., description="User's current latitude"),
    longitude: float = Query(..., description="User's current longitude"),
    radius_km: float = Query(2.0, description="Search radius in kilometers", le=50.0),
    limit: int = Query(20, description="Maximum number of places to return", le=50),
    current_user = Depends(get_current_user)
):
    """Get nearby places by category for exploration"""
    
    try:
        radius_meters = int(radius_km * 1000)
        place_types = CATEGORY_PLACE_TYPES.get(category, ["point_of_interest"])
        
        all_places = []
        
        # Search for each place type in the category
        for place_type in place_types:
            places = google_maps_service.find_nearby_places(
                latitude=latitude,
                longitude=longitude,
                place_type=place_type,
                radius=radius_meters
            )
            all_places.extend(places)
        
        # Remove duplicates and convert to NearbyPlace objects
        unique_places = {}
        for place in all_places:
            if place['place_id'] not in unique_places:
                # Calculate distance (basic approximation)
                import math
                lat_diff = latitude - place['location']['latitude']
                lon_diff = longitude - place['location']['longitude']
                distance = math.sqrt(lat_diff**2 + lon_diff**2) * 111000  # Rough meters
                
                nearby_place = NearbyPlace(
                    place_id=place['place_id'],
                    name=place['name'],
                    category=category,
                    rating=place.get('rating'),
                    user_ratings_total=place.get('user_ratings_total'),
                    vicinity=place.get('vicinity'),
                    latitude=place['location']['latitude'],
                    longitude=place['location']['longitude'],
                    distance_meters=distance,
                    photo_reference=place['photos'][0]['photo_reference'] if place.get('photos') else None
                )
                unique_places[place['place_id']] = nearby_place
        
        # Sort by distance and limit results
        sorted_places = sorted(unique_places.values(), key=lambda x: x.distance_meters or float('inf'))
        limited_places = sorted_places[:limit]
        
        return ExplorationResponse(
            category=category,
            places=limited_places,
            total_found=len(unique_places),
            search_center={"latitude": latitude, "longitude": longitude},
            radius_km=radius_km
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch nearby places: {str(e)}"
        )

@router.get("/place/{place_id}")
async def get_place_details(
    place_id: str,
    current_user = Depends(get_current_user)
):
    """Get detailed information about a specific place"""
    
    try:
        place_details = google_maps_service.get_place_details(place_id)
        
        if not place_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Place not found"
            )
        
        return place_details
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch place details: {str(e)}"
        )

@router.get("/search")
async def search_places(
    query: str = Query(..., description="Search query for places"),
    latitude: Optional[float] = Query(None, description="Search near this latitude"),
    longitude: Optional[float] = Query(None, description="Search near this longitude"),
    radius_km: Optional[float] = Query(5.0, description="Search radius in kilometers"),
    limit: int = Query(20, description="Maximum number of results", le=50),
    current_user = Depends(get_current_user)
):
    """Search for places using text query"""
    
    try:
        location = None
        radius = None
        
        if latitude is not None and longitude is not None:
            location = (latitude, longitude)
            radius = int(radius_km * 1000) if radius_km else None
        
        places = google_maps_service.search_places_text(
            query=query,
            location=location,
            radius=radius
        )
        
        # Limit results
        limited_places = places[:limit]
        
        return {
            "query": query,
            "total_found": len(places),
            "places": limited_places,
            "search_location": {"latitude": latitude, "longitude": longitude} if location else None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search places: {str(e)}"
        )

@router.post("/checklist/generate", response_model=DailyChecklist)
async def generate_daily_checklist(
    city_name: str,
    date: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Generate a personalized daily checklist for travel"""
    
    try:
        if not date:
            date = datetime.now().strftime("%A, %d %B")
        
        # Get user profile for personalization
        user = await db.user.find_unique(where={"id": current_user.id})
        
        # Base checklist items
        checklist_items = []
        
        # Morning preparation items
        checklist_items.extend([
            ChecklistItem(
                id="morning_prep_1",
                type=ChecklistItemType.PREPARATION,
                title="Check weather forecast",
                description="Plan your outfit and activities based on weather",
                priority="high",
                due_time="Morning"
            ),
            ChecklistItem(
                id="morning_prep_2",
                type=ChecklistItemType.PREPARATION,
                title="Charge devices",
                description="Ensure phone, camera, and power banks are charged",
                priority="medium"
            )
        ])
        
        # Safety items
        checklist_items.extend([
            ChecklistItem(
                id="safety_1",
                type=ChecklistItemType.SAFETY,
                title="Share location",
                description="Let someone know your planned itinerary",
                priority="high"
            ),
            ChecklistItem(
                id="safety_2",
                type=ChecklistItemType.SAFETY,
                title="Emergency contacts",
                description="Save local emergency numbers",
                priority="medium"
            )
        ])
        
        # Exploration items
        checklist_items.extend([
            ChecklistItem(
                id="explore_1",
                type=ChecklistItemType.EXPLORATION,
                title="Download offline maps",
                description="Ensure you can navigate without internet",
                priority="medium",
                location_dependent=True
            ),
            ChecklistItem(
                id="explore_2",
                type=ChecklistItemType.EXPLORATION,
                title="Research local customs",
                description="Learn basic etiquette and customs",
                priority="low"
            )
        ])
        
        # Accommodation items
        if preferences and preferences.get("has_accommodation"):
            checklist_items.append(
                ChecklistItem(
                    id="accommodation_1",
                    type=ChecklistItemType.ACCOMMODATION,
                    title="Confirm accommodation",
                    description="Verify booking and check-in details",
                    priority="high",
                    due_time="Before departure"
                )
            )
        
        # Calculate completion rate (simulate some completed items)
        import random
        for item in checklist_items[:2]:  # Mark first 2 items as completed
            item.is_completed = True
        
        completion_rate = len([item for item in checklist_items if item.is_completed]) / len(checklist_items)
        
        return DailyChecklist(
            date=date,
            city=city_name,
            items=checklist_items,
            completion_rate=round(completion_rate, 2)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate checklist: {str(e)}"
        )

@router.put("/checklist/{item_id}/complete", response_model=MessageResponse)
async def complete_checklist_item(
    item_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Mark a checklist item as completed"""
    
    try:
        # In a real implementation, you'd update the database
        # For now, we'll just return success
        
        return MessageResponse(
            message=f"Checklist item {item_id} marked as completed",
            success=True
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete checklist item: {str(e)}"
        )