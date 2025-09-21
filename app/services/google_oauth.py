from typing import Optional, Dict, Any
import httpx
from google.auth.transport import requests
from google.oauth2 import id_token
import secrets
import string

from app.core.config import settings

class GoogleOAuthService:
    """Service for Google OAuth authentication"""
    
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
    
    async def verify_google_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify Google OAuth token and return user info
        Supports both ID tokens and access tokens
        """
        try:
            # First try as ID token
            try:
                user_info = id_token.verify_oauth2_token(
                    token, 
                    requests.Request(), 
                    self.client_id
                )
                
                if user_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                    return None
                    
                return {
                    'id': user_info['sub'],
                    'email': user_info['email'],
                    'name': user_info.get('name', ''),
                    'picture': user_info.get('picture', ''),
                    'email_verified': user_info.get('email_verified', False)
                }
            except ValueError:
                # If ID token verification fails, try as access token
                return await self._verify_access_token(token)
                
        except Exception as e:
            print(f"Google token verification error: {e}")
            return None
    
    async def _verify_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Verify Google access token by calling Google's userinfo API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    return {
                        'id': user_data['id'],
                        'email': user_data['email'],
                        'name': user_data.get('name', ''),
                        'picture': user_data.get('picture', ''),
                        'email_verified': user_data.get('verified_email', False)
                    }
                else:
                    return None
                    
        except Exception as e:
            print(f"Google access token verification error: {e}")
            return None
    
    def generate_username_from_email(self, email: str) -> str:
        """Generate a unique username from email"""
        base_username = email.split('@')[0]
        # Clean username (remove special chars, keep alphanumeric and underscore)
        clean_username = ''.join(c for c in base_username if c.isalnum() or c == '_')
        
        # Add random suffix to ensure uniqueness
        random_suffix = ''.join(secrets.choice(string.digits) for _ in range(4))
        return f"{clean_username}_{random_suffix}"

# Singleton instance
google_oauth_service = GoogleOAuthService()