from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    LeaderboardResponse,
    LeaderboardType,
    LeaderboardScope,
    LeaderboardPeriod,
    UserResponse,
    MessageResponse
)

router = APIRouter()

class LeaderboardService:
    """Service for managing and calculating leaderboards"""
    
    @staticmethod
    def hash_user_id(user_id: str) -> str:
        """Hash user ID for privacy in public leaderboards"""
        return hashlib.sha256(user_id.encode()).hexdigest()[:12]
    
    @staticmethod
    def get_period_start(period: LeaderboardPeriod) -> datetime:
        """Get the start date for a leaderboard period"""
        now = datetime.utcnow()
        
        if period == LeaderboardPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == LeaderboardPeriod.WEEKLY:
            # Start of current week (Monday)
            days_since_monday = now.weekday()
            return (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == LeaderboardPeriod.MONTHLY:
            # Start of current month
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # ALL_TIME
            return datetime.min
    
    @staticmethod
    async def calculate_xp_leaderboard(
        db, scope: LeaderboardScope, period: LeaderboardPeriod,
        city_id: Optional[str] = None, user_friends: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Calculate XP-based leaderboard"""
        
        period_start = LeaderboardService.get_period_start(period)
        
        # Base query filters
        where_filters = {}
        if period != LeaderboardPeriod.ALL_TIME:
            where_filters["lastActiveAt"] = {"gte": period_start}
        
        if scope == LeaderboardScope.FRIENDS and user_friends:
            where_filters["id"] = {"in": user_friends}
        
        # For city scope, we need users who have activity in that city
        if scope == LeaderboardScope.CITY and city_id:
            where_filters["questProgresses"] = {
                "some": {
                    "status": "completed",
                    "quest": {"cityId": city_id}
                }
            }
            
            if period != LeaderboardPeriod.ALL_TIME:
                where_filters["questProgresses"]["some"]["completedAt"] = {"gte": period_start}
        
        # Get users with their XP
        users = await db.user.find_many(
            where=where_filters,
            order={"totalXP": "desc"},
            take=100,  # Top 100
            include={"questProgresses": {"include": {"quest": True}}}
        )
        
        # Calculate period-specific XP if needed
        leaderboard = []
        for user in users:
            if period == LeaderboardPeriod.ALL_TIME:
                score = user.totalXP
            else:
                # Calculate XP earned in the period
                period_xp = 0
                for qp in user.questProgresses:
                    if (qp.status == "completed" and qp.completedAt and 
                        qp.completedAt >= period_start):
                        if scope == LeaderboardScope.CITY and city_id:
                            if qp.quest.cityId == city_id:
                                period_xp += qp.quest.xpReward
                        else:
                            period_xp += qp.quest.xpReward
                score = period_xp
            
            if score > 0:  # Only include users with points in this period
                leaderboard.append({
                    "user": user,
                    "score": score
                })
        
        # Sort by score and assign ranks
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        
        return leaderboard
    
    @staticmethod
    async def calculate_badge_leaderboard(
        db, scope: LeaderboardScope, period: LeaderboardPeriod,
        city_id: Optional[str] = None, user_friends: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Calculate badge-based leaderboard"""
        
        period_start = LeaderboardService.get_period_start(period)
        
        # Build where clause for badges
        badge_where = {}
        if period != LeaderboardPeriod.ALL_TIME:
            badge_where["mintedAt"] = {"gte": period_start}
        
        if scope == LeaderboardScope.FRIENDS and user_friends:
            badge_where["userId"] = {"in": user_friends}
        
        if scope == LeaderboardScope.CITY and city_id:
            badge_where["badge"] = {
                "questRewards": {
                    "some": {"cityId": city_id}
                }
            }
        
        # Get badge counts per user
        users_with_badges = await db.userbadge.group_by(
            by=["userId"],
            where=badge_where,
            _count={"userId": True}
        )
        
        # Get user details
        leaderboard = []
        for entry in users_with_badges:
            user = await db.user.find_unique(where={"id": entry.userId})
            if user:
                leaderboard.append({
                    "user": user,
                    "score": entry._count.userId,
                    "rank": 0  # Will be set below
                })
        
        # Sort and assign ranks
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        
        return leaderboard
    
    @staticmethod
    async def calculate_quest_leaderboard(
        db, scope: LeaderboardScope, period: LeaderboardPeriod,
        city_id: Optional[str] = None, user_friends: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Calculate quest completion leaderboard"""
        
        period_start = LeaderboardService.get_period_start(period)
        
        # Build where clause
        quest_where = {"status": "completed"}
        if period != LeaderboardPeriod.ALL_TIME:
            quest_where["completedAt"] = {"gte": period_start}
        
        if scope == LeaderboardScope.FRIENDS and user_friends:
            quest_where["userId"] = {"in": user_friends}
        
        if scope == LeaderboardScope.CITY and city_id:
            quest_where["quest"] = {"cityId": city_id}
        
        # Get quest completion counts
        users_with_quests = await db.questprogress.group_by(
            by=["userId"],
            where=quest_where,
            _count={"userId": True}
        )
        
        # Get user details
        leaderboard = []
        for entry in users_with_quests:
            user = await db.user.find_unique(where={"id": entry.userId})
            if user:
                leaderboard.append({
                    "user": user,
                    "score": entry._count.userId,
                    "rank": 0
                })
        
        # Sort and assign ranks
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        
        return leaderboard
    
    @staticmethod
    async def calculate_streak_leaderboard(
        db, scope: LeaderboardScope, period: LeaderboardPeriod,
        city_id: Optional[str] = None, user_friends: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Calculate streak-based leaderboard"""
        
        # Build where clause
        where_filters = {}
        if scope == LeaderboardScope.FRIENDS and user_friends:
            where_filters["id"] = {"in": user_friends}
        
        # For city scope, only users active in that city
        if scope == LeaderboardScope.CITY and city_id:
            where_filters["questProgresses"] = {
                "some": {
                    "status": "completed",
                    "quest": {"cityId": city_id}
                }
            }
        
        # Get users ordered by streak
        users = await db.user.find_many(
            where=where_filters,
            order={"streakDays": "desc"},
            take=100
        )
        
        leaderboard = []
        for i, user in enumerate(users):
            if user.streakDays > 0:  # Only include users with active streaks
                leaderboard.append({
                    "user": user,
                    "score": user.streakDays,
                    "rank": i + 1
                })
        
        return leaderboard

leaderboard_service = LeaderboardService()

@router.get("/", response_model=List[Dict[str, Any]])
async def get_leaderboards(
    leaderboard_type: LeaderboardType = Query(LeaderboardType.XP),
    scope: LeaderboardScope = Query(LeaderboardScope.GLOBAL),
    period: LeaderboardPeriod = Query(LeaderboardPeriod.ALL_TIME),
    city_id: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get leaderboard with specified filters"""
    
    # Get user's friends list for friends-only leaderboard
    user_friends = []
    if scope == LeaderboardScope.FRIENDS:
        user_with_friends = await db.user.find_unique(
            where={"id": current_user.id},
            include={"friends": True}
        )
        user_friends = [friend.id for friend in user_with_friends.friends] + [current_user.id]
    
    # Calculate leaderboard based on type
    if leaderboard_type == LeaderboardType.XP:
        leaderboard_data = await leaderboard_service.calculate_xp_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.BADGES:
        leaderboard_data = await leaderboard_service.calculate_badge_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.QUESTS_COMPLETED:
        leaderboard_data = await leaderboard_service.calculate_quest_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.STREAKS:
        leaderboard_data = await leaderboard_service.calculate_streak_leaderboard(
            db, scope, period, city_id, user_friends
        )
    else:
        leaderboard_data = []
    
    # Limit results
    leaderboard_data = leaderboard_data[:limit]
    
    # Format response with privacy considerations
    entries = []
    for entry in leaderboard_data:
        user = entry["user"]
        
        # Check privacy settings for non-friends
        show_full_info = (
            user.id == current_user.id or  # Own data
            scope == LeaderboardScope.FRIENDS or  # Friends leaderboard
            user.id in user_friends  # Is a friend
        )
        
        if show_full_info:
            user_info = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "profile_image_url": user.profileImageUrl,
                "level": user.level
            }
        else:
            # Privacy-protected info for strangers
            privacy_settings = user.privacySettings or {}
            hide_info = privacy_settings.get("hide_from_public_leaderboards", False)
            
            if hide_info and scope == LeaderboardScope.GLOBAL:
                continue  # Skip this user entirely
            
            user_info = {
                "id": leaderboard_service.hash_user_id(user.id),
                "username": f"Anonymous {leaderboard_service.hash_user_id(user.id)[:6]}",
                "email": f"user{leaderboard_service.hash_user_id(user.id)[:6]}@hidden.com",
                "profile_image_url": None,
                "level": user.level
            }
        
        entries.append({
            "rank": entry["rank"],
            "user": user_info,
            "score": entry["score"],
            "is_current_user": user.id == current_user.id
        })
    
    # Get user's position in leaderboard if not visible
    current_user_position = None
    if not any(entry["is_current_user"] for entry in entries):
        # Find current user's position in the full leaderboard
        for i, entry in enumerate(leaderboard_data):
            if entry["user"].id == current_user.id:
                current_user_position = {
                    "rank": entry["rank"],
                    "score": entry["score"]
                }
                break
    
    return {
        "leaderboard_type": leaderboard_type,
        "scope": scope,
        "period": period,
        "city_id": city_id,
        "total_entries": len(entries),
        "entries": entries,
        "current_user_position": current_user_position,
        "last_updated": datetime.utcnow().isoformat()
    }

@router.get("/user/{user_id}/position")
async def get_user_leaderboard_position(
    user_id: str,
    leaderboard_type: LeaderboardType = Query(LeaderboardType.XP),
    scope: LeaderboardScope = Query(LeaderboardScope.GLOBAL),
    period: LeaderboardPeriod = Query(LeaderboardPeriod.ALL_TIME),
    city_id: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get a specific user's position in the leaderboard"""
    
    # Check if requesting user has permission to view this data
    if user_id != current_user.id:
        target_user = await db.user.find_unique(where={"id": user_id})
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if users are friends
        friendship = await db.user.find_first(
            where={
                "id": current_user.id,
                "friends": {"some": {"id": user_id}}
            }
        )
        
        if not friendship:
            privacy_settings = target_user.privacySettings or {}
            if privacy_settings.get("hide_leaderboard_position", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User's leaderboard position is private"
                )
    
    # Get user's friends for friends leaderboard
    user_friends = []
    if scope == LeaderboardScope.FRIENDS:
        user_with_friends = await db.user.find_unique(
            where={"id": user_id},
            include={"friends": True}
        )
        user_friends = [friend.id for friend in user_with_friends.friends] + [user_id]
    
    # Calculate full leaderboard
    if leaderboard_type == LeaderboardType.XP:
        leaderboard_data = await leaderboard_service.calculate_xp_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.BADGES:
        leaderboard_data = await leaderboard_service.calculate_badge_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.QUESTS_COMPLETED:
        leaderboard_data = await leaderboard_service.calculate_quest_leaderboard(
            db, scope, period, city_id, user_friends
        )
    elif leaderboard_type == LeaderboardType.STREAKS:
        leaderboard_data = await leaderboard_service.calculate_streak_leaderboard(
            db, scope, period, city_id, user_friends
        )
    else:
        leaderboard_data = []
    
    # Find user's position
    user_position = None
    for entry in leaderboard_data:
        if entry["user"].id == user_id:
            user_position = {
                "rank": entry["rank"],
                "score": entry["score"],
                "total_participants": len(leaderboard_data)
            }
            break
    
    if not user_position:
        user_position = {
            "rank": None,
            "score": 0,
            "total_participants": len(leaderboard_data),
            "message": "User not ranked in this leaderboard"
        }
    
    return user_position

@router.get("/summary")
async def get_leaderboard_summary(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get summary of user's positions across different leaderboards"""
    
    user_id = current_user.id
    
    # Calculate positions across different leaderboards
    positions = {}
    
    # Global XP leaderboard
    xp_leaderboard = await leaderboard_service.calculate_xp_leaderboard(
        db, LeaderboardScope.GLOBAL, LeaderboardPeriod.ALL_TIME
    )
    
    for entry in xp_leaderboard:
        if entry["user"].id == user_id:
            positions["global_xp"] = {
                "rank": entry["rank"],
                "score": entry["score"],
                "total": len(xp_leaderboard)
            }
            break
    
    # Global badge leaderboard
    badge_leaderboard = await leaderboard_service.calculate_badge_leaderboard(
        db, LeaderboardScope.GLOBAL, LeaderboardPeriod.ALL_TIME
    )
    
    for entry in badge_leaderboard:
        if entry["user"].id == user_id:
            positions["global_badges"] = {
                "rank": entry["rank"],
                "score": entry["score"],
                "total": len(badge_leaderboard)
            }
            break
    
    # Weekly XP leaderboard
    weekly_xp = await leaderboard_service.calculate_xp_leaderboard(
        db, LeaderboardScope.GLOBAL, LeaderboardPeriod.WEEKLY
    )
    
    for entry in weekly_xp:
        if entry["user"].id == user_id:
            positions["weekly_xp"] = {
                "rank": entry["rank"],
                "score": entry["score"],
                "total": len(weekly_xp)
            }
            break
    
    # Streak leaderboard
    streak_leaderboard = await leaderboard_service.calculate_streak_leaderboard(
        db, LeaderboardScope.GLOBAL, LeaderboardPeriod.ALL_TIME
    )
    
    for entry in streak_leaderboard:
        if entry["user"].id == user_id:
            positions["global_streaks"] = {
                "rank": entry["rank"],
                "score": entry["score"],
                "total": len(streak_leaderboard)
            }
            break
    
    # Calculate percentiles
    for key, position in positions.items():
        if position.get("rank") and position.get("total"):
            percentile = 100 - ((position["rank"] - 1) / position["total"] * 100)
            position["percentile"] = round(percentile, 1)
    
    return {
        "user_id": user_id,
        "positions": positions,
        "achievements": {
            "top_10_global": any(pos.get("rank", float('inf')) <= 10 for pos in positions.values()),
            "top_100_global": any(pos.get("rank", float('inf')) <= 100 for pos in positions.values()),
            "top_1_percent": any(pos.get("percentile", 0) >= 99 for pos in positions.values()),
            "top_10_percent": any(pos.get("percentile", 0) >= 90 for pos in positions.values())
        },
        "generated_at": datetime.utcnow().isoformat()
    }

@router.post("/privacy", response_model=MessageResponse)
async def update_leaderboard_privacy(
    privacy_settings: Dict[str, bool],
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update user's leaderboard privacy settings"""
    
    # Get current preferences
    current_preferences = current_user.privacySettings or {}
    
    # Update leaderboard privacy settings
    leaderboard_privacy = {
        "hide_from_public_leaderboards": privacy_settings.get("hide_from_public", False),
        "hide_leaderboard_position": privacy_settings.get("hide_position", False),
        "friends_only_leaderboards": privacy_settings.get("friends_only", False),
        "anonymous_in_global": privacy_settings.get("anonymous_global", False)
    }
    
    current_preferences.update(leaderboard_privacy)
    
    # Update user privacy settings
    await db.user.update(
        where={"id": current_user.id},
        data={"privacySettings": current_preferences}
    )
    
    return MessageResponse(message="Leaderboard privacy settings updated successfully")

@router.get("/competitions")
async def get_active_competitions(
    db = Depends(get_db)
):
    """Get active leaderboard competitions and challenges"""
    
    # Mock competitions for demonstration
    # In a real system, these would be stored in the database
    competitions = [
        {
            "id": "weekly_explorer",
            "name": "Weekly Explorer Challenge",
            "description": "Most quests completed this week",
            "type": "QUESTS_COMPLETED",
            "period": "WEEKLY",
            "prize": "500 tokens + Exclusive Badge",
            "starts_at": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            "ends_at": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7),
            "participants": 156,
            "is_active": True
        },
        {
            "id": "monthly_badges",
            "name": "Badge Collector Monthly",
            "description": "Collect the most unique badges this month",
            "type": "BADGES",
            "period": "MONTHLY",
            "prize": "1000 tokens + Legendary Badge",
            "starts_at": datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            "ends_at": (datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1) - timedelta(seconds=1),
            "participants": 89,
            "is_active": True
        }
    ]
    
    return {
        "active_competitions": competitions,
        "total_active": len(competitions)
    }