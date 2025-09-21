from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    UserUpdate,
    UserResponse,
    UserBadgeResponse,
    MessageResponse,
    FriendRequestCreate,
    FollowUserRequest,
    RelationshipResponse,
    FriendRequestResponse,
    FollowResponse,
    FriendsListResponse,
    FollowersListResponse,
    FollowingListResponse,
    PendingRequestsResponse,
    UserRelationshipStats,
    RelationshipType,
    RelationshipStatus
)

router = APIRouter()

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user = Depends(get_current_user)):
    """Get current user's profile"""
    return UserResponse(
        id=current_user.id,
        wallet_address=current_user.walletAddress,
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

# ============================================================================
# FRIENDSHIP AND RELATIONSHIP ENDPOINTS
# ============================================================================

@router.post("/send-friend-request", response_model=MessageResponse)
async def send_friend_request(
    request: FriendRequestCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Send a friend request to another user"""
    
    # Find target user
    target_user = await db.user.find_unique(
        where={"id": request.to_user_id}
    )
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send friend request to yourself"
        )
    
    # Check if relationship already exists
    existing_relationship = await db.userrelationship.find_first(
        where={
            "fromUserId": current_user.id,
            "toUserId": target_user.id,
            "type": RelationshipType.FRIEND_REQUEST
        }
    )
    
    if existing_relationship:
        if existing_relationship.status == RelationshipStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Friend request already sent"
            )
        elif existing_relationship.status == RelationshipStatus.ACCEPTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already friends with this user"
            )
        elif existing_relationship.status == RelationshipStatus.BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot send friend request to this user"
            )
    
    # Check if they already sent us a friend request (auto-accept)
    reverse_request = await db.userrelationship.find_first(
        where={
            "fromUserId": target_user.id,
            "toUserId": current_user.id,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.PENDING
        }
    )
    
    if reverse_request:
        # Auto-accept their request and create mutual friendship
        await db.userrelationship.update(
            where={"id": reverse_request.id},
            data={"status": RelationshipStatus.ACCEPTED}
        )
        
        await db.userrelationship.create(
            data={
                "fromUserId": current_user.id,
                "toUserId": target_user.id,
                "type": RelationshipType.FRIEND_REQUEST,
                "status": RelationshipStatus.ACCEPTED
            }
        )
        
        return MessageResponse(message=f"You are now friends with {target_user.username}")
    
    # Create new friend request
    await db.userrelationship.create(
        data={
            "fromUserId": current_user.id,
            "toUserId": target_user.id,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.PENDING
        }
    )
    
    return MessageResponse(message=f"Friend request sent to {target_user.username}")

@router.post("/accept-friend-request/{request_id}", response_model=MessageResponse)
async def accept_friend_request(
    request_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Accept a friend request"""
    
    # Find the friend request
    friend_request = await db.userrelationship.find_unique(
        where={"id": request_id},
        include={"fromUser": True}
    )
    
    if not friend_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend request not found"
        )
    
    if friend_request.toUserId != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to accept this friend request"
        )
    
    if friend_request.type != RelationshipType.FRIEND_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a friend request"
        )
    
    if friend_request.status != RelationshipStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Friend request is no longer pending"
        )
    
    # Update the request status
    await db.userrelationship.update(
        where={"id": request_id},
        data={"status": RelationshipStatus.ACCEPTED}
    )
    
    # Create reciprocal friendship
    await db.userrelationship.create(
        data={
            "fromUserId": current_user.id,
            "toUserId": friend_request.fromUserId,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    return MessageResponse(message=f"You are now friends with {friend_request.fromUser.username}")

@router.post("/reject-friend-request/{request_id}", response_model=MessageResponse)
async def reject_friend_request(
    request_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Reject a friend request"""
    
    # Find the friend request
    friend_request = await db.userrelationship.find_unique(
        where={"id": request_id},
        include={"fromUser": True}
    )
    
    if not friend_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend request not found"
        )
    
    if friend_request.toUserId != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to reject this friend request"
        )
    
    if friend_request.status != RelationshipStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Friend request is no longer pending"
        )
    
    # Update the request status
    await db.userrelationship.update(
        where={"id": request_id},
        data={"status": RelationshipStatus.REJECTED}
    )
    
    return MessageResponse(message=f"Friend request from {friend_request.fromUser.username} rejected")

@router.post("/follow", response_model=MessageResponse)
async def follow_user(
    request: FollowUserRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Follow another user"""
    
    # Find target user
    target_user = await db.user.find_unique(
        where={"id": request.user_id}
    )
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself"
        )
    
    # Check if already following
    existing_follow = await db.userrelationship.find_first(
        where={
            "fromUserId": current_user.id,
            "toUserId": target_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    if existing_follow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following this user"
        )
    
    # Create follow relationship
    await db.userrelationship.upsert(
        where={
            "fromUserId_toUserId_type": {
                "fromUserId": current_user.id,
                "toUserId": target_user.id,
                "type": RelationshipType.FOLLOW
            }
        },
        create={
            "fromUserId": current_user.id,
            "toUserId": target_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        },
        update={
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    return MessageResponse(message=f"You are now following {target_user.username}")

@router.delete("/unfollow/{user_id}", response_model=MessageResponse)
async def unfollow_user(
    user_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Unfollow a user"""
    
    # Find target user
    target_user = await db.user.find_unique(
        where={"id": user_id}
    )
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Find and delete follow relationship
    follow_relationship = await db.userrelationship.find_first(
        where={
            "fromUserId": current_user.id,
            "toUserId": target_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    if not follow_relationship:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not following this user"
        )
    
    await db.userrelationship.delete(
        where={"id": follow_relationship.id}
    )
    
    return MessageResponse(message=f"Unfollowed {target_user.username}")

@router.delete("/remove-friend/{user_id}", response_model=MessageResponse)
async def remove_friend(
    user_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Remove a friend (unfriend)"""
    
    # Find target user
    target_user = await db.user.find_unique(
        where={"id": user_id}
    )
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Find both directions of friendship
    friendships = await db.userrelationship.find_many(
        where={
            "OR": [
                {
                    "fromUserId": current_user.id,
                    "toUserId": target_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                },
                {
                    "fromUserId": target_user.id,
                    "toUserId": current_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                }
            ]
        }
    )
    
    if not friendships:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not friends with this user"
        )
    
    # Delete all friendship relationships
    for friendship in friendships:
        await db.userrelationship.delete(
            where={"id": friendship.id}
        )
    
    return MessageResponse(message=f"Removed {target_user.username} from friends")

@router.get("/friends", response_model=FriendsListResponse)
async def get_friends(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's friends list"""
    
    # Get accepted friend relationships in both directions
    friendships = await db.userrelationship.find_many(
        where={
            "OR": [
                {
                    "fromUserId": current_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                },
                {
                    "toUserId": current_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                }
            ]
        },
        include={
            "fromUser": True,
            "toUser": True
        }
    )
    
    # Extract unique friends
    friends_map = {}
    for relationship in friendships:
        friend = relationship.toUser if relationship.fromUserId == current_user.id else relationship.fromUser
        if friend.id != current_user.id and friend.id not in friends_map:
            friends_map[friend.id] = UserResponse(
                id=friend.id,
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
    
    friends_list = list(friends_map.values())
    
    return FriendsListResponse(
        friends=friends_list,
        total_count=len(friends_list)
    )

@router.get("/followers", response_model=FollowersListResponse)
async def get_followers(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get users following the current user"""
    
    followers_relationships = await db.userrelationship.find_many(
        where={
            "toUserId": current_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        },
        include={"fromUser": True}
    )
    
    followers = [
        UserResponse(
            id=rel.fromUser.id,
            username=rel.fromUser.username,
            email=rel.fromUser.email,
            profile_image_url=rel.fromUser.profileImageUrl,
            total_xp=rel.fromUser.totalXP,
            level=rel.fromUser.level,
            streak_days=rel.fromUser.streakDays,
            tokens=rel.fromUser.tokens,
            is_verified=rel.fromUser.isVerified,
            joined_at=rel.fromUser.joinedAt,
            last_active_at=rel.fromUser.lastActiveAt
        )
        for rel in followers_relationships
    ]
    
    return FollowersListResponse(
        followers=followers,
        total_count=len(followers)
    )

@router.get("/following", response_model=FollowingListResponse)
async def get_following(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get users the current user is following"""
    
    following_relationships = await db.userrelationship.find_many(
        where={
            "fromUserId": current_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        },
        include={"toUser": True}
    )
    
    following = [
        UserResponse(
            id=rel.toUser.id,
            username=rel.toUser.username,
            email=rel.toUser.email,
            profile_image_url=rel.toUser.profileImageUrl,
            total_xp=rel.toUser.totalXP,
            level=rel.toUser.level,
            streak_days=rel.toUser.streakDays,
            tokens=rel.toUser.tokens,
            is_verified=rel.toUser.isVerified,
            joined_at=rel.toUser.joinedAt,
            last_active_at=rel.toUser.lastActiveAt
        )
        for rel in following_relationships
    ]
    
    return FollowingListResponse(
        following=following,
        total_count=len(following)
    )

@router.get("/pending-requests", response_model=PendingRequestsResponse)
async def get_pending_requests(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get pending friend requests (sent and received)"""
    
    # Get sent friend requests
    sent_requests = await db.userrelationship.find_many(
        where={
            "fromUserId": current_user.id,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.PENDING
        },
        include={"toUser": True}
    )
    
    # Get received friend requests
    received_requests = await db.userrelationship.find_many(
        where={
            "toUserId": current_user.id,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.PENDING
        },
        include={"fromUser": True}
    )
    
    sent_requests_response = [
        FriendRequestResponse(
            id=req.id,
            from_user=UserResponse(
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
            ),
            to_user=UserResponse(
                id=req.toUser.id,
                username=req.toUser.username,
                email=req.toUser.email,
                profile_image_url=req.toUser.profileImageUrl,
                total_xp=req.toUser.totalXP,
                level=req.toUser.level,
                streak_days=req.toUser.streakDays,
                tokens=req.toUser.tokens,
                is_verified=req.toUser.isVerified,
                joined_at=req.toUser.joinedAt,
                last_active_at=req.toUser.lastActiveAt
            ),
            status=req.status,
            created_at=req.createdAt,
            updated_at=req.updatedAt
        )
        for req in sent_requests
    ]
    
    received_requests_response = [
        FriendRequestResponse(
            id=req.id,
            from_user=UserResponse(
                id=req.fromUser.id,
                username=req.fromUser.username,
                email=req.fromUser.email,
                profile_image_url=req.fromUser.profileImageUrl,
                total_xp=req.fromUser.totalXP,
                level=req.fromUser.level,
                streak_days=req.fromUser.streakDays,
                tokens=req.fromUser.tokens,
                is_verified=req.fromUser.isVerified,
                joined_at=req.fromUser.joinedAt,
                last_active_at=req.fromUser.lastActiveAt
            ),
            to_user=UserResponse(
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
            ),
            status=req.status,
            created_at=req.createdAt,
            updated_at=req.updatedAt
        )
        for req in received_requests
    ]
    
    return PendingRequestsResponse(
        sent_requests=sent_requests_response,
        received_requests=received_requests_response,
        total_sent=len(sent_requests_response),
        total_received=len(received_requests_response)
    )

@router.get("/relationship-stats", response_model=UserRelationshipStats)
async def get_relationship_stats(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's relationship statistics"""
    
    # Count friends (accepted friend requests in both directions)
    friends_count = await db.userrelationship.count(
        where={
            "OR": [
                {
                    "fromUserId": current_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                },
                {
                    "toUserId": current_user.id,
                    "type": RelationshipType.FRIEND_REQUEST,
                    "status": RelationshipStatus.ACCEPTED
                }
            ]
        }
    )
    # Since friendship is bidirectional, divide by 2
    friends_count = friends_count // 2
    
    # Count followers
    followers_count = await db.userrelationship.count(
        where={
            "toUserId": current_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    # Count following
    following_count = await db.userrelationship.count(
        where={
            "fromUserId": current_user.id,
            "type": RelationshipType.FOLLOW,
            "status": RelationshipStatus.ACCEPTED
        }
    )
    
    # Count pending friend requests received
    pending_requests_count = await db.userrelationship.count(
        where={
            "toUserId": current_user.id,
            "type": RelationshipType.FRIEND_REQUEST,
            "status": RelationshipStatus.PENDING
        }
    )
    
    return UserRelationshipStats(
        friends_count=friends_count,
        followers_count=followers_count,
        following_count=following_count,
        pending_requests_count=pending_requests_count
    )