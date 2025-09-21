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

# AI Recommendation models
class AiRecommendationType(str, Enum):
    QUEST = "QUEST"
    CITY = "CITY"
    ROUTE = "ROUTE"
    SAFETY_TIP = "SAFETY_TIP"
    FRIEND_SUGGESTION = "FRIEND_SUGGESTION"
    BADGE_OPPORTUNITY = "BADGE_OPPORTUNITY"

class AiRecommendationResponse(BaseModel):
    id: str
    type: AiRecommendationType
    content: Dict[str, Any]
    reason: str
    confidence: float
    created_at: datetime
    expires_at: Optional[datetime]

# Generic response models
class MessageResponse(BaseModel):
    message: str
    success: bool = True

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    success: bool = False