from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    UserUpdate,
    UserResponse,
    UserBadgeResponse,
    MessageResponse
)

router = APIRouter()

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user = Depends(get_current_user)):
    """Get current user's profile"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        profile_image_url=current_user.profileImageUrl,
        total_xp=current_user.totalXP,
        level=current_user.level,
        streak_days=current_user.streakDays,
        tokens=current_user.tokens,
        is_verified=current_user.isVerified,
        joined_at=current_user.joinedAt,
        last_active_at=current_user.lastActiveAt
    )

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update current user's profile"""
    
    # Check if username is already taken (if updating username)
    if user_update.username and user_update.username != current_user.username:
        existing_user = await db.user.find_unique(
            where={"username": user_update.username}
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    # Prepare update data
    update_data = {}
    if user_update.username is not None:
        update_data["username"] = user_update.username
    if user_update.email is not None:
        update_data["email"] = user_update.email
    if user_update.profile_image_url is not None:
        update_data["profileImageUrl"] = user_update.profile_image_url
    if user_update.privacy_settings is not None:
        update_data["privacySettings"] = user_update.privacy_settings
    if user_update.preferences is not None:
        update_data["preferences"] = user_update.preferences
    
    # Update user
    updated_user = await db.user.update(
        where={"id": current_user.id},
        data=update_data
    )
    
    return UserResponse(
        id=updated_user.id,
        wallet_address=updated_user.walletAddress,
        username=updated_user.username,
        email=updated_user.email,
        profile_image_url=updated_user.profileImageUrl,
        total_xp=updated_user.totalXP,
        level=updated_user.level,
        streak_days=updated_user.streakDays,
        tokens=updated_user.tokens,
        is_verified=updated_user.isVerified,
        joined_at=updated_user.joinedAt,
        last_active_at=updated_user.lastActiveAt
    )

@router.get("/badges", response_model=List[UserBadgeResponse])
async def get_user_badges(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current user's badges (Digital Passport)"""
    user_badges = await db.userbadge.find_many(
        where={"userId": current_user.id},
        include={"badge": True},
        order={"mintedAt": "desc"}
    )
    
    return [
        UserBadgeResponse(
            id=user_badge.id,
            badge=user_badge.badge,
            minted_at=user_badge.mintedAt,
            token_id=user_badge.tokenId,
            transaction_hash=user_badge.transactionHash
        )
        for user_badge in user_badges
    ]

@router.get("/stats")
async def get_user_stats(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user statistics"""
    
    # Count completed quests
    completed_quests = await db.questprogress.count(
        where={
            "userId": current_user.id,
            "status": "completed"
        }
    )
    
    # Count total badges
    total_badges = await db.userbadge.count(
        where={"userId": current_user.id}
    )
    
    # Count cities visited (quests completed in different cities)
    cities_visited_query = await db.questprogress.find_many(
        where={
            "userId": current_user.id,
            "status": "completed"
        },
        include={"quest": True},
        distinct=["quest.cityId"]
    )
    cities_visited = len(set(qp.quest.cityId for qp in cities_visited_query))
    
    # Count safety reports submitted
    safety_reports = await db.safetyreport.count(
        where={"userId": current_user.id}
    )
    
    return {
        "total_xp": current_user.totalXP,
        "level": current_user.level,
        "streak_days": current_user.streakDays,
        "tokens": current_user.tokens,
        "completed_quests": completed_quests,
        "total_badges": total_badges,
        "cities_visited": cities_visited,
        "safety_reports_submitted": safety_reports,
        "join_date": current_user.joinedAt
    }

@router.post("/add-friend/{friend_wallet_address}", response_model=MessageResponse)
async def add_friend(
    friend_wallet_address: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Add a friend by wallet address"""
    
    # Find friend by wallet address
    friend = await db.user.find_unique(
        where={"walletAddress": friend_wallet_address}
    )
    
    if not friend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if friend.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add yourself as friend"
        )
    
    # Check if already friends
    existing_friendship = await db.user.find_first(
        where={
            "id": current_user.id,
            "friends": {
                "some": {"id": friend.id}
            }
        }
    )
    
    if existing_friendship:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already friends with this user"
        )
    
    # Add friend (bidirectional)
    await db.user.update(
        where={"id": current_user.id},
        data={
            "friends": {
                "connect": {"id": friend.id}
            }
        }
    )
    
    await db.user.update(
        where={"id": friend.id},
        data={
            "friends": {
                "connect": {"id": current_user.id}
            }
        }
    )
    
    return MessageResponse(message=f"Successfully added {friend.username or friend.walletAddress} as friend")

@router.get("/friends", response_model=List[UserResponse])
async def get_friends(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's friends list"""
    user_with_friends = await db.user.find_unique(
        where={"id": current_user.id},
        include={"friends": True}
    )
    
    return [
        UserResponse(
            id=friend.id,
            wallet_address=friend.walletAddress,
            username=friend.username,
            email=friend.email,
            profile_image_url=friend.profileImageUrl,
            total_xp=friend.totalXP,
            level=friend.level,
            streak_days=friend.streakDays,
            tokens=friend.tokens,
            is_verified=friend.isVerified,
            joined_at=friend.joinedAt,
            last_active_at=friend.lastActiveAt
        )
        for friend in user_with_friends.friends
    ]