from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

from app.core.database import init_db
from app.api.routes import auth, users, cities, quests, badges, safety, leaderboards, ai_recommendations
from app.core.config import settings

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    pass

app = FastAPI(
    title="SoloMate Backend API",
    description="Gamified travel exploration platform with blockchain integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(cities.router, prefix="/api/cities", tags=["cities"])
app.include_router(quests.router, prefix="/api/quests", tags=["quests"])
app.include_router(badges.router, prefix="/api/badges", tags=["badges"])
app.include_router(safety.router, prefix="/api/safety", tags=["safety"])
app.include_router(leaderboards.router, prefix="/api/leaderboards", tags=["leaderboards"])
app.include_router(ai_recommendations.router, prefix="/api/ai", tags=["ai-recommendations"])

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and deployment"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "service": "SoloMate Backend API"
        }
    )

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "SoloMate Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)