from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from datetime import datetime, date, timedelta

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntriesResponse,
    MessageResponse
)

router = APIRouter()

@router.post("/entries", response_model=JournalEntryResponse)
async def create_journal_entry(
    entry_data: JournalEntryCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new journal entry"""
    
    # Use provided date or current time
    entry_date = entry_data.date if entry_data.date else datetime.utcnow()
    
    # Validate content length
    if len(entry_data.content.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journal entry content cannot be empty"
        )
    
    # Create journal entry
    try:
        journal_entry = await db.journalentry.create(
            data={
                "userId": current_user.id,
                "content": entry_data.content.strip(),
                "date": entry_date,
                "location": entry_data.location,
                "mood": entry_data.mood,
                "tags": entry_data.tags or []
            }
        )
        
        # Award tokens for journaling activity
        await db.user.update(
            where={"id": current_user.id},
            data={"tokens": {"increment": 3}}  # 3 tokens for journal entry
        )
        
        return JournalEntryResponse(
            id=journal_entry.id,
            content=journal_entry.content,
            date=journal_entry.date,
            location=journal_entry.location,
            mood=journal_entry.mood,
            tags=journal_entry.tags,
            created_at=journal_entry.createdAt,
            updated_at=journal_entry.updatedAt,
            user_id=journal_entry.userId
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create journal entry: {str(e)}"
        )

@router.get("/entries", response_model=JournalEntriesResponse)
async def get_journal_entries(
    limit: int = Query(20, ge=1, le=100, description="Number of entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    date: Optional[date] = Query(None, description="Filter by specific date (YYYY-MM-DD)"),
    start_date: Optional[date] = Query(None, description="Filter from this date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter until this date (YYYY-MM-DD)"),
    location: Optional[str] = Query(None, description="Filter by location"),
    mood: Optional[str] = Query(None, description="Filter by mood"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's journal entries with filtering options"""
    
    try:
        # Build where clause
        where_clause = {"userId": current_user.id}
        
        # Date filtering
        if date:
            # Filter by specific date
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = datetime.combine(date, datetime.max.time())
            where_clause["date"] = {
                "gte": start_of_day,
                "lte": end_of_day
            }
        elif start_date or end_date:
            # Filter by date range
            date_filter = {}
            if start_date:
                date_filter["gte"] = datetime.combine(start_date, datetime.min.time())
            if end_date:
                date_filter["lte"] = datetime.combine(end_date, datetime.max.time())
            where_clause["date"] = date_filter
        
        # Location filtering
        if location:
            where_clause["location"] = {"contains": location, "mode": "insensitive"}
        
        # Mood filtering
        if mood:
            where_clause["mood"] = {"contains": mood, "mode": "insensitive"}
        
        # Tags filtering
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
            if tag_list:
                where_clause["tags"] = {"hasSome": tag_list}
        
        # Get total count
        total_count = await db.journalentry.count(where=where_clause)
        
        # Get entries
        entries = await db.journalentry.find_many(
            where=where_clause,
            skip=offset,
            take=limit,
            order={"date": "desc"}
        )
        
        # Convert to response format
        entry_responses = [
            JournalEntryResponse(
                id=entry.id,
                content=entry.content,
                date=entry.date,
                location=entry.location,
                mood=entry.mood,
                tags=entry.tags,
                created_at=entry.createdAt,
                updated_at=entry.updatedAt,
                user_id=entry.userId
            )
            for entry in entries
        ]
        
        has_more = (offset + len(entries)) < total_count
        
        return JournalEntriesResponse(
            entries=entry_responses,
            total=total_count,
            has_more=has_more
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve journal entries: {str(e)}"
        )

@router.get("/entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get a specific journal entry by ID"""
    
    try:
        entry = await db.journalentry.find_unique(
            where={"id": entry_id}
        )
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Journal entry not found"
            )
        
        # Check if user owns this entry
        if entry.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return JournalEntryResponse(
            id=entry.id,
            content=entry.content,
            date=entry.date,
            location=entry.location,
            mood=entry.mood,
            tags=entry.tags,
            created_at=entry.createdAt,
            updated_at=entry.updatedAt,
            user_id=entry.userId
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve journal entry: {str(e)}"
        )

@router.put("/entries/{entry_id}", response_model=JournalEntryResponse)
async def update_journal_entry(
    entry_id: str,
    entry_data: JournalEntryCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update a specific journal entry"""
    
    try:
        # Check if entry exists and user owns it
        existing_entry = await db.journalentry.find_unique(
            where={"id": entry_id}
        )
        
        if not existing_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Journal entry not found"
            )
        
        if existing_entry.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Validate content
        if len(entry_data.content.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Journal entry content cannot be empty"
            )
        
        # Update entry
        updated_entry = await db.journalentry.update(
            where={"id": entry_id},
            data={
                "content": entry_data.content.strip(),
                "date": entry_data.date if entry_data.date else existing_entry.date,
                "location": entry_data.location,
                "mood": entry_data.mood,
                "tags": entry_data.tags or []
            }
        )
        
        return JournalEntryResponse(
            id=updated_entry.id,
            content=updated_entry.content,
            date=updated_entry.date,
            location=updated_entry.location,
            mood=updated_entry.mood,
            tags=updated_entry.tags,
            created_at=updated_entry.createdAt,
            updated_at=updated_entry.updatedAt,
            user_id=updated_entry.userId
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update journal entry: {str(e)}"
        )

@router.delete("/entries/{entry_id}", response_model=MessageResponse)
async def delete_journal_entry(
    entry_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete a specific journal entry"""
    
    try:
        # Check if entry exists and user owns it
        entry = await db.journalentry.find_unique(
            where={"id": entry_id}
        )
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Journal entry not found"
            )
        
        if entry.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Delete the entry
        await db.journalentry.delete(
            where={"id": entry_id}
        )
        
        return MessageResponse(
            message="Journal entry deleted successfully",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete journal entry: {str(e)}"
        )

@router.get("/stats")
async def get_journal_stats(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get user's journal statistics"""
    
    try:
        # Total entries
        total_entries = await db.journalentry.count(
            where={"userId": current_user.id}
        )
        
        # Entries this month
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        entries_this_month = await db.journalentry.count(
            where={
                "userId": current_user.id,
                "createdAt": {"gte": start_of_month}
            }
        )
        
        # Most used tags
        all_entries = await db.journalentry.find_many(
            where={"userId": current_user.id},
            select={"tags": True}
        )
        
        tag_counts = {}
        for entry in all_entries:
            for tag in entry.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        most_used_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Longest streak (simplified calculation)
        recent_entries = await db.journalentry.find_many(
            where={"userId": current_user.id},
            order={"createdAt": "desc"},
            take=30
        )
        
        # Calculate current streak
        current_streak = 0
        if recent_entries:
            current_date = datetime.utcnow().date()
            for entry in recent_entries:
                entry_date = entry.createdAt.date()
                if entry_date == current_date or entry_date == (current_date - timedelta(days=current_streak)):
                    current_streak += 1
                    current_date = entry_date - timedelta(days=1)
                else:
                    break
        
        return {
            "total_entries": total_entries,
            "entries_this_month": entries_this_month,
            "current_streak": current_streak,
            "most_used_tags": [{"tag": tag, "count": count} for tag, count in most_used_tags],
            "first_entry_date": recent_entries[-1].createdAt if recent_entries else None,
            "last_entry_date": recent_entries[0].createdAt if recent_entries else None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve journal statistics: {str(e)}"
        )

@router.get("/search")
async def search_journal_entries(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Search journal entries by content"""
    
    try:
        # Search in content, location, mood, and tags
        where_clause = {
            "userId": current_user.id,
            "OR": [
                {"content": {"contains": query, "mode": "insensitive"}},
                {"location": {"contains": query, "mode": "insensitive"}},
                {"mood": {"contains": query, "mode": "insensitive"}},
                {"tags": {"has": query}}
            ]
        }
        
        # Get total count
        total_count = await db.journalentry.count(where=where_clause)
        
        # Get entries
        entries = await db.journalentry.find_many(
            where=where_clause,
            skip=offset,
            take=limit,
            order={"date": "desc"}
        )
        
        entry_responses = [
            JournalEntryResponse(
                id=entry.id,
                content=entry.content,
                date=entry.date,
                location=entry.location,
                mood=entry.mood,
                tags=entry.tags,
                created_at=entry.createdAt,
                updated_at=entry.updatedAt,
                user_id=entry.userId
            )
            for entry in entries
        ]
        
        has_more = (offset + len(entries)) < total_count
        
        return {
            "query": query,
            "entries": entry_responses,
            "total": total_count,
            "has_more": has_more
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search journal entries: {str(e)}"
        )
        
