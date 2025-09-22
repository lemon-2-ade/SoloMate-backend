from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Authentication models
class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=6, description="Password")

class UserLoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")

class GoogleAuthRequest(BaseModel):
    token: str = Field(..., description="Google OAuth access token or ID token")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

# User models
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=6)
    profile_image_url: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = None
    profile_image_url: Optional[str] = None
    privacy_settings: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    name: Optional[str] = None
    age: Optional[int] = Field(None, ge=13, le=120, description="Age must be between 13 and 120")
    gender: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    profile_image_url: Optional[str]
    total_xp: int
    level: int
    streak_days: int
    tokens: int
    is_verified: bool
    joined_at: datetime
    last_active_at: datetime
    access_token: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None

# City models
class CityCreate(BaseModel):
    name: str
    country: str
    latitude: float
    longitude: float
    description: Optional[str] = None
    image_url: Optional[str] = None

class CityResponse(BaseModel):
    id: str
    name: str
    country: str
    latitude: float
    longitude: float
    description: Optional[str]
    image_url: Optional[str]
    safety_index: float
    is_active: bool

# Quest models
class QuestType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    HERITAGE = "HERITAGE"
    HIDDEN_GEMS = "HIDDEN_GEMS"
    SAFETY_CHALLENGE = "SAFETY_CHALLENGE"
    COMMUNITY_PICKS = "COMMUNITY_PICKS"

class QuestDifficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    EXTREME = "EXTREME"

class QuestPointCreate(BaseModel):
    name: str
    description: Optional[str] = None
    latitude: float
    longitude: float
    radius: float = 50.0
    order: int
    is_optional: bool = False

class QuestCreate(BaseModel):
    title: str
    description: str
    type: QuestType
    difficulty: QuestDifficulty
    city_id: str
    latitude: float
    longitude: float
    radius: float
    xp_reward: int
    token_reward: int
    required_level: int = 1
    time_limit: Optional[int] = None
    available_from: Optional[datetime] = None
    available_to: Optional[datetime] = None
    max_completions: Optional[int] = None
    requirements: Optional[Dict[str, Any]] = None
    hints: List[str] = []
    partner_info: Optional[Dict[str, Any]] = None
    quest_points: List[QuestPointCreate] = []

class QuestResponse(BaseModel):
    id: str
    title: str
    description: str
    type: QuestType
    difficulty: QuestDifficulty
    city_id: str
    latitude: float
    longitude: float
    radius: float
    xp_reward: int
    token_reward: int
    required_level: int
    current_completions: int
    max_completions: Optional[int]
    is_active: bool
    created_at: datetime

# Location proof models
class LocationProofCreate(BaseModel):
    quest_point_id: Optional[str] = None
    latitude: float
    longitude: float
    accuracy: float
    device_info: Optional[Dict[str, Any]] = None
    photo_url: Optional[str] = None

class LocationProofResponse(BaseModel):
    id: str
    latitude: float
    longitude: float
    accuracy: float
    timestamp: datetime
    is_verified: bool

# Badge models
class BadgeType(str, Enum):
    LANDMARK = "LANDMARK"
    EXPLORER = "EXPLORER"
    NIGHT_OWL = "NIGHT_OWL"
    CULTURE = "CULTURE"
    COMMUNITY = "COMMUNITY"
    LEGEND = "LEGEND"
    STREAK = "STREAK"
    LEVEL = "LEVEL"
    SPECIAL = "SPECIAL"

class BadgeRarity(str, Enum):
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"

class BadgeResponse(BaseModel):
    id: str
    name: str
    description: str
    type: BadgeType
    rarity: BadgeRarity
    image_url: str
    animation_url: Optional[str]
    xp_reward: int
    token_reward: int
    is_soulbound: bool

class UserBadgeResponse(BaseModel):
    id: str
    badge: BadgeResponse
    minted_at: datetime
    token_id: Optional[str]
    transaction_hash: Optional[str]

# Safety models
class SafetyReportType(str, Enum):
    UNSAFE_AREA = "UNSAFE_AREA"
    WELL_LIT = "WELL_LIT"
    POLICE_PRESENCE = "POLICE_PRESENCE"
    CROWDED_AREA = "CROWDED_AREA"
    EMERGENCY_SERVICES = "EMERGENCY_SERVICES"
    UNSAFE_TRANSPORT = "UNSAFE_TRANSPORT"
    SAFE_TRANSPORT = "SAFE_TRANSPORT"
    TOURIST_SCAM = "TOURIST_SCAM"
    PICKPOCKET_RISK = "PICKPOCKET_RISK"
    OTHER = "OTHER"

class SafetyReportCreate(BaseModel):
    city_id: str
    latitude: float
    longitude: float
    type: SafetyReportType
    severity: int = Field(..., ge=1, le=10)
    description: str

class SafetyReportResponse(BaseModel):
    id: str
    city_id: str
    latitude: float
    longitude: float
    type: SafetyReportType
    severity: int
    description: str
    is_verified: bool
    reported_at: datetime

# Leaderboard models
class LeaderboardType(str, Enum):
    XP = "XP"
    BADGES = "BADGES"
    STREAKS = "STREAKS"
    QUESTS_COMPLETED = "QUESTS_COMPLETED"
    SAFETY_SCORE = "SAFETY_SCORE"

class LeaderboardScope(str, Enum):
    GLOBAL = "GLOBAL"
    CITY = "CITY"
    FRIENDS = "FRIENDS"

class LeaderboardPeriod(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    ALL_TIME = "ALL_TIME"

class LeaderboardEntry(BaseModel):
    rank: int
    user: UserResponse
    score: int

class LeaderboardResponse(BaseModel):
    id: str
    name: str
    type: LeaderboardType
    scope: LeaderboardScope
    period: LeaderboardPeriod
    entries: List[LeaderboardEntry]

# Exploration models
class ExplorationCategory(str, Enum):
    FOOD = "FOOD"
    SHOPS = "SHOPS"
    MEDICAL = "MEDICAL"
    TRAVEL = "TRAVEL"
    TOURISM = "TOURISM"
    ENTERTAINMENT = "ENTERTAINMENT"
    SERVICES = "SERVICES"

class NearbyPlace(BaseModel):
    place_id: str
    name: str
    category: ExplorationCategory
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    vicinity: Optional[str] = None
    latitude: float
    longitude: float
    distance_meters: Optional[float] = None
    photo_reference: Optional[str] = None
    is_open_now: Optional[bool] = None
    price_level: Optional[int] = None

class ExplorationResponse(BaseModel):
    category: ExplorationCategory
    places: List[NearbyPlace]
    total_found: int
    search_center: Dict[str, float]
    radius_km: float

# Itinerary models
class ItinerarySource(str, Enum):
    AI = "AI"
    USER = "USER"

class ItineraryTimeSlot(BaseModel):
    start_time: str  # "09:00 AM"
    end_time: str    # "10:30 AM"
    activity_type: str  # "quest", "exploration", "travel", "rest"
    title: str
    description: str
    location: Optional[Dict[str, float]] = None  # {latitude, longitude}
    estimated_duration: str  # "1 hour 30 minutes"
    difficulty: Optional[str] = None
    weather_dependent: bool = False

class DailyItinerary(BaseModel):
    date: str  # "Tuesday, 23 December"
    city: str
    weather: Optional[Dict[str, Any]] = None
    time_slots: List[ItineraryTimeSlot]
    total_estimated_time: str
    safety_notes: List[str] = []

# Database Itinerary models
class ItineraryCreate(BaseModel):
    title: str = Field(..., description="Title for the itinerary")
    date: str = Field(..., description="Date of the itinerary")
    city_name: str = Field(..., description="City name")
    city_id: Optional[str] = Field(None, description="City ID if available")
    
    # For AI-generated itineraries
    time_slots: Optional[List[ItineraryTimeSlot]] = Field(None, description="List of time slots for AI itineraries")
    total_estimated_time: Optional[str] = Field(None, description="Total estimated time for AI itineraries")
    
    # For user-created itineraries
    destination: Optional[str] = Field(None, description="Destination name for user itineraries")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD) for user itineraries")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD) for user itineraries")
    budget_per_day: Optional[int] = Field(None, ge=0, description="Budget per day in local currency")
    travel_style: Optional[str] = Field(None, description="Travel style: Chill&Relax, Culture&Heritage, Adventure&Thrill, Mix of Everything")
    interests: Optional[List[str]] = Field(None, description="User interests/activities")
    accommodation_type: Optional[str] = Field(None, description="Accommodation preference")
    accommodation_budget_per_night: Optional[int] = Field(None, ge=0, description="Accommodation budget per night")
    safety_priority: Optional[str] = Field(None, description="Safety priority: High, Medium, Low")
    special_requests: Optional[str] = Field(None, max_length=1000, description="Special requirements or requests")
    status: Optional[str] = Field("draft", description="Status: draft, planning, confirmed, completed")
    
    # Common fields
    safety_notes: List[str] = Field(default=[], description="Safety notes")
    weather: Optional[Dict[str, Any]] = Field(None, description="Weather information")
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences used")
    ai_context: Optional[Dict[str, Any]] = Field(None, description="AI generation context")
    source: ItinerarySource = Field(ItinerarySource.AI, description="Source of itinerary (AI or USER)")

class ItineraryResponse(BaseModel):
    id: str
    user_id: str
    city_id: Optional[str]
    title: str
    date: str
    city_name: str
    time_slots: List[ItineraryTimeSlot]
    total_estimated_time: str
    safety_notes: List[str]
    weather: Optional[Dict[str, Any]]
    preferences: Optional[Dict[str, Any]]
    ai_context: Optional[Dict[str, Any]]
    quests_generated: int
    source: ItinerarySource
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ItineraryUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    time_slots: Optional[List[ItineraryTimeSlot]] = None
    safety_notes: Optional[List[str]] = None
# Checklist models
class ChecklistItemType(str, Enum):
    ACCOMMODATION = "ACCOMMODATION"
    TRANSPORT = "TRANSPORT" 
    DOCUMENTATION = "DOCUMENTATION"
    PREPARATION = "PREPARATION"
    EXPLORATION = "EXPLORATION"
    SAFETY = "SAFETY"

class ChecklistItem(BaseModel):
    id: str
    type: ChecklistItemType
    title: str
    description: Optional[str] = None
    is_completed: bool = False
    priority: str = "medium"  # low, medium, high
    due_time: Optional[str] = None
    location_dependent: bool = False

class DailyChecklist(BaseModel):
    date: str
    city: str
    items: List[ChecklistItem]
    completion_rate: float  # 0.0 to 1.0

# AI Recommendation models
class AiRecommendationType(str, Enum):
    QUEST = "QUEST"
    CITY = "CITY"
    ROUTE = "ROUTE"
    SAFETY_TIP = "SAFETY_TIP"
    FRIEND_SUGGESTION = "FRIEND_SUGGESTION"
    BADGE_OPPORTUNITY = "BADGE_OPPORTUNITY"
    ITINERARY = "ITINERARY"
    CHECKLIST = "CHECKLIST"

class AiRecommendationResponse(BaseModel):
    id: str
    type: AiRecommendationType
    content: Dict[str, Any]
    reason: str
    confidence: float
    created_at: datetime
    expires_at: Optional[datetime]

# Journal Entry schemas
class JournalEntryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000, description="Journal entry content")
    date: Optional[datetime] = Field(None, description="Entry date (defaults to current time)")
    location: Optional[str] = Field(None, max_length=200, description="Location for this entry")
    mood: Optional[str] = Field(None, max_length=50, description="User's mood")
    tags: Optional[List[str]] = Field(default_factory=list, description="Entry tags")

class JournalEntryResponse(BaseModel):
    id: str
    content: str
    date: datetime
    location: Optional[str] = None
    mood: Optional[str] = None
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime
    user_id: str

class JournalEntriesResponse(BaseModel):
    entries: List[JournalEntryResponse]
    total: int
    has_more: bool

# Generic response models
class MessageResponse(BaseModel):
    message: str
    success: bool = True

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    success: bool = False

# Emergency Contact models
class EmergencyContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Contact name")
    phone_number: str = Field(..., description="Phone number in international format")
    email: Optional[str] = Field(None, description="Contact email address")
    relationship: str = Field(..., min_length=1, max_length=50, description="Relationship to user")
    is_primary: bool = Field(False, description="Mark as primary contact")

class EmergencyContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = None
    email: Optional[str] = None
    relationship: Optional[str] = Field(None, min_length=1, max_length=50)
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None

class EmergencyContactResponse(BaseModel):
    id: str
    user_id: str
    name: str
    phone_number: str
    email: Optional[str]
    relationship: str
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# SOS models
class SosAlertCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes about the emergency")

class SosAlertResponse(BaseModel):
    id: str
    user_id: str
    latitude: float
    longitude: float
    address: Optional[str]
    timestamp: datetime
    contacts_notified: int
    is_resolved: bool
    resolved_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True