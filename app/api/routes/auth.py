from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from datetime import datetime
import secrets

from app.core.database import get_db
from app.core.auth import auth_service
from app.services.google_oauth import google_oauth_service
from app.models.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    GoogleAuthRequest,
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
            "authProvider": "email",
            "lastActiveAt": datetime.utcnow()
        }
    )

    # Create access token
    access_token = auth_service.create_access_token(
        data={"sub": user.email, "user_id": user.id}
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
        access_token=access_token,
        is_verified=user.isVerified,
        joined_at=user.joinedAt,
        last_active_at=user.lastActiveAt,
        name=user.name,
        age=user.age,
        gender=user.gender
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
    
    # Check if user is OAuth user (no password)
    if user.authProvider != "email" or not user.passwordHash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please use Google Sign-In for this account"
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
        data={"lastActiveAt": datetime.utcnow()}
    )
    
    # Create access token
    access_token = auth_service.create_access_token(
        data={"sub": user.email, "user_id": user.id}
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
    
    user_id = payload.get("user_id")
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

@router.post("/google", response_model=TokenResponse)
async def google_auth(request: GoogleAuthRequest, db = Depends(get_db)):
    """Authenticate user with Google OAuth"""
    
    # Verify Google token
    google_user_info = await google_oauth_service.verify_google_token(request.token)
    if not google_user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google token"
        )
    
    # Check if user already exists by Google ID
    existing_user = await db.user.find_unique(
        where={"googleId": google_user_info['id']}
    )
    
    if existing_user:
        # Update last active time
        await db.user.update(
            where={"id": existing_user.id},
            data={"lastActiveAt": datetime.utcnow()}
        )
        user = existing_user
    else:
        # Check if user exists by email
        existing_email_user = await db.user.find_unique(
            where={"email": google_user_info['email']}
        )
        
        if existing_email_user:
            # Link Google account to existing user
            user = await db.user.update(
                where={"id": existing_email_user.id},
                data={
                    "googleId": google_user_info['id'],
                    "authProvider": "google",
                    "isVerified": True,  # Google accounts are verified
                    "profileImageUrl": google_user_info.get('picture') or existing_email_user.profileImageUrl,
                    "lastActiveAt": datetime.utcnow()
                }
            )
        else:
            # Create new user
            username = google_oauth_service.generate_username_from_email(google_user_info['email'])
            
            # Ensure username is unique
            base_username = username
            counter = 1
            while await db.user.find_unique(where={"username": username}):
                username = f"{base_username}_{counter}"
                counter += 1
            
            user = await db.user.create(
                data={
                    "username": username,
                    "email": google_user_info['email'],
                    "googleId": google_user_info['id'],
                    "authProvider": "google",
                    "isVerified": True,  # Google accounts are verified
                    "profileImageUrl": google_user_info.get('picture'),
                    "joinedAt": datetime.utcnow(),
                    "lastActiveAt": datetime.utcnow()
                }
            )
    
    # Create JWT token
    access_token = auth_service.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60
    )

# Export the dependency for use in other routes
__all__ = ["router", "get_current_user"]