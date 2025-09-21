from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime, timedelta
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.core.database import get_db

class AgentState(TypedDict):
    user_id: str
    user_profile: Dict[str, Any]
    user_location: Optional[Dict[str, float]]
    quest_history: List[Dict[str, Any]]
    safety_preferences: Dict[str, Any]
    recommendation_type: str
    context: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    reasoning: str

class SoloMateAIAgent:
    """AI Agent for personalized quest and travel recommendations using LangGraph"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.7
        )
        self.memory = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow for AI recommendations"""
        
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("profile_analyzer", self._analyze_user_profile)
        workflow.add_node("quest_analyzer", self._analyze_quest_history)
        workflow.add_node("safety_analyzer", self._analyze_safety_preferences)
        workflow.add_node("location_analyzer", self._analyze_location_context)
        workflow.add_node("recommendation_generator", self._generate_recommendations)
        workflow.add_node("filter_and_rank", self._filter_and_rank_recommendations)
        
        # Define the flow
        workflow.set_entry_point("profile_analyzer")
        
        workflow.add_edge("profile_analyzer", "quest_analyzer")
        workflow.add_edge("quest_analyzer", "safety_analyzer")
        workflow.add_edge("safety_analyzer", "location_analyzer")
        workflow.add_edge("location_analyzer", "recommendation_generator")
        workflow.add_edge("recommendation_generator", "filter_and_rank")
        workflow.add_edge("filter_and_rank", END)
        
        return workflow.compile(checkpointer=self.memory)
    
    async def _analyze_user_profile(self, state: AgentState) -> AgentState:
        """Analyze user profile and preferences"""
        
        profile = state["user_profile"]
        
        # Create user persona analysis
        persona_prompt = f"""
        Analyze this user profile and create a travel persona:
        
        User Stats:
        - Level: {profile.get('level', 1)}
        - Total XP: {profile.get('total_xp', 0)}
        - Streak Days: {profile.get('streak_days', 0)}
        - Completed Quests: {profile.get('completed_quests', 0)}
        - Badges Earned: {profile.get('total_badges', 0)}
        - Cities Visited: {profile.get('cities_visited', 0)}
        
        Preferences: {profile.get('preferences', {})}
        
        Create a concise travel persona (adventure seeker, culture enthusiast, safety-conscious, etc.)
        and identify key motivations and interests.
        
        Respond in JSON format:
        {{
            "persona": "description",
            "interests": ["list", "of", "interests"],
            "experience_level": "beginner|intermediate|expert",
            "risk_tolerance": "low|medium|high",
            "preferred_quest_types": ["list"]
        }}
        """
        
        try:
            response = await self.llm.ainvoke([HumanMessage(content=persona_prompt)])
            persona_data = json.loads(response.content)
            state["context"]["user_persona"] = persona_data
        except Exception as e:
            # Fallback persona analysis
            state["context"]["user_persona"] = {
                "persona": "Explorer",
                "interests": ["sightseeing", "culture"],
                "experience_level": "beginner" if profile.get('level', 1) < 5 else "intermediate",
                "risk_tolerance": "medium",
                "preferred_quest_types": ["HERITAGE", "LANDMARK"]
            }
        
        return state
    
    async def _analyze_quest_history(self, state: AgentState) -> AgentState:
        """Analyze user's quest completion history"""
        
        quest_history = state["quest_history"]
        
        if not quest_history:
            state["context"]["quest_patterns"] = {
                "preferred_types": [],
                "preferred_difficulty": "EASY",
                "completion_rate": 0,
                "favorite_times": [],
                "patterns": []
            }
            return state
        
        # Analyze patterns
        quest_types = [q.get("type") for q in quest_history]
        difficulties = [q.get("difficulty") for q in quest_history]
        completion_times = [q.get("completion_time") for q in quest_history if q.get("completion_time")]
        
        # Count preferences
        type_counts = {}
        for qtype in quest_types:
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
        
        difficulty_counts = {}
        for diff in difficulties:
            difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1
        
        # Find preferred types and difficulty
        preferred_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)[:3]
        preferred_difficulty = max(difficulty_counts.keys(), key=lambda x: difficulty_counts[x]) if difficulty_counts else "EASY"
        
        state["context"]["quest_patterns"] = {
            "preferred_types": preferred_types,
            "preferred_difficulty": preferred_difficulty,
            "completion_rate": len([q for q in quest_history if q.get("completed")]) / len(quest_history),
            "total_completed": len(quest_history),
            "patterns": [
                f"Prefers {preferred_types[0]} quests" if preferred_types else "No clear preference",
                f"Usually completes {preferred_difficulty} difficulty",
                f"Has {len(quest_history)} completed quests"
            ]
        }
        
        return state
    
    async def _analyze_safety_preferences(self, state: AgentState) -> AgentState:
        """Analyze user's safety preferences and risk tolerance"""
        
        safety_prefs = state["safety_preferences"]
        persona = state["context"]["user_persona"]
        
        # Determine safety requirements
        risk_tolerance = persona.get("risk_tolerance", "medium")
        
        safety_requirements = {
            "min_safety_index": 6.0 if risk_tolerance == "low" else 4.0 if risk_tolerance == "medium" else 2.0,
            "avoid_night_quests": risk_tolerance == "low",
            "prefer_crowded_areas": risk_tolerance == "low",
            "require_safety_reports": risk_tolerance == "low",
            "safety_priority": risk_tolerance
        }
        
        # Include user's explicit safety preferences
        if safety_prefs:
            safety_requirements.update(safety_prefs)
        
        state["context"]["safety_requirements"] = safety_requirements
        
        return state
    
    async def _analyze_location_context(self, state: AgentState) -> AgentState:
        """Analyze user's current location and travel context"""
        
        location = state["user_location"]
        
        if not location:
            state["context"]["location_context"] = {
                "has_location": False,
                "nearby_cities": [],
                "travel_suggestions": []
            }
            return state
        
        # Analyze location context
        location_context = {
            "has_location": True,
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "timezone_consideration": True,
            "local_time_hour": datetime.now().hour
        }
        
        state["context"]["location_context"] = location_context
        
        return state
    
    async def _generate_recommendations(self, state: AgentState) -> AgentState:
        """Generate personalized recommendations using LLM"""
        
        recommendation_type = state["recommendation_type"]
        context = state["context"]
        
        if recommendation_type == "QUEST":
            recommendations = await self._generate_quest_recommendations(state)
        elif recommendation_type == "CITY":
            recommendations = await self._generate_city_recommendations(state)
        elif recommendation_type == "ROUTE":
            recommendations = await self._generate_route_recommendations(state)
        elif recommendation_type == "SAFETY_TIP":
            recommendations = await self._generate_safety_recommendations(state)
        elif recommendation_type == "ITINERARY":
            recommendations = await self._generate_itinerary_recommendations(state)
        else:
            recommendations = []
        
        state["recommendations"] = recommendations
        
        return state
    
    async def _generate_quest_recommendations(self, state: AgentState) -> List[Dict[str, Any]]:
        """Generate quest recommendations"""
        
        persona = state["context"]["user_persona"]
        quest_patterns = state["context"]["quest_patterns"]
        safety_req = state["context"]["safety_requirements"]
        
        recommendation_prompt = f"""
        Generate 3-5 personalized quest recommendations for a user with this profile:
        
        User Persona: {persona}
        Quest History Patterns: {quest_patterns}
        Safety Requirements: {safety_req}
        
        Consider:
        - User's preferred quest types: {persona.get('preferred_quest_types', [])}
        - Experience level: {persona.get('experience_level', 'beginner')}
        - Risk tolerance: {persona.get('risk_tolerance', 'medium')}
        - Past completion patterns
        
        Generate recommendations in this JSON format:
        [
            {{
                "title": "Quest Title",
                "description": "Why this quest fits the user",
                "quest_type": "HERITAGE|DAILY|WEEKLY|HIDDEN_GEMS|SAFETY_CHALLENGE|COMMUNITY_PICKS",
                "difficulty": "EASY|MEDIUM|HARD|EXTREME",
                "estimated_duration": "30 minutes",
                "confidence": 0.85,
                "reasoning": "Why this is recommended",
                "tags": ["culture", "beginner-friendly"]
            }}
        ]
        """
        
        try:
            response = await self.llm.ainvoke([HumanMessage(content=recommendation_prompt)])
            recommendations = json.loads(response.content)
            return recommendations
        except Exception as e:
            # Fallback recommendations
            return [
                {
                    "title": "Local Heritage Walk",
                    "description": "Explore historical landmarks at your own pace",
                    "quest_type": "HERITAGE",
                    "difficulty": "EASY",
                    "estimated_duration": "45 minutes",
                    "confidence": 0.7,
                    "reasoning": "Good for beginners and history enthusiasts",
                    "tags": ["culture", "walking", "beginner-friendly"]
                }
            ]
    
    async def _generate_city_recommendations(self, state: AgentState) -> List[Dict[str, Any]]:
        """Generate city/destination recommendations"""
        
        persona = state["context"]["user_persona"]
        location_context = state["context"]["location_context"]
        
        # Mock city recommendations based on persona
        if "culture" in persona.get("interests", []):
            return [
                {
                    "city_name": "Prague",
                    "country": "Czech Republic",
                    "reasoning": "Rich historical heritage matches your cultural interests",
                    "confidence": 0.9,
                    "highlight_features": ["Historic castles", "Art galleries", "Walking tours"],
                    "safety_index": 8.5
                }
            ]
        
        return []
    
    async def _generate_route_recommendations(self, state: AgentState) -> List[Dict[str, Any]]:
        """Generate route recommendations"""
        
        return [
            {
                "route_name": "Cultural District Tour",
                "description": "Optimized route through cultural landmarks",
                "estimated_time": "3 hours",
                "confidence": 0.8,
                "waypoints": ["Museum", "Historic Square", "Art Gallery"],
                "difficulty": "EASY"
            }
        ]
    
    async def _generate_safety_recommendations(self, state: AgentState) -> List[Dict[str, Any]]:
        """Generate safety tips and recommendations"""
        
        location_context = state["context"]["location_context"]
        safety_req = state["context"]["safety_requirements"]
        
        current_hour = location_context.get("local_time_hour", 12)
        
        tips = []
        
        if current_hour >= 20 or current_hour <= 6:
            tips.append({
                "tip": "Travel in well-lit areas during nighttime",
                "category": "NIGHT_SAFETY",
                "importance": "HIGH",
                "confidence": 0.95
            })
        
        if safety_req.get("safety_priority") == "low":
            tips.append({
                "tip": "Stay in crowded tourist areas for maximum safety",
                "category": "GENERAL_SAFETY",
                "importance": "HIGH",
                "confidence": 0.9
            })
        
        return tips
    
    async def _generate_itinerary_recommendations(self, state: AgentState) -> List[Dict[str, Any]]:
        """Generate daily itinerary recommendations"""
        
        persona = state["context"]["user_persona"]
        location_context = state["context"]["location_context"]
        safety_req = state["context"]["safety_requirements"]
        quest_patterns = state["context"]["quest_patterns"]
        
        # Get context for itinerary generation
        user_location = state.get("user_location", {})
        additional_context = state.get("context", {}).get("itinerary_context", {})
        
        itinerary_prompt = f"""
        Generate a personalized daily itinerary for a user with this profile:
        
        User Persona: {persona}
        Location Context: {location_context}
        Safety Requirements: {safety_req}
        Quest Preferences: {quest_patterns}
        
        Additional Context: {additional_context}
        
        Create a balanced daily schedule that includes:
        - Morning activities (9 AM - 12 PM)
        - Afternoon exploration (12 PM - 6 PM) 
        - Evening activities (6 PM - 9 PM)
        
        Consider:
        - User's experience level: {persona.get('experience_level', 'beginner')}
        - Preferred activities: {persona.get('interests', [])}
        - Safety requirements based on risk tolerance: {persona.get('risk_tolerance', 'medium')}
        - Local time and optimal activity timing
        
        Generate itinerary in this JSON format:
        [
            {{
                "start_time": "09:00 AM",
                "end_time": "10:30 AM", 
                "activity_type": "quest",
                "title": "Morning Heritage Walk",
                "description": "Explore historic downtown area with guided audio tour",
                "location": {{"latitude": 0.0, "longitude": 0.0}},
                "estimated_duration": "1 hour 30 minutes",
                "difficulty": "EASY",
                "weather_dependent": false,
                "confidence": 0.85
            }}
        ]
        """
        
        try:
            response = await self.llm.ainvoke([HumanMessage(content=itinerary_prompt)])
            itinerary_items = json.loads(response.content)
            return itinerary_items
        except Exception as e:
            # Fallback itinerary
            return [
                {
                    "start_time": "09:00 AM",
                    "end_time": "10:30 AM",
                    "activity_type": "quest",
                    "title": "Local Walking Tour",
                    "description": "Explore nearby attractions at your own pace",
                    "location": user_location,
                    "estimated_duration": "1 hour 30 minutes",
                    "difficulty": "EASY",
                    "weather_dependent": False,
                    "confidence": 0.7
                },
                {
                    "start_time": "11:00 AM",
                    "end_time": "12:30 PM",
                    "activity_type": "exploration",
                    "title": "Local Food Discovery",
                    "description": "Try authentic local cuisine at recommended spots",
                    "location": user_location,
                    "estimated_duration": "1 hour 30 minutes",
                    "difficulty": "EASY",
                    "weather_dependent": False,
                    "confidence": 0.8
                },
                {
                    "start_time": "02:00 PM",
                    "end_time": "04:00 PM",
                    "activity_type": "quest",
                    "title": "Cultural Heritage Quest",
                    "description": "Visit museums and cultural sites in the area",
                    "location": user_location,
                    "estimated_duration": "2 hours",
                    "difficulty": "MEDIUM",
                    "weather_dependent": False,
                    "confidence": 0.75
                }
            ]

    async def _filter_and_rank_recommendations(self, state: AgentState) -> AgentState:
        """Filter and rank recommendations based on user context"""
        
        recommendations = state["recommendations"]
        context = state["context"]
        
        # Sort by confidence score
        filtered_recommendations = sorted(
            recommendations,
            key=lambda x: x.get("confidence", 0.5),
            reverse=True
        )
        
        # Take top 5
        state["recommendations"] = filtered_recommendations[:5]
        
        # Generate overall reasoning
        reasoning_parts = []
        for rec in state["recommendations"]:
            if "reasoning" in rec:
                reasoning_parts.append(rec["reasoning"])
        
        state["reasoning"] = " ".join(reasoning_parts)
        
        return state

# Singleton instance
ai_agent = SoloMateAIAgent()

async def generate_recommendations(
    user_id: str,
    recommendation_type: str,
    user_location: Optional[Dict[str, float]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate AI recommendations for a user
    
    Args:
        user_id: User ID
        recommendation_type: Type of recommendation (QUEST, CITY, ROUTE, SAFETY_TIP)
        user_location: Optional user location {latitude, longitude}
        context: Additional context for recommendations
        
    Returns:
        Dictionary with recommendations and reasoning
    """
    
    db = await get_db()
    
    # Get user profile
    user = await db.user.find_unique(
        where={"id": user_id},
        include={
            "questProgresses": {
                "include": {"quest": True},
                "where": {"status": "completed"}
            },
            "badges": True
        }
    )
    
    if not user:
        raise ValueError("User not found")
    
    # Prepare user profile data
    user_profile = {
        "level": user.level,
        "total_xp": user.totalXP,
        "streak_days": user.streakDays,
        "completed_quests": len(user.questProgresses),
        "total_badges": len(user.badges),
        "cities_visited": len(set(qp.quest.cityId for qp in user.questProgresses)),
        "preferences": user.preferences or {}
    }
    
    # Prepare quest history
    quest_history = []
    for qp in user.questProgresses:
        quest_history.append({
            "type": qp.quest.type,
            "difficulty": qp.quest.difficulty,
            "completed": qp.status == "completed",
            "completion_time": qp.completedAt,
            "xp_reward": qp.quest.xpReward
        })
    
    # Get safety preferences from user preferences
    safety_preferences = user.preferences.get("safety", {}) if user.preferences else {}
    
    # Create initial state
    initial_state = AgentState(
        user_id=user_id,
        user_profile=user_profile,
        user_location=user_location,
        quest_history=quest_history,
        safety_preferences=safety_preferences,
        recommendation_type=recommendation_type,
        context=context or {},
        recommendations=[],
        reasoning=""
    )
    
    # Run the AI agent workflow
    result = await ai_agent.graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": f"user_{user_id}"}}
    )
    
    return {
        "recommendations": result["recommendations"],
        "reasoning": result["reasoning"],
        "user_persona": result["context"].get("user_persona", {}),
        "confidence": sum(r.get("confidence", 0.5) for r in result["recommendations"]) / len(result["recommendations"]) if result["recommendations"] else 0.5,
        "generated_at": datetime.utcnow().isoformat()
    }