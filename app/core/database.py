from prisma import Prisma
import asyncio
import os
from .config import settings

# Global database instance
db = Prisma()

async def init_db():
    """Initialize database connection"""
    await db.connect()
    print("✅ Database connected successfully")

async def disconnect_db():
    """Disconnect from database"""
    await db.disconnect()
    print("✅ Database disconnected")

async def get_db():
    """Dependency to get database instance"""
    return db