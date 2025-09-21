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

# News analysis models
class NewsSourceType(str, Enum):
    RSS = "RSS"
    NEWSAPI = "NEWSAPI"
    WEB_SCRAPE = "WEB_SCRAPE"
    MCP = "MCP"
    LOCAL_NEWS = "LOCAL_NEWS"

class NewsConcernType(str, Enum):
    CRIME = "CRIME"
    VIOLENCE = "VIOLENCE"
    TERRORISM = "TERRORISM"
    TRAFFIC = "TRAFFIC"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    HEALTH = "HEALTH"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    POSITIVE = "POSITIVE"
    UNKNOWN = "UNKNOWN"

class NewsJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class NewsArticleCreate(BaseModel):
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    url: str
    published: Optional[datetime] = None
    source: str
    type: NewsSourceType = NewsSourceType.RSS
    city_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_radius: Optional[float] = None

class NewsArticleResponse(BaseModel):
    id: str
    title: str
    summary: Optional[str]
    content: Optional[str]
    url: str
    published: Optional[datetime]
    source: str
    type: NewsSourceType
    city_id: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_radius: Optional[float]
    safety_score: float
    threat_level: int
    concern_type: NewsConcernType
    sentiment_polarity: float
    sentiment_subjectivity: float
    confidence: float
    is_processed: bool
    is_relevant: bool
    processed_at: Optional[datetime]
    created_at: datetime

class NewsSafetyImpactCreate(BaseModel):
    news_article_id: str
    city_id: str
    impact_factor: float = Field(..., ge=-1.0, le=1.0)
    weight_factor: float = Field(..., ge=0.0, le=2.0)
    latitude: float
    longitude: float
    radius_km: float = Field(..., ge=0.1, le=100.0)
    expires_at: Optional[datetime] = None

class NewsSafetyImpactResponse(BaseModel):
    id: str
    news_article_id: str
    city_id: str
    impact_factor: float
    weight_factor: float
    decay_factor: float
    latitude: float
    longitude: float
    radius_km: float
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime

class NewsScrapingJobCreate(BaseModel):
    city_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = Field(default=50.0, ge=1.0, le=500.0)
    days_back: int = Field(default=7, ge=1, le=30)
    sources: List[str] = Field(default_factory=lambda: ["rss", "newsapi", "local"])

class NewsScrapingJobResponse(BaseModel):
    id: str
    city_id: Optional[str]
    status: NewsJobStatus
    latitude: Optional[float]
    longitude: Optional[float]
    radius_km: float
    days_back: int
    sources: List[str]
    articles_found: int
    articles_processed: int
    safety_relevant: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

class NewsSafetyAnalysis(BaseModel):
    total_articles: int
    relevant_articles: int
    avg_threat_level: float
    sentiment_score: float
    news_safety_factor: float
    confidence: float
    analysis_date: datetime
    top_concerns: List[str]
    recent_incidents: int

# User Relationship models for friends and followers
class RelationshipType(str, Enum):
    FRIEND_REQUEST = "FRIEND_REQUEST"
    FOLLOW = "FOLLOW"

class RelationshipStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"

class FriendRequestCreate(BaseModel):
    to_user_id: str = Field(..., description="ID of the user to send friend request to")

class FollowUserRequest(BaseModel):
    user_id: str = Field(..., description="ID of the user to follow")

class RelationshipResponse(BaseModel):
    id: str
    from_user_id: str
    to_user_id: str
    type: RelationshipType
    status: RelationshipStatus
    created_at: datetime
    updated_at: datetime

class RelationshipWithUserResponse(BaseModel):
    id: str
    type: RelationshipType
    status: RelationshipStatus
    created_at: datetime
    updated_at: datetime
    user: UserResponse  # The other user in the relationship

class FriendRequestResponse(BaseModel):
    id: str
    from_user: UserResponse
    to_user: UserResponse
    status: RelationshipStatus
    created_at: datetime
    updated_at: datetime

class FollowResponse(BaseModel):
    id: str
    follower: UserResponse
    following: UserResponse
    created_at: datetime

class FriendsListResponse(BaseModel):
    friends: List[UserResponse]
    total_count: int

class FollowersListResponse(BaseModel):
    followers: List[UserResponse]
    total_count: int

class FollowingListResponse(BaseModel):
    following: List[UserResponse]
    total_count: int

class PendingRequestsResponse(BaseModel):
    sent_requests: List[FriendRequestResponse]
    received_requests: List[FriendRequestResponse]
    total_sent: int
    total_received: int

class UserRelationshipStats(BaseModel):
    friends_count: int
    followers_count: int
    following_count: int
    pending_requests_count: int