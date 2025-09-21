from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.services.ai_agent import generate_recommendations
from app.models.schemas import (
    AiRecommendationResponse,
    AiRecommendationType,
    MessageResponse,
    DailyItinerary,
    ItineraryTimeSlot
)

router = APIRouter()

@router.post("/recommendations/{recommendation_type}")
async def get_ai_recommendations(
    recommendation_type: AiRecommendationType,
    latitude: Optional[float] = Query(None, description="User's current latitude"),
    longitude: Optional[float] = Query(None, description="User's current longitude"),
    context: Optional[Dict[str, Any]] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get AI-powered recommendations for the user"""
    
    try:
        # Prepare user location if provided
        user_location = None
        if latitude is not None and longitude is not None:
            user_location = {"latitude": latitude, "longitude": longitude}
        
        # Generate recommendations using AI agent
        recommendations_data = await generate_recommendations(
            user_id=current_user.id,
            recommendation_type=recommendation_type.value,
            user_location=user_location,
            context=context or {}
        )
        
        # Store recommendations in database for tracking
        stored_recommendations = []
        for rec in recommendations_data["recommendations"]:
            stored_rec = await db.airecommendation.create(
                data={
                    "userId": current_user.id,
                    "type": recommendation_type,
                    "content": rec,
                    "reason": rec.get("reasoning", recommendations_data["reasoning"]),
                    "confidence": rec.get("confidence", 0.5),
                    "expiresAt": datetime.utcnow() + timedelta(days=7)  # Expire in 7 days
                }
            )
            stored_recommendations.append(stored_rec)
        
        return {
            "success": True,
            "recommendation_type": recommendation_type,
            "total_recommendations": len(stored_recommendations),
            "recommendations": [
                AiRecommendationResponse(
                    id=rec.id,
                    type=rec.type,
                    content=rec.content,
                    reason=rec.reason,
                    confidence=rec.confidence,
                    created_at=rec.createdAt,
                    expires_at=rec.expiresAt
                )
                for rec in stored_recommendations
            ],
            "user_persona": recommendations_data.get("user_persona", {}),
            "overall_confidence": recommendations_data.get("confidence", 0.5),
            "generated_at": recommendations_data["generated_at"]
        }
    
    except Exception as e:
        # Fallback to simple recommendations if AI fails
        fallback_rec = await db.airecommendation.create(
            data={
                "userId": current_user.id,
                "type": recommendation_type,
                "content": {
                    "title": "Explore nearby attractions",
                    "description": "Discover what's around you",
                    "fallback": True
                },
                "reason": "Fallback recommendation due to AI service unavailability",
                "confidence": 0.3,
                "expiresAt": datetime.utcnow() + timedelta(days=1)
            }
        )
        
        return {
            "success": True,
            "recommendation_type": recommendation_type,
            "total_recommendations": 1,
            "recommendations": [
                AiRecommendationResponse(
                    id=fallback_rec.id,
                    type=fallback_rec.type,
                    content=fallback_rec.content,
                    reason=fallback_rec.reason,
                    confidence=fallback_rec.confidence,
                    created_at=fallback_rec.createdAt,
                    expires_at=fallback_rec.expiresAt
                )
            ],
            "fallback": True,
            "error": str(e)
        }

@router.get("/history", response_model=List[AiRecommendationResponse])
async def get_recommendation_history(
    recommendation_type: Optional[AiRecommendationType] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    include_viewed: bool = Query(True),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's AI recommendation history"""
    
    where_clause = {
        "userId": current_user.id,
        "isActive": True
    }
    
    if recommendation_type:
        where_clause["type"] = recommendation_type
    
    if not include_viewed:
        where_clause["isViewed"] = False
    
    recommendations = await db.airecommendation.find_many(
        where=where_clause,
        skip=offset,
        take=limit,
        order={"createdAt": "desc"}
    )
    
    return [
        AiRecommendationResponse(
            id=rec.id,
            type=rec.type,
            content=rec.content,
            reason=rec.reason,
            confidence=rec.confidence,
            created_at=rec.createdAt,
            expires_at=rec.expiresAt
        )
        for rec in recommendations
    ]

@router.post("/{recommendation_id}/accept", response_model=MessageResponse)
async def accept_recommendation(
    recommendation_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Mark a recommendation as accepted"""
    
    recommendation = await db.airecommendation.find_unique(
        where={
            "id": recommendation_id,
            "userId": current_user.id
        }
    )
    
    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found"
        )
    
    await db.airecommendation.update(
        where={"id": recommendation_id},
        data={
            "isViewed": True,
            "isAccepted": True
        }
    )
    
    # Award tokens for engaging with AI recommendations
    await db.user.update(
        where={"id": current_user.id},
        data={"tokens": {"increment": 2}}
    )
    
    return MessageResponse(message="Recommendation accepted successfully")

@router.post("/{recommendation_id}/dismiss", response_model=MessageResponse)
async def dismiss_recommendation(
    recommendation_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Mark a recommendation as dismissed"""
    
    recommendation = await db.airecommendation.find_unique(
        where={
            "id": recommendation_id,
            "userId": current_user.id
        }
    )
    
    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found"
        )
    
    await db.airecommendation.update(
        where={"id": recommendation_id},
        data={
            "isViewed": True,
            "isAccepted": False,
            "isActive": False
        }
    )
    
    return MessageResponse(message="Recommendation dismissed")

@router.get("/insights")
async def get_user_insights(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get AI-powered insights about user's travel patterns"""
    
    # Get user's quest history
    quest_progresses = await db.questprogress.find_many(
        where={
            "userId": current_user.id,
            "status": "completed"
        },
        include={"quest": {"include": {"city": True}}},
        order={"completedAt": "desc"}
    )
    
    # Get user's recommendations acceptance rate
    total_recommendations = await db.airecommendation.count(
        where={"userId": current_user.id}
    )
    
    accepted_recommendations = await db.airecommendation.count(
        where={
            "userId": current_user.id,
            "isAccepted": True
        }
    )
    
    # Analyze patterns
    quest_types = [qp.quest.type for qp in quest_progresses]
    cities_visited = list(set(qp.quest.city.name for qp in quest_progresses))
    countries_visited = list(set(qp.quest.city.country for qp in quest_progresses))
    
    # Calculate stats
    type_preferences = {}
    for qtype in quest_types:
        type_preferences[qtype] = type_preferences.get(qtype, 0) + 1
    
    most_preferred_type = max(type_preferences.keys(), key=lambda x: type_preferences[x]) if type_preferences else None
    
    # Recent activity analysis
    last_30_days = datetime.utcnow() - timedelta(days=30)
    recent_quests = [qp for qp in quest_progresses if qp.completedAt and qp.completedAt >= last_30_days]
    
    acceptance_rate = (accepted_recommendations / total_recommendations * 100) if total_recommendations > 0 else 0
    
    insights = {
        "travel_style": {
            "most_preferred_quest_type": most_preferred_type,
            "quest_type_distribution": type_preferences,
            "exploration_level": "Local Explorer" if len(countries_visited) <= 1 else "International Traveler",
            "activity_level": "High" if len(recent_quests) >= 10 else "Medium" if len(recent_quests) >= 5 else "Low"
        },
        "destinations": {
            "cities_visited": cities_visited,
            "countries_visited": countries_visited,
            "total_cities": len(cities_visited),
            "total_countries": len(countries_visited),
            "favorite_destinations": cities_visited[:3]  # Top 3 most visited
        },
        "ai_engagement": {
            "total_recommendations_received": total_recommendations,
            "acceptance_rate": round(acceptance_rate, 1),
            "engagement_level": "High" if acceptance_rate >= 70 else "Medium" if acceptance_rate >= 40 else "Low"
        },
        "achievements": {
            "total_quests_completed": len(quest_progresses),
            "recent_activity": len(recent_quests),
            "streak_days": current_user.streakDays,
            "current_level": current_user.level
        },
        "recommendations": [
            "Try exploring heritage sites if you haven't already" if "HERITAGE" not in quest_types else None,
            "Consider visiting a new country for international explorer badge" if len(countries_visited) <= 1 else None,
            "Engage more with AI recommendations to get better suggestions" if acceptance_rate < 50 else None
        ]
    }
    
    # Remove None recommendations
    insights["recommendations"] = [r for r in insights["recommendations"] if r is not None]
    
    return insights

@router.post("/feedback")
async def submit_recommendation_feedback(
    recommendation_id: str,
    feedback_data: Dict[str, Any],
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Submit feedback on AI recommendations to improve future suggestions"""
    
    recommendation = await db.airecommendation.find_unique(
        where={
            "id": recommendation_id,
            "userId": current_user.id
        }
    )
    
    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found"
        )
    
    # Store feedback (in a real system, this would be used to retrain the AI)
    feedback = {
        "rating": feedback_data.get("rating", 0),  # 1-5 scale
        "helpful": feedback_data.get("helpful", False),
        "comments": feedback_data.get("comments", ""),
        "followed": feedback_data.get("followed", False),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Update recommendation with feedback
    current_content = recommendation.content
    current_content["user_feedback"] = feedback
    
    await db.airecommendation.update(
        where={"id": recommendation_id},
        data={"content": current_content}
    )
    
    # Award tokens for providing feedback
    await db.user.update(
        where={"id": current_user.id},
        data={"tokens": {"increment": 1}}
    )
    
    return MessageResponse(message="Feedback submitted successfully. Thank you for helping improve our AI!")

@router.get("/personalization")
async def get_personalization_settings(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current AI personalization settings"""
    
    preferences = current_user.preferences or {}
    ai_preferences = preferences.get("ai", {})
    
    return {
        "personalization_enabled": ai_preferences.get("enabled", True),
        "recommendation_frequency": ai_preferences.get("frequency", "daily"),
        "preferred_quest_types": ai_preferences.get("preferred_types", []),
        "safety_priority": ai_preferences.get("safety_priority", "medium"),
        "adventure_level": ai_preferences.get("adventure_level", "medium"),
        "cultural_interests": ai_preferences.get("cultural_interests", []),
        "notification_preferences": ai_preferences.get("notifications", {
            "new_recommendations": True,
            "quest_suggestions": True,
            "safety_alerts": True
        })
    }

@router.post("/personalization")
async def update_personalization_settings(
    settings: Dict[str, Any],
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update AI personalization settings"""
    
    current_preferences = current_user.preferences or {}
    
    # Update AI preferences
    current_preferences["ai"] = {
        "enabled": settings.get("personalization_enabled", True),
        "frequency": settings.get("recommendation_frequency", "daily"),
        "preferred_types": settings.get("preferred_quest_types", []),
        "safety_priority": settings.get("safety_priority", "medium"),
        "adventure_level": settings.get("adventure_level", "medium"),
        "cultural_interests": settings.get("cultural_interests", []),
        "notifications": settings.get("notification_preferences", {})
    }
    
    # Update user preferences
    await db.user.update(
        where={"id": current_user.id},
        data={"preferences": current_preferences}
    )
    
    return MessageResponse(message="AI personalization settings updated successfully")

@router.post("/generate-itinerary", response_model=DailyItinerary)
async def generate_daily_itinerary(
    city_name: str = Query(..., description="City name for the itinerary"),
    date: Optional[str] = Query(None, description="Date for the itinerary (e.g., 'Tuesday, 23 December')"),
    latitude: Optional[float] = Query(None, description="User's current latitude"),
    longitude: Optional[float] = Query(None, description="User's current longitude"),
    preferences: Optional[Dict[str, Any]] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Generate AI-powered daily itinerary"""
    
    try:
        # Prepare user location if provided
        user_location = None
        if latitude is not None and longitude is not None:
            user_location = {"latitude": latitude, "longitude": longitude}
        
        # Set default date if not provided
        if not date:
            from datetime import datetime
            date = datetime.now().strftime("%A, %d %B")
        
        # Prepare context for itinerary generation
        itinerary_context = {
            "city_name": city_name,
            "date": date,
            "preferences": preferences or {},
            "weather_consideration": True,
            "include_quests": True,
            "include_exploration": True
        }
        
        # Generate itinerary using AI agent
        recommendations_data = await generate_recommendations(
            user_id=current_user.id,
            recommendation_type="ITINERARY",
            user_location=user_location,
            context={"itinerary_context": itinerary_context}
        )
        
        # Convert AI recommendations to structured itinerary
        time_slots = []
        safety_notes = []
        
        for rec in recommendations_data["recommendations"]:
            time_slot = ItineraryTimeSlot(
                start_time=rec.get("start_time", "09:00 AM"),
                end_time=rec.get("end_time", "10:00 AM"),
                activity_type=rec.get("activity_type", "exploration"),
                title=rec.get("title", "Activity"),
                description=rec.get("description", "Explore and enjoy"),
                location=rec.get("location"),
                estimated_duration=rec.get("estimated_duration", "1 hour"),
                difficulty=rec.get("difficulty"),
                weather_dependent=rec.get("weather_dependent", False)
            )
            time_slots.append(time_slot)
        
        # Add safety notes based on user profile and AI analysis
        if recommendations_data.get("user_persona", {}).get("risk_tolerance") == "low":
            safety_notes.extend([
                "Stay in well-lit and crowded areas",
                "Share your itinerary with someone",
                "Keep emergency contacts handy"
            ])
        
        # Calculate total estimated time
        total_minutes = len(time_slots) * 90  # Assume 1.5 hours average per activity
        total_hours = total_minutes // 60
        remaining_minutes = total_minutes % 60
        total_estimated_time = f"{total_hours} hours {remaining_minutes} minutes"
        
        return DailyItinerary(
            date=date,
            city=city_name,
            weather={"status": "Check local weather", "temperature": "Varies"},
            time_slots=time_slots,
            total_estimated_time=total_estimated_time,
            safety_notes=safety_notes
        )
        
    except Exception as e:
        # Fallback itinerary
        fallback_slots = [
            ItineraryTimeSlot(
                start_time="09:00 AM",
                end_time="10:30 AM",
                activity_type="exploration",
                title="Morning City Walk",
                description="Explore the city center and main attractions",
                estimated_duration="1 hour 30 minutes",
                weather_dependent=True
            ),
            ItineraryTimeSlot(
                start_time="11:00 AM",
                end_time="12:30 PM",
                activity_type="quest",
                title="Local Heritage Quest",
                description="Discover historical landmarks and cultural sites",
                estimated_duration="1 hour 30 minutes",
                difficulty="EASY"
            ),
            ItineraryTimeSlot(
                start_time="02:00 PM",
                end_time="04:00 PM",
                activity_type="exploration",
                title="Local Food Discovery",
                description="Try authentic local cuisine and visit food markets",
                estimated_duration="2 hours"
            )
        ]
        
        return DailyItinerary(
            date=date or datetime.now().strftime("%A, %d %B"),
            city=city_name,
            time_slots=fallback_slots,
            total_estimated_time="5 hours",
            safety_notes=["Stay hydrated", "Keep local emergency numbers", "Use official transportation"]
        )