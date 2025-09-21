from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import secrets

from app.core.database import get_db
from app.core.auth import auth_service
from app.models.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
    MessageResponse
)

router = APIRouter()
security = HTTPBearer()

@router.post("/register", response_model=UserResponse)
async def register_user(request: UserRegisterRequest, db = Depends(get_db)):
    """Register a new user with username/email/password"""
    
    # Check if email already exists
    existing_user = await db.user.find_unique(where={"email": request.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    existing_username = await db.user.find_unique(where={"username": request.username})
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Validate email format
    if not auth_service.is_valid_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )
    
    # Hash password
    hashed_password = auth_service.hash_password(request.password)
    
    # Create new user
    user = await db.user.create(
        data={
            "username": request.username,
            "email": request.email,
            "passwordHash": hashed_password,
            "lastActiveAt": "now()"
        }
    )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        profile_image_url=user.profileImageUrl,
        total_xp=user.totalXP,
        level=user.level,
        streak_days=user.streakDays,
        tokens=user.tokens,
        is_verified=user.isVerified,
        joined_at=user.joinedAt,
        last_active_at=user.lastActiveAt
    )

@router.post("/login", response_model=TokenResponse)
async def login_user(request: UserLoginRequest, db = Depends(get_db)):
    """Authenticate user with email and password"""
    
    # Find user by email
    user = await db.user.find_unique(where={"email": request.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Verify password
    if not auth_service.verify_password(request.password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Update last active time
    user = await db.user.update(
        where={"id": user.id},
        data={"lastActiveAt": "now()"}
    )
    
    # Create access token
    access_token = auth_service.create_access_token(
        data={"sub": user.id, "email": user.email}
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60
    )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db = Depends(get_db)
) -> Optional[dict]:
    """Get current authenticated user"""
    token = credentials.credentials
    payload = auth_service.verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await db.user.find_unique(where={"id": user_id})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current user information"""
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

@router.post("/logout", response_model=MessageResponse)
async def logout(current_user = Depends(get_current_user)):
    """Logout user (client should remove token)"""
    return MessageResponse(message="Successfully logged out")

# Export the dependency for use in other routes
__all__ = ["router", "get_current_user"]