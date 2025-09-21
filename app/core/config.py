from pydantic_settings import BaseSettings
from typing import List, Optional
import os

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL database connection string")
    
    # Authentication - CRITICAL: These must be set in .env file
    SECRET_KEY: str = Field(..., description="Secret key for JWT token signing")
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, description="Token expiration in minutes (24 hours)")
    
    # External APIs - REQUIRED: Set these in .env file
    GOOGLE_MAPS_API_KEY: str = Field(..., description="Google Maps API key")
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key for AI features")
    
    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment (development/production)")
    
    # CORS - Parse from JSON string in .env
    ALLOWED_HOSTS: List[str] = Field(default=["http://localhost:3000", "http://localhost:8080"], description="Allowed CORS origins")
    
    # File uploads
    UPLOAD_FOLDER: str = Field(default="uploads", description="Upload directory")
    MAX_FILE_SIZE: int = Field(default=5242880, description="Max file size in bytes (5MB)")
    
    # Safety index weights
    SAFETY_INDEX_WEIGHT_REPORTS: float = Field(default=0.4, description="Weight for safety reports")
    SAFETY_INDEX_WEIGHT_TIME: float = Field(default=0.3, description="Weight for time decay")
    SAFETY_INDEX_WEIGHT_DENSITY: float = Field(default=0.3, description="Weight for report density")
    
    # Quest configuration
    DEFAULT_QUEST_RADIUS: float = Field(default=100.0, description="Default quest radius in meters")
    MAX_QUEST_RADIUS: float = Field(default=1000.0, description="Maximum quest radius in meters")
    MIN_QUEST_RADIUS: float = Field(default=10.0, description="Minimum quest radius in meters")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        if not self.GOOGLE_MAPS_API_KEY:
            print("WARNING: GOOGLE_MAPS_API_KEY not set - Google Maps features will be disabled")
            
        if not self.OPENAI_API_KEY:
            print("WARNING: OPENAI_API_KEY not set - AI features will be disabled")

settings = Settings()