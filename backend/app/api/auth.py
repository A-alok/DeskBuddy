"""User Authentication & Account Management API."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status

from .. import repo
from ..db import mongo
from ..models import Device, User
from ..schemas import LoginRequest, RegisterRequest, UserAccountRead
from ..utils import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256 and unique salt."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against salt:hash format."""
    if not hashed or ":" not in hashed:
        return False
    salt, h_hex = hashed.split(":", 1)
    test_h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return hmac.compare_digest(test_h.hex(), h_hex)


def generate_competition_code(username: str) -> str:
    """Generate a clean, memorable, unique independent competition code."""
    clean = re.sub(r"[^A-Za-z0-9]", "", username).upper()[:4]
    if len(clean) < 4:
        clean = clean.ljust(4, "X")
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"{clean}-{digits}"


def _user_to_read(user: User, token: Optional[str] = None) -> UserAccountRead:
    has_pwd = bool(getattr(user, "password_hash", None))
    active_token = token or getattr(user, "auth_token", None)
    return UserAccountRead(
        id=user.id,
        username=getattr(user, "username", "student"),
        display_name=getattr(user, "display_name", "Student"),
        competition_code=getattr(user, "competition_code", ""),
        device_id=getattr(user, "device_id", "deskmate-01"),
        avatar=getattr(user, "avatar", "⚡") or "⚡",
        status=getattr(user, "status", "Active") or "Active",
        competitors=getattr(user, "competitors", []) or [],
        token=active_token,
        has_password=has_pwd,
        created_at=user.created_at,
    )


@router.get("/accounts", response_model=list[UserAccountRead])
async def list_accounts() -> list[UserAccountRead]:
    """List all registered user accounts for quick switching and competition."""
    users = await repo.find_many(
        mongo.users,
        User,
        {"is_demo": {"$ne": True}, "hidden": {"$ne": True}},
        sort=[("created_at", repo.ASC)],
    )
    return [_user_to_read(u) for u in users]


@router.get("/me", response_model=UserAccountRead)
async def get_current_user(
    username: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_username: Optional[str] = Header(default=None, alias="X-Username"),
) -> UserAccountRead:
    """Look up active user by valid auth token, username, or linked device_id."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            user = await mongo.users.find_one({"auth_token": token})
            if user:
                return _user_to_read(User.model_validate(user), token=token)

    target_id = x_user_id or user_id
    if target_id:
        user = await mongo.users.find_one({"_id": target_id})
        if user:
            return _user_to_read(User.model_validate(user))

    target_name = x_username or username
    if target_name:
        user = await mongo.users.find_one({"username": {"$regex": f"^{re.escape(target_name.strip())}$", "$options": "i"}})
        if user:
            return _user_to_read(User.model_validate(user))

    if device_id:
        user = await mongo.users.find_one({"device_id": device_id})
        if user:
            return _user_to_read(User.model_validate(user))
        # If device_id == "deskmate-01" or starts with "dev-", fallback to owner
        dev_doc = await mongo.devices.find_one({"_id": device_id})
        if dev_doc and dev_doc.get("user_id"):
            user = await mongo.users.find_one({"_id": dev_doc["user_id"]})
            if user:
                return _user_to_read(User.model_validate(user))

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated. Please sign in.")


@router.post("/login", response_model=UserAccountRead)
async def login(payload: LoginRequest) -> UserAccountRead:
    """Login with username and password verification."""
    name = payload.username.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")

    user_doc = await mongo.users.find_one({"username": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{name}' not found. Please check spelling or create a new account.",
        )

    user = User.model_validate(user_doc)

    # Password validation
    pwd_hash = getattr(user, "password_hash", None)
    if pwd_hash:
        if not payload.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This account is password-protected. Please enter your password.",
            )
        if not verify_password(payload.password, pwd_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password. Please try again.",
            )
    elif payload.password:
        # User supplied a password for an account that didn't have one set: secure it!
        new_hash = hash_password(payload.password)
        await repo.patch(mongo.users, User, user.id, {"password_hash": new_hash})
        user.password_hash = new_hash

    # Generate a fresh authentication session token
    token = secrets.token_urlsafe(32)
    await repo.patch(mongo.users, User, user.id, {"auth_token": token})
    user.auth_token = token

    # Ensure user has a competition code
    if not getattr(user, "competition_code", None):
        code = generate_competition_code(user.username)
        await repo.patch(mongo.users, User, user.id, {"competition_code": code})
        user.competition_code = code

    return _user_to_read(user, token=token)


@router.post("/register", response_model=UserAccountRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> UserAccountRead:
    """Create a new account with its own unique competition code and credentials."""
    raw_name = payload.username.strip()
    clean_username = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_name).lower()
    if len(clean_username) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 2 characters (letters, numbers, hyphens/underscores).",
        )

    existing = await mongo.users.find_one({"username": clean_username})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{clean_username}' is already taken. Please choose another username.",
        )

    # Generate a unique competition code
    code = ""
    for _ in range(10):
        candidate = generate_competition_code(clean_username)
        collision = await mongo.users.find_one({"competition_code": candidate})
        if not collision:
            code = candidate
            break
    if not code:
        code = f"{clean_username[:4].upper()}-{secrets.randbelow(9000) + 1000}"

    display_name = (payload.display_name or raw_name).strip() or clean_username.capitalize()
    dev_id = payload.device_id.strip() if payload.device_id else f"dev-{clean_username}"

    # Hash password if provided
    pwd_hash = hash_password(payload.password) if payload.password else None
    token = secrets.token_urlsafe(32)

    user = User(
        username=clean_username,
        display_name=display_name,
        email=f"{clean_username}@deskmate.local",
        password_hash=pwd_hash,
        auth_token=token,
        competition_code=code,
        device_id=dev_id,
        avatar=payload.avatar or "⚡",
        competitors=[],
    )
    await repo.insert(mongo.users, user)

    # Ensure associated device exists
    await repo.get_or_create(
        mongo.devices,
        Device,
        dev_id,
        lambda: Device(
            id=dev_id,
            user_id=user.id,
            name=f"{display_name}'s DeskMate",
            competition_code=code,
            competitors=[],
            competitive_unlocked=True,
        ),
    )

    return _user_to_read(user, token=token)
