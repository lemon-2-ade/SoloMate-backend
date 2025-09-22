from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import uuid

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.services.ai_agent import generate_recommendations
from app.models.schemas import (
    AiRecommendationResponse,
    AiRecommendationType,
    MessageResponse,
    DailyItinerary,
    ItineraryTimeSlot,
    ItineraryCreate,
    ItineraryResponse,
    QuestType,
    QuestDifficulty
)

router = APIRouter()

def _calculate_xp_reward(difficulty: QuestDifficulty) -> int:
    """Calculate XP reward based on quest difficulty"""
    rewards = {
        QuestDifficulty.EASY: 50,
        QuestDifficulty.MEDIUM: 100,
        QuestDifficulty.HARD: 200,
        QuestDifficulty.EXTREME: 300
    }
    return rewards.get(difficulty, 50)

def _calculate_token_reward(difficulty: QuestDifficulty) -> int:
    """Calculate token reward based on quest difficulty"""
    rewards = {
        QuestDifficulty.EASY: 10,
        QuestDifficulty.MEDIUM: 25,
        QuestDifficulty.HARD: 50,
        QuestDifficulty.EXTREME: 100
    }
    return rewards.get(difficulty, 10)

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

@router.post("/generate-itinerary")
async def generate_daily_itinerary(
    city_name: str = Query(..., description="City name for the itinerary"),
    date: Optional[str] = Query(None, description="Date for the itinerary (e.g., 'Tuesday, 23 December')"),
    latitude: Optional[float] = Query(None, description="User's current latitude"),
    longitude: Optional[float] = Query(None, description="User's current longitude"),
    generate_quests: bool = Query(True, description="Generate quests for itinerary locations"),
    auto_save: bool = Query(True, description="Automatically save itinerary to database"),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Generate AI-powered daily itinerary with automatic quest creation
    
    This endpoint implements the complete user flow:
    1. Uses user preferences for personalized itinerary generation
    2. Creates quests for each location in the itinerary
    3. Links quests to the itinerary in the database
    4. Returns both itinerary and generated quests
    """
    
    try:
        # Get user preferences from database
        user = await db.user.find_unique(
            where={"id": current_user.id},
            select={"preferences": True}
        )
        
        user_preferences = user.preferences if user and user.preferences else {}
        
        user_location = None
        if latitude is not None and longitude is not None:
            user_location = {"latitude": latitude, "longitude": longitude}

        if not date:
            date = datetime.now().strftime("%A, %d %B")
        
        # Prepare context for itinerary generation with user preferences
        itinerary_context = {
            "city_name": city_name,
            "date": date,
            "user_preferences": user_preferences,
            "weather_consideration": True,
            "include_quests": True,
            "include_exploration": True,
            "generate_detailed_locations": True
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
        quest_locations = []
        safety_notes = []
        
        for i, rec in enumerate(recommendations_data.get("recommendations", [])):
            # Create time slot
            time_slot = ItineraryTimeSlot(
                start_time=rec.get("start_time", f"{9 + (i * 2):02d}:00 AM"),
                end_time=rec.get("end_time", f"{10 + (i * 2):02d}:30 AM"),
                activity_type=rec.get("activity_type", "exploration"),
                title=rec.get("title", f"Activity {i + 1}"),
                description=rec.get("description", "Explore and enjoy"),
                location=rec.get("location"),
                estimated_duration=rec.get("estimated_duration", "1 hour 30 minutes"),
                difficulty=rec.get("difficulty"),
                weather_dependent=rec.get("weather_dependent", False)
            )
            time_slots.append(time_slot)
            
            # Collect locations for quest generation
            if generate_quests and rec.get("location") and rec.get("latitude") and rec.get("longitude"):
                quest_locations.append({
                    "title": rec.get("title"),
                    "description": rec.get("description"),
                    "location": rec.get("location"),
                    "latitude": rec.get("latitude"),
                    "longitude": rec.get("longitude"),
                    "activity_type": rec.get("activity_type"),
                    "difficulty": rec.get("difficulty", "EASY"),
                    "time_slot_index": i
                })
        
        # Add safety notes based on user preferences
        risk_tolerance = user_preferences.get("risk_tolerance", "medium")
        if risk_tolerance == "low":
            safety_notes.extend([
                "Stay in well-lit and crowded areas",
                "Share your itinerary with someone",
                "Keep emergency contacts handy",
                "Use only official transportation"
            ])
        elif risk_tolerance == "medium":
            safety_notes.extend([
                "Share your itinerary with someone",
                "Keep emergency contacts handy"
            ])
        else:  # high risk tolerance
            safety_notes.extend([
                "Keep emergency contacts handy"
            ])
        
        # Calculate total estimated time
        total_minutes = len(time_slots) * 90  # Assume 1.5 hours average per activity
        total_hours = total_minutes // 60
        remaining_minutes = total_minutes % 60
        total_estimated_time = f"{total_hours} hours {remaining_minutes} minutes"
        
        # Create the itinerary response
        itinerary = DailyItinerary(
            date=date,
            city=city_name,
            weather={"status": "Check local weather", "temperature": "Varies"},
            time_slots=time_slots,
            total_estimated_time=total_estimated_time,
            safety_notes=safety_notes
        )
        
        saved_itinerary = None
        generated_quests = []
        
        # Save to database if requested
        if auto_save:
            try:
                # Get city_id if available
                city_id = None
                if user_location:
                    city = await db.city.find_first(
                        where={
                            "name": {"contains": city_name, "mode": "insensitive"},
                            "isActive": True
                        }
                    )
                    if city:
                        city_id = city.id
                
                # Convert time slots to JSON-compatible format
                time_slots_json = []
                for slot in time_slots:
                    slot_dict = {
                        "start_time": slot.start_time,
                        "end_time": slot.end_time,
                        "activity_type": slot.activity_type,
                        "title": slot.title,
                        "description": slot.description,
                        "estimated_duration": slot.estimated_duration,
                        "weather_dependent": slot.weather_dependent
                    }
                    if slot.location:
                        slot_dict["location"] = slot.location
                    if slot.difficulty:
                        slot_dict["difficulty"] = slot.difficulty
                    time_slots_json.append(slot_dict)
                
                # Create itinerary in database
                create_data = {
                    "userId": current_user.id,
                    "title": f"{city_name} Daily Itinerary",
                    "date": date,
                    "cityName": city_name,
                    "timeSlots": time_slots_json,
                    "totalEstimatedTime": total_estimated_time,
                    "safetyNotes": safety_notes,
                    "weather": {"status": "Check local weather", "temperature": "Varies"},
                    "preferences": user_preferences,
                    "aiContext": recommendations_data.get("user_persona", {}),
                    "questsGenerated": 0  # Will be updated after quest creation
                }
                
                if city_id:
                    create_data["cityId"] = city_id
                
                saved_itinerary = await db.itinerary.create(data=create_data)
                
                # Generate quests for locations if requested
                if generate_quests and quest_locations:
                    quests_created = 0
                    
                    for quest_loc in quest_locations:
                        try:
                            # Determine quest type based on activity type
                            activity_type = quest_loc.get("activity_type", "exploration")
                            if activity_type in ["heritage", "culture", "museum"]:
                                quest_type = QuestType.HERITAGE
                            elif activity_type in ["hidden", "local", "secret"]:
                                quest_type = QuestType.HIDDEN_GEMS
                            else:
                                quest_type = QuestType.DAILY
                            
                            # Map difficulty
                            difficulty_map = {
                                "easy": QuestDifficulty.EASY,
                                "medium": QuestDifficulty.MEDIUM,
                                "hard": QuestDifficulty.HARD,
                                "extreme": QuestDifficulty.EXTREME
                            }
                            quest_difficulty = difficulty_map.get(
                                quest_loc.get("difficulty", "easy").lower(), 
                                QuestDifficulty.EASY
                            )
                            
                            # Create quest
                            quest = await db.quest.create(
                                data={
                                    "title": f"Explore: {quest_loc['title']}",
                                    "description": f"Visit and explore {quest_loc['title']}. {quest_loc.get('description', '')}",
                                    "type": quest_type,
                                    "difficulty": quest_difficulty,
                                    "cityId": city_id or str(uuid.uuid4()),
                                    "itineraryId": saved_itinerary.id,
                                    "latitude": quest_loc["latitude"],
                                    "longitude": quest_loc["longitude"],
                                    "radius": 100.0,
                                    "xpReward": _calculate_xp_reward(quest_difficulty),
                                    "tokenReward": _calculate_token_reward(quest_difficulty),
                                    "requiredLevel": 1,
                                    "isActive": True,
                                    "hints": [f"Look for {quest_loc['location']}", "Take a photo to prove your visit"],
                                    "requirements": {
                                        "time_slot_index": quest_loc["time_slot_index"]
                                    }
                                }
                            )
                            
                            generated_quests.append({
                                "id": quest.id,
                                "title": quest.title,
                                "description": quest.description,
                                "type": quest.type,
                                "difficulty": quest.difficulty,
                                "latitude": quest.latitude,
                                "longitude": quest.longitude,
                                "xp_reward": quest.xpReward,
                                "token_reward": quest.tokenReward,
                                "location": quest_loc["location"],
                                "time_slot_index": quest_loc["time_slot_index"]
                            })
                            
                            quests_created += 1
                            
                        except Exception as quest_error:
                            print(f"Failed to create quest for {quest_loc.get('title', 'Unknown')}: {quest_error}")
                    
                    # Update itinerary with quest count
                    if quests_created > 0:
                        await db.itinerary.update(
                            where={"id": saved_itinerary.id},
                            data={"questsGenerated": quests_created}
                        )
                
            except Exception as db_error:
                print(f"Failed to save itinerary to database: {db_error}")
                # Continue without failing the request
        
        # Return comprehensive response
        return {
            "success": True,
            "message": "Itinerary generated successfully" + (" with quests" if generate_quests else ""),
            "itinerary": {
                "id": saved_itinerary.id if saved_itinerary else None,
                "date": date,
                "city": city_name,
                "time_slots": [slot.__dict__ for slot in time_slots],
                "total_estimated_time": total_estimated_time,
                "safety_notes": safety_notes,
                "weather": {"status": "Check local weather", "temperature": "Varies"},
                "quests_generated": len(generated_quests)
            },
            "generated_quests": generated_quests if generate_quests else [],
            "user_preferences_used": user_preferences,
            "quest_generation_summary": {
                "total_locations": len(quest_locations) if generate_quests else 0,
                "quests_created": len(generated_quests),
                "auto_saved": auto_save
            } if generate_quests else None
        }
        
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
        
        # Create fallback itinerary
        fallback_itinerary = DailyItinerary(
            date=date or datetime.now().strftime("%A, %d %B"),
            city=city_name,
            time_slots=fallback_slots,
            total_estimated_time="5 hours",
            safety_notes=["Stay hydrated", "Keep local emergency numbers", "Use official transportation"]
        )
        
        # Save fallback to database
        try:
            # Get city_id if available
            city_id = None
            if user_location:
                # Try to find the city in our database based on name
                city = await db.city.find_first(
                    where={
                        "name": {"contains": city_name, "mode": "insensitive"},
                        "isActive": True
                    }
                )
                if city:
                    city_id = city.id
            
            # Create database record for fallback
            # Convert fallback time slots to plain dictionaries for JSON storage
            fallback_time_slots_json = []
            for slot in fallback_slots:
                slot_dict = {
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "activity_type": slot.activity_type,
                    "title": slot.title,
                    "description": slot.description,
                    "estimated_duration": slot.estimated_duration,
                    "weather_dependent": slot.weather_dependent
                }
                # Only add optional fields if they exist and are not None
                if slot.location:
                    slot_dict["location"] = slot.location
                if slot.difficulty:
                    slot_dict["difficulty"] = slot.difficulty
                fallback_time_slots_json.append(slot_dict)
            
            fallback_create_data = {
                "userId": current_user.id,
                "title": f"{city_name} Daily Itinerary (Fallback)",
                "date": date or datetime.now().strftime("%A, %d %B"),
                "cityName": city_name,
                "timeSlots": fallback_time_slots_json,
                "totalEstimatedTime": "5 hours",
                "safetyNotes": ["Stay hydrated", "Keep local emergency numbers", "Use official transportation"],
                "weather": None,
                "preferences": user_preferences,
                "aiContext": {"fallback": True, "error": str(e)},
                "questsGenerated": len([slot for slot in fallback_slots if slot.activity_type == "quest"])
            }
            
            # Add city ID only if it exists
            if city_id:
                fallback_create_data["cityId"] = city_id
                
            db_itinerary = await db.itinerary.create(data=fallback_create_data)
            print(f"✅ Successfully saved fallback itinerary to database with ID: {db_itinerary.id}")
        except Exception as db_error:
            # Log the error but don't fail the request
            print(f"❌ Failed to save fallback itinerary to database: {db_error}")
            print(f"Error type: {type(db_error).__name__}")
            if hasattr(db_error, 'code'):
                print(f"Error code: {db_error.code}")
        
        return fallback_itinerary


@router.get("/itinerary/{itinerary_id}/quests")
async def get_itinerary_quests(
    itinerary_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get all quests generated for a specific itinerary"""
    try:
        # Verify itinerary ownership
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
        
        # Find quests generated for this itinerary
        quests = await db.quest.find_many(
            where={
                "itineraryId": itinerary_id,
                "isActive": True
            },
            include={"city": True}
        )
        
        return {
            "success": True,
            "itinerary_id": itinerary_id,
            "total_quests": len(quests),
            "quests": [
                {
                    "id": quest.id,
                    "title": quest.title,
                    "description": quest.description,
                    "type": quest.type,
                    "difficulty": quest.difficulty,
                    "latitude": quest.latitude,
                    "longitude": quest.longitude,
                    "xp_reward": quest.xpReward,
                    "token_reward": quest.tokenReward,
                    "time_slot_index": quest.requirements.get("time_slot_index") if quest.requirements else None,
                    "created_at": quest.createdAt
                }
                for quest in quests
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve itinerary quests: {str(e)}"
        )


@router.get("/itineraries", response_model=List[ItineraryResponse])
async def get_user_itineraries(
    limit: int = Query(10, description="Maximum number of itineraries to return", le=50),
    offset: int = Query(0, description="Number of itineraries to skip"),
    city_name: Optional[str] = Query(None, description="Filter by city name"),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's saved itineraries"""
    
    try:
        # Build query filters
        where_clause = {"userId": current_user.id, "isActive": True}
        if city_name:
            where_clause["cityName"] = {"contains": city_name, "mode": "insensitive"}
        
        # Get itineraries from database
        itineraries = await db.itinerary.find_many(
            where=where_clause,
            order={"createdAt": "desc"},
            take=limit,
            skip=offset,
            include={"city": True}
        )
        
        # Convert to response format
        result = []
        for itinerary in itineraries:
            # Convert timeSlots from JSON to ItineraryTimeSlot objects
            time_slots = [
                ItineraryTimeSlot(**slot) for slot in itinerary.timeSlots
            ]
            
            result.append(ItineraryResponse(
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
                is_active=itinerary.isActive,
                created_at=itinerary.createdAt,
                updated_at=itinerary.updatedAt
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve itineraries: {str(e)}"
        )


@router.get("/itineraries/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get a specific itinerary by ID"""
    
    try:
        # Get itinerary from database
        itinerary = await db.itinerary.find_unique(
            where={"id": itinerary_id},
            include={"city": True}
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
                detail="Access denied"
            )
        
        # Convert timeSlots from JSON to ItineraryTimeSlot objects
        time_slots = [
            ItineraryTimeSlot(**slot) for slot in itinerary.timeSlots
        ]
        
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


@router.delete("/itineraries/{itinerary_id}", response_model=MessageResponse)
async def delete_itinerary(
    itinerary_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete an itinerary (soft delete by marking inactive)"""
    
    try:
        # Get itinerary from database
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
                detail="Access denied"
            )
        
        # Soft delete by marking inactive
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