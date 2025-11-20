import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import (
    User,
    CreatorProfile,
    SubscriptionTier,
    Subscription,
    MediaAsset,
    Post,
    TokenTransaction,
    Comment,
    Report,
)

app = FastAPI(title="Exclusive Creator Content Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Simple demo auth via API key in header ---
class AuthUser(BaseModel):
    user_id: str
    is_creator: bool = False


def get_current_user(x_api_key: Optional[str] = None) -> Optional[AuthUser]:
    # Demo auth: if header is provided, try to find user by api_key
    # In production replace with JWT/auth provider
    if x_api_key is None:
        return None
    user = db["user"].find_one({"api_key": x_api_key}) if db else None
    if not user:
        return None
    return AuthUser(user_id=str(user.get("_id")), is_creator=bool(user.get("is_creator", False)))


@app.get("/")
def read_root():
    return {"message": "Creator Platform API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set" if not os.getenv("DATABASE_URL") else "✅ Set",
        "database_name": "❌ Not Set" if not os.getenv("DATABASE_NAME") else "✅ Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response


# --- User & Creator endpoints ---
@app.post("/api/users", response_model=dict)
def create_user(user: User):
    # Enforce non-adult policy via categories later at content level
    inserted_id = create_document("user", user)
    return {"id": inserted_id}


@app.post("/api/creators/profile", response_model=dict)
def create_creator_profile(profile: CreatorProfile):
    # Ensure the referenced user exists and is creator
    u = db["user"].find_one({"_id": {"$eq": db.client.get_default_database().codec_options.uuid_representation}}) if False else None
    # We skip heavy validation for demo; rely on front-end flow
    inserted_id = create_document("creatorprofile", profile)
    return {"id": inserted_id}


@app.post("/api/creators/tiers", response_model=dict)
def create_tier(tier: SubscriptionTier):
    inserted_id = create_document("subscriptiontier", tier)
    return {"id": inserted_id}


@app.get("/api/creators/{creator_id}/tiers")
def list_tiers(creator_id: str):
    items = get_documents("subscriptiontier", {"creator_id": creator_id})
    return [{**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc.get("_id"))} for doc in items]


# --- Content endpoints ---
@app.post("/api/media", response_model=dict)
def upload_media(asset: MediaAsset):
    # For MVP we only store references (URL). Real uploads would use S3, etc.
    inserted_id = create_document("mediaasset", asset)
    return {"id": inserted_id}


@app.post("/api/posts", response_model=dict)
def create_post(post: Post):
    inserted_id = create_document("post", post)
    return {"id": inserted_id}


@app.get("/api/creators/{creator_id}/posts")
def list_posts(creator_id: str, tier_level: int = 1):
    # Gate by access_level_required
    items = get_documents("post", {"creator_id": creator_id, "is_draft": False, "access_level_required": {"$lte": tier_level}})
    return [{**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc.get("_id"))} for doc in items]


# --- Subscriptions ---
@app.post("/api/subscribe", response_model=dict)
def subscribe(sub: Subscription):
    # Payment is out of scope; assume success for demo
    inserted_id = create_document("subscription", sub)
    return {"id": inserted_id}


@app.get("/api/users/{user_id}/subscriptions")
def list_subscriptions(user_id: str):
    items = get_documents("subscription", {"user_id": user_id, "active": True})
    return [{**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc.get("_id"))} for doc in items]


# --- Tokens ---
class PurchaseTokensRequest(BaseModel):
    user_id: str
    amount: int


@app.post("/api/tokens/purchase")
def purchase_tokens(payload: PurchaseTokensRequest):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    user = db["user"].find_one({"_id": {"$eq": payload.user_id}})
    if not user:
        # Allow creation-lite for demo
        db["user"].insert_one({"_id": payload.user_id, "name": "Guest", "email": "guest@example.com", "token_balance": 0, "is_creator": False})
        user = db["user"].find_one({"_id": {"$eq": payload.user_id}})
    new_balance = int(user.get("token_balance", 0)) + payload.amount
    db["user"].update_one({"_id": user["_id"]}, {"$set": {"token_balance": new_balance}})
    create_document("tokentransaction", TokenTransaction(from_user_id=None, to_user_id=None, amount=payload.amount, kind="purchase"))
    return {"token_balance": new_balance}


class TipRequest(BaseModel):
    from_user_id: str
    to_user_id: str
    amount: int
    post_id: Optional[str] = None


@app.post("/api/tokens/tip")
def tip_creator(payload: TipRequest):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    from_user = db["user"].find_one({"_id": {"$eq": payload.from_user_id}})
    to_user = db["user"].find_one({"_id": {"$eq": payload.to_user_id}})
    if not from_user or not to_user:
        raise HTTPException(status_code=404, detail="User not found")
    balance = int(from_user.get("token_balance", 0))
    if balance < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient tokens")
    # Deduct and credit
    db["user"].update_one({"_id": from_user["_id"]}, {"$inc": {"token_balance": -payload.amount}})
    db["user"].update_one({"_id": to_user["_id"]}, {"$inc": {"token_balance": payload.amount}})
    create_document("tokentransaction", TokenTransaction(from_user_id=payload.from_user_id, to_user_id=payload.to_user_id, amount=payload.amount, kind="tip", note=None, post_id=payload.post_id))
    return {"ok": True}


# --- Comments (subscriber-only, light check) ---
@app.post("/api/comments", response_model=dict)
def add_comment(comment: Comment):
    # Minimal gating: ensure user has an active subscription to the creator who owns the post
    post = db["post"].find_one({"_id": {"$eq": comment.post_id}})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    creator_id = post.get("creator_id")
    has_sub = db["subscription"].find_one({"user_id": comment.user_id, "creator_id": creator_id, "active": True})
    if not has_sub:
        raise HTTPException(status_code=403, detail="Subscription required")
    inserted_id = create_document("comment", comment)
    return {"id": inserted_id}


@app.get("/api/posts/{post_id}/comments")
def list_comments(post_id: str):
    items = get_documents("comment", {"post_id": post_id})
    return [{**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc.get("_id"))} for doc in items]


# --- Moderation (non-adult policy) ---
BLOCKED_KEYWORDS = [
    # Keep it simple for demo; real system would use proper moderation service
    "nsfw", "adult", "explicit", "18+",
]


def violates_policy(text: Optional[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in BLOCKED_KEYWORDS)


@app.post("/api/moderate/post")
def moderate_post(post: Post):
    if violates_policy(post.title) or violates_policy(post.body_text):
        raise HTTPException(status_code=400, detail="Content violates non-adult policy")
    inserted_id = create_document("post", post)
    return {"id": inserted_id}


# --- Simple analytics (creator view) ---
@app.get("/api/creators/{creator_id}/stats")
def creator_stats(creator_id: str):
    subs = db["subscription"].count_documents({"creator_id": creator_id, "active": True})
    tips = list(db["tokentransaction"].aggregate([
        {"$match": {"to_user_id": creator_id, "kind": "tip"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]))
    total_tips = tips[0]["total"] if tips else 0
    posts_count = db["post"].count_documents({"creator_id": creator_id})
    return {"active_subscribers": subs, "total_tips": total_tips, "posts": posts_count}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
