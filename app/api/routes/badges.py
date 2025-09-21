from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    BadgeResponse,
    UserBadgeResponse,
    MessageResponse
)

router = APIRouter()

class BadgeService:
    """Service for managing digital badges without blockchain"""
    
    @staticmethod
    def create_badge_metadata(badge_data: dict, user_data: dict, proof_data: dict) -> dict:
        """Create badge metadata"""
        return {
            "name": badge_data["name"],
            "description": badge_data["description"],
            "image": badge_data["image_url"],
            "animation_url": badge_data.get("animation_url"),
            "attributes": [
                {"trait_type": "Badge Type", "value": badge_data["type"]},
                {"trait_type": "Rarity", "value": badge_data["rarity"]},
                {"trait_type": "Earned By", "value": user_data["username"]},
                {"trait_type": "Earned Date", "value": datetime.utcnow().isoformat()},
                {"trait_type": "XP Reward", "value": badge_data["xp_reward"]}
            ],
            "properties": {
                "proof_data": proof_data
            }
        }
    
    @staticmethod
    async def award_badge(user_id: str, badge_id: str, proof_data: dict, db) -> dict:
        """Award a digital badge to a user"""
        try:
            # Check if user already has this badge
            existing_badge = await db.userbadge.find_first(
                where={
                    "userId": user_id,
                    "badgeId": badge_id
                }
            )
            
            if existing_badge:
                return {
                    "success": False,
                    "error": "User already has this badge"
                }
            
            # Get badge details
            badge = await db.badge.find_unique(where={"id": badge_id})
            if not badge:
                return {
                    "success": False,
                    "error": "Badge not found"
                }
            
            # Create user badge record
            user_badge = await db.userbadge.create(
                data={
                    "userId": user_id,
                    "badgeId": badge_id,
                    "metadata": proof_data,
                    "mintedAt": datetime.utcnow()
                }
            )
            
            # Update user XP and tokens
            await db.user.update(
                where={"id": user_id},
                data={
                    "totalXP": {"increment": badge.xpReward},
                    "tokens": {"increment": badge.tokenReward}
                }
            )
            
            return {
                "success": True,
                "badge_id": user_badge.id,
                "xp_earned": badge.xpReward,
                "tokens_earned": badge.tokenReward
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

badge_service = BadgeService()

@router.get("/", response_model=List[BadgeResponse])
async def get_all_badges(
    badge_type: Optional[str] = Query(None, description="Filter by badge type"),
    rarity: Optional[str] = Query(None, description="Filter by rarity"),
    is_active: bool = Query(True, description="Filter active badges"),
    db = Depends(get_db)
):
    """Get all available badges"""
    
    where_clause = {"isActive": is_active}
    
    if badge_type:
        where_clause["type"] = badge_type
    
    if rarity:
        where_clause["rarity"] = rarity
    
    badges = await db.badge.find_many(
        where=where_clause,
        order={"createdAt": "desc"}
    )
    
    return [
        BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            type=badge.type,
            rarity=badge.rarity,
            image_url=badge.imageUrl,
            animation_url=badge.animationUrl,
            xp_reward=badge.xpReward,
            token_reward=badge.tokenReward,
            is_soulbound=False  # No longer blockchain-based
        )
        for badge in badges
    ]

@router.get("/{badge_id}", response_model=Dict[str, Any])
async def get_badge_details(badge_id: str, db = Depends(get_db)):
    """Get detailed badge information"""
    
    badge = await db.badge.find_unique(
        where={"id": badge_id},
        include={"userBadges": {"include": {"user": True}}}
    )
    
    if not badge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found"
        )
    
    # Calculate badge statistics
    total_awarded = len(badge.userBadges)
    unique_holders = len(set(ub.userId for ub in badge.userBadges))
    
    return {
        "badge": BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            type=badge.type,
            rarity=badge.rarity,
            image_url=badge.imageUrl,
            animation_url=badge.animationUrl,
            xp_reward=badge.xpReward,
            token_reward=badge.tokenReward,
            is_soulbound=False
        ),
        "requirements": badge.requirements,
        "statistics": {
            "total_awarded": total_awarded,
            "unique_holders": unique_holders,
            "first_awarded": badge.userBadges[0].mintedAt if badge.userBadges else None,
            "last_awarded": badge.userBadges[-1].mintedAt if badge.userBadges else None
        }
    }

@router.get("/my", response_model=List[UserBadgeResponse])
async def get_user_badges(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current user's badges"""
    
    user_badges = await db.userbadge.find_many(
        where={"userId": current_user.id},
        include={"badge": True},
        order={"mintedAt": "desc"}
    )
    
    return [
        UserBadgeResponse(
            id=ub.id,
            badge=BadgeResponse(
                id=ub.badge.id,
                name=ub.badge.name,
                description=ub.badge.description,
                type=ub.badge.type,
                rarity=ub.badge.rarity,
                image_url=ub.badge.imageUrl,
                animation_url=ub.badge.animationUrl,
                xp_reward=ub.badge.xpReward,
                token_reward=ub.badge.tokenReward,
                is_soulbound=False
            ),
            earned_at=ub.mintedAt,
            metadata=ub.metadata
        )
        for ub in user_badges
    ]

@router.post("/{badge_id}/award", response_model=MessageResponse)
async def award_badge_to_user(
    badge_id: str,
    proof_data: Dict[str, Any],
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Award a badge to the current user"""
    
    # Verify badge exists and is active
    badge = await db.badge.find_unique(where={"id": badge_id})
    if not badge or not badge.isActive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found or inactive"
        )
    
    # Award the badge
    result = await badge_service.award_badge(
        current_user.id, 
        badge_id, 
        proof_data, 
        db
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(
        message=f"Badge '{badge.name}' awarded successfully! "
                f"Earned {result['xp_earned']} XP and {result['tokens_earned']} tokens."
    )

@router.get("/user/{user_id}", response_model=List[UserBadgeResponse])
async def get_user_badges_public(
    user_id: str,
    db = Depends(get_db)
):
    """Get public badges for a specific user"""
    
    # Check if user exists
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get user's badges (only public ones based on privacy settings)
    user_badges = await db.userbadge.find_many(
        where={"userId": user_id},
        include={"badge": True},
        order={"mintedAt": "desc"}
    )
    
    # Filter based on privacy settings
    privacy_settings = user.privacySettings or {}
    hide_badges = privacy_settings.get("hide_badges", False)
    
    if hide_badges:
        return []
    
    return [
        UserBadgeResponse(
            id=ub.id,
            badge=BadgeResponse(
                id=ub.badge.id,
                name=ub.badge.name,
                description=ub.badge.description,
                type=ub.badge.type,
                rarity=ub.badge.rarity,
                image_url=ub.badge.imageUrl,
                animation_url=ub.badge.animationUrl,
                xp_reward=ub.badge.xpReward,
                token_reward=ub.badge.tokenReward,
                is_soulbound=False
            ),
            earned_at=ub.mintedAt,
            metadata=ub.metadata
        )
        for ub in user_badges
    ]

@router.get("/leaderboard", response_model=List[Dict[str, Any]])
async def get_badge_leaderboard(
    badge_type: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    db = Depends(get_db)
):
    """Get badge leaderboard showing users with most badges"""
    
    # Build where clause for badges
    where_clause = {}
    if badge_type:
        where_clause["badge"] = {"type": badge_type}
    
    # Get badge counts per user
    # Note: This is a simplified version - in production you'd use proper aggregation
    user_badges = await db.userbadge.find_many(
        where=where_clause,
        include={"user": True, "badge": True}
    )
    
    # Count badges per user
    user_badge_counts = {}
    for ub in user_badges:
        user_id = ub.userId
        if user_id not in user_badge_counts:
            user_badge_counts[user_id] = {
                "user": ub.user,
                "badge_count": 0,
                "total_xp_from_badges": 0
            }
        user_badge_counts[user_id]["badge_count"] += 1
        user_badge_counts[user_id]["total_xp_from_badges"] += ub.badge.xpReward
    
    # Sort by badge count
    sorted_users = sorted(
        user_badge_counts.values(),
        key=lambda x: x["badge_count"],
        reverse=True
    )[:limit]
    
    # Format response
    leaderboard = []
    for i, entry in enumerate(sorted_users):
        user = entry["user"]
        leaderboard.append({
            "rank": i + 1,
            "user": {
                "id": user.id,
                "username": user.username,
                "profile_image_url": user.profileImageUrl
            },
            "badge_count": entry["badge_count"],
            "total_xp_from_badges": entry["total_xp_from_badges"]
        })
    
    return leaderboard