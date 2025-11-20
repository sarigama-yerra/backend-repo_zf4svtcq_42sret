"""
Database Schemas for Exclusive Creator Content Platform

Each Pydantic model corresponds to a MongoDB collection. The collection
name is the lowercase of the class name (e.g., User -> "user").

These schemas are used for validation before inserting into MongoDB via
helper functions in database.py
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import datetime

# Core users
class User(BaseModel):
    name: str = Field(..., description="Display name")
    email: EmailStr = Field(..., description="Email address")
    is_creator: bool = Field(False, description="Whether user is a creator")
    api_key: Optional[str] = Field(None, description="Simple API key for demo auth")
    token_balance: int = Field(0, ge=0, description="Virtual tokens owned by the user")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")
    bio: Optional[str] = Field(None, description="Short bio")

# Creator profile (separate so we can extend without cluttering User)
class CreatorProfile(BaseModel):
    user_id: str = Field(..., description="Owner user id string")
    handle: str = Field(..., min_length=3, max_length=30, description="Unique creator handle")
    headline: Optional[str] = Field(None, description="Tagline shown on profile")
    about: Optional[str] = Field(None, description="About/description")
    categories: List[str] = Field(default_factory=list, description="Non-adult skill categories")

# Subscription tiers set by creators
class SubscriptionTier(BaseModel):
    creator_id: str = Field(..., description="Creator user id")
    name: str = Field(..., description="Tier name")
    description: Optional[str] = Field(None, description="Tier benefits")
    price_monthly: int = Field(..., ge=0, description="Price in cents per month (demo)")
    level: int = Field(1, ge=1, le=10, description="Relative access level (higher = more access)")
    is_active: bool = Field(True, description="Whether tier is available")

# Active subscriptions by audience
class Subscription(BaseModel):
    user_id: str = Field(..., description="Subscriber user id")
    creator_id: str = Field(..., description="Creator user id")
    tier_id: str = Field(..., description="Tier id subscribed to")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(True)

# Media assets uploaded/referenced by posts
class MediaAsset(BaseModel):
    creator_id: str = Field(...)
    url: str = Field(..., description="Where the asset is hosted (demo: direct URL)")
    media_type: Literal["video","image","file","code","text"] = Field(...)
    title: Optional[str] = None
    size_bytes: Optional[int] = None

# Posts (content units)
class Post(BaseModel):
    creator_id: str = Field(...)
    title: str = Field(...)
    body_text: Optional[str] = None
    media_ids: List[str] = Field(default_factory=list)
    access_level_required: int = Field(1, ge=1, le=10, description="Min tier level to view")
    is_draft: bool = Field(False)
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

# Token transactions (tips and purchases)
class TokenTransaction(BaseModel):
    from_user_id: Optional[str] = Field(None, description="Who sent tokens (None for purchase)")
    to_user_id: Optional[str] = Field(None, description="Creator who received tokens")
    amount: int = Field(..., ge=1)
    kind: Literal["purchase","tip"] = Field(...)
    note: Optional[str] = None
    post_id: Optional[str] = None

# Comments on posts (subscribers only)
class Comment(BaseModel):
    post_id: str
    user_id: str
    text: str

# Simple moderation report
class Report(BaseModel):
    target_type: Literal["post","comment","user"]
    target_id: str
    reason: str
    reporter_id: str
    status: Literal["open","reviewing","closed"] = "open"
