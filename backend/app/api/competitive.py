"""Competitive Learning API: Real XP calculations, League ranks, Real Leaderboard, Activity, and Friend Competition Codes."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep
from ..models import CompetitionInvite, Device, FocusSession, InviteStatus, QuizSession, Task, User
from ..realtime import hub
from ..schemas import (
    BadgeRead,
    ChallengeRequest,
    ChallengeResponse,
    CompetitionInviteRead,
    CompetitiveActivityItem,
    CompetitivePillarStats,
    CompetitiveSummaryRead,
    CompetitorAddRequest,
    CompetitorAddResponse,
    InviteActionResponse,
    InvitesListRead,
    LeaderboardEntry,
    OkResponse,
    ReferralAccessRead,
    ReferralUnlockRequest,
)
from ..utils import utcnow

router = APIRouter(prefix="/competitive", tags=["competitive"])


def _get_device_code(device: Device) -> str:
    """Generate or return a clean, human-readable competition code for the device."""
    if getattr(device, "competition_code", None):
        return device.competition_code
    if getattr(device, "referral_code", None):
        return device.referral_code
    clean = re.sub(r"[^A-Za-z0-9]", "", device.id).upper()
    suffix = clean[-4:] if len(clean) >= 4 else clean.ljust(4, "X")
    return f"DESK-{suffix}"


def _calculate_league(xp: int) -> str:
    if xp >= 7000:
        return "Diamond"
    if xp >= 3500:
        return "Platinum"
    if xp >= 1500:
        return "Gold"
    if xp >= 500:
        return "Silver"
    return "Bronze"


async def _get_user_for_device(device: Device) -> Optional[User]:
    """Find the user profile linked to this device, if any."""
    user_doc = await mongo.users.find_one({"device_id": device.id})
    if not user_doc and getattr(device, "user_id", None):
        user_doc = await mongo.users.find_one({"_id": device.user_id})
    if user_doc:
        return User.model_validate(user_doc)
    return None


async def compute_stats_for_device(dev_id: str) -> dict[str, Any]:
    """Calculate 100% genuine stats and XP for a device from MongoDB records."""
    # 1. Pomodoro Focus
    focus_sessions = await repo.find_many(
        mongo.focus_sessions, FocusSession, {"device_id": dev_id}
    )
    completed_focus = [s for s in focus_sessions if s.completed]
    total_focus_seconds = sum(
        s.actual_seconds or s.planned_seconds for s in completed_focus
    )
    total_focus_minutes = total_focus_seconds // 60
    pomodoro_cycles = len(completed_focus)
    pomodoro_xp = (pomodoro_cycles * 25) + ((total_focus_minutes // 10) * 5)

    # 2. Tasks
    all_tasks = await repo.find_many(mongo.tasks, Task, {"device_id": dev_id})
    personal_tasks = [
        t for t in all_tasks if getattr(t, "list_type", "personal") != "competitive"
    ]
    competitive_tasks = [
        t for t in all_tasks if getattr(t, "list_type", "personal") == "competitive"
    ]
    done_competitive = [t for t in competitive_tasks if t.done]
    done_personal = [t for t in personal_tasks if t.done]
    task_xp = sum(getattr(t, "xp", 50) or 50 for t in done_competitive) + (
        len(done_personal) * 10
    )

    # 3. Quizzes
    quiz_sessions = await repo.find_many(
        mongo.quiz_sessions, QuizSession, {"device_id": dev_id}
    )
    total_questions = sum(len(q.questions) for q in quiz_sessions if q.questions)
    total_correct = sum(q.correct_count for q in quiz_sessions)
    accuracy_pct = (
        int(round((total_correct / total_questions) * 100))
        if total_questions > 0
        else 0
    )
    finished_quizzes = [q for q in quiz_sessions if q.finished]
    perfect_quizzes = sum(
        1
        for q in finished_quizzes
        if len(q.questions) > 0 and q.correct_count == len(q.questions)
    )
    quiz_xp = (total_correct * 30) + (perfect_quizzes * 50)

    # 4. Streak from real activity timestamps
    activity_dates = set()
    for s in focus_sessions:
        if s.started_at:
            activity_dates.add(s.started_at.strftime("%Y-%m-%d"))
    for t in all_tasks:
        if t.completed_at:
            activity_dates.add(t.completed_at.strftime("%Y-%m-%d"))
    for q in quiz_sessions:
        if q.created_at:
            activity_dates.add(q.created_at.strftime("%Y-%m-%d"))

    today = utcnow().date()
    streak = 0
    check_date = today
    while check_date.strftime("%Y-%m-%d") in activity_dates:
        streak += 1
        check_date -= timedelta(days=1)
    if streak == 0:
        check_date = today - timedelta(days=1)
        while check_date.strftime("%Y-%m-%d") in activity_dates:
            streak += 1
            check_date -= timedelta(days=1)
    streak_days = max(1 if activity_dates else 0, streak)

    total_xp = pomodoro_xp + task_xp + quiz_xp
    level = (total_xp // 250) + 1
    league = _calculate_league(total_xp)

    return {
        "total_xp": total_xp,
        "pomodoro_xp": pomodoro_xp,
        "task_xp": task_xp,
        "quiz_xp": quiz_xp,
        "pomodoro_cycles": pomodoro_cycles,
        "total_focus_minutes": total_focus_minutes,
        "completed_focus": len(completed_focus),
        "done_competitive": len(done_competitive),
        "total_competitive": len(competitive_tasks),
        "done_personal": len(done_personal),
        "total_personal": len(personal_tasks),
        "total_questions": total_questions,
        "total_correct": total_correct,
        "accuracy_pct": accuracy_pct,
        "perfect_quizzes": perfect_quizzes,
        "streak_days": streak_days,
        "level": level,
        "league": league,
    }


@router.get("/access", response_model=ReferralAccessRead)
async def get_access(device: DeviceDep) -> ReferralAccessRead:
    """Returns access info and this account's competition code."""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    return ReferralAccessRead(
        unlocked=True,
        my_referral_code=my_code,
        referred_by=getattr(device, "referred_by", None),
        referrals_count=len(getattr(user, "competitors", []) or getattr(device, "competitors", [])),
        message="Active",
    )


@router.post("/unlock", response_model=ReferralAccessRead)
async def unlock_competitive(
    device: DeviceDep, payload: ReferralUnlockRequest
) -> ReferralAccessRead:
    """Backward compatibility alias for adding a competitor by code."""
    return await get_access(device)


def _invite_to_read(inv: CompetitionInvite) -> CompetitionInviteRead:
    return CompetitionInviteRead(
        id=inv.id,
        sender_user_id=inv.sender_user_id,
        sender_username=inv.sender_username,
        sender_name=inv.sender_name,
        sender_code=inv.sender_code,
        sender_device_id=inv.sender_device_id,
        sender_avatar=inv.sender_avatar,
        recipient_user_id=inv.recipient_user_id,
        recipient_username=inv.recipient_username,
        recipient_name=inv.recipient_name,
        recipient_code=inv.recipient_code,
        recipient_device_id=inv.recipient_device_id,
        recipient_avatar=inv.recipient_avatar,
        status=inv.status.value if hasattr(inv.status, "value") else str(inv.status),
        created_at=inv.created_at,
        responded_at=inv.responded_at,
    )


@router.post("/challenge", response_model=ChallengeResponse)
async def send_challenge(
    device: DeviceDep, payload: ChallengeRequest
) -> ChallengeResponse:
    """Send a competition challenge to a friend. The competition starts once they accept!"""
    input_code = payload.competition_code.strip().upper()
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)

    if input_code == my_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot challenge yourself! Enter a classmate's competition code.",
        )

    # Find the recipient account by competition code (in users or devices)
    peer_user_doc = await mongo.users.find_one({"competition_code": input_code})
    peer_device_doc = None
    if not peer_user_doc:
        peer_device_doc = await mongo.devices.find_one({"$or": [{"competition_code": input_code}, {"referral_code": input_code}]})

    if not peer_user_doc and not peer_device_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account found with competition code '{input_code}'. Check the code with your classmate.",
        )

    peer_user_id = str(peer_user_doc["_id"]) if peer_user_doc else str(peer_device_doc["_id"])
    peer_username = peer_user_doc.get("username", "peer") if peer_user_doc else "peer"
    peer_name = (
        peer_user_doc.get("display_name")
        if peer_user_doc
        else peer_device_doc.get("name", "Classmate")
    )
    peer_dev_id = peer_user_doc.get("device_id", peer_user_id) if peer_user_doc else peer_device_doc["_id"]
    peer_avatar = peer_user_doc.get("avatar", "🎓") if peer_user_doc else "🎓"

    # Check if already active competitors (accepted)
    current_competitors: list[str] = list(getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or [])
    if input_code in current_competitors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{peer_name}' ({input_code}) is already an active competitor in your study league!",
        )

    # Check for existing pending outgoing challenge
    existing_outgoing = await mongo.competition_invites.find_one({
        "sender_code": my_code,
        "recipient_code": input_code,
        "status": InviteStatus.PENDING.value,
    })
    if existing_outgoing:
        inv = CompetitionInvite.model_validate(existing_outgoing)
        return ChallengeResponse(
            ok=True,
            message=f"⏳ Challenge is already pending for {peer_name}! Waiting for them to accept.",
            invite=_invite_to_read(inv),
        )

    # Check if peer had already challenged me -> if so, auto-accept it!
    existing_incoming = await mongo.competition_invites.find_one({
        "sender_code": input_code,
        "recipient_code": my_code,
        "status": InviteStatus.PENDING.value,
    })
    if existing_incoming:
        inv_id = existing_incoming["_id"]
        await mongo.competition_invites.update_one(
            {"_id": inv_id},
            {"$set": {"status": InviteStatus.ACCEPTED.value, "responded_at": utcnow()}},
        )
        current_competitors.append(input_code)
        if user:
            await repo.patch(mongo.users, User, user.id, {"competitors": current_competitors})
        await repo.patch(mongo.devices, Device, device.id, {"competitors": current_competitors})

        if peer_user_doc:
            peer_comp = list(peer_user_doc.get("competitors") or [])
            if my_code not in peer_comp:
                peer_comp.append(my_code)
                await mongo.users.update_one({"_id": peer_user_doc["_id"]}, {"$set": {"competitors": peer_comp}})

        await hub.publish(
            ev.COMPETITION_ACCEPTED,
            {"invite_id": inv_id, "competitor_code": input_code, "competitor_name": peer_name},
            device_id=device.id,
            origin="dashboard",
        )
        updated_inv = await repo.find_by_id(mongo.competition_invites, CompetitionInvite, inv_id)
        return ChallengeResponse(
            ok=True,
            message=f"🎉 {peer_name} had already challenged you! Challenge accepted — the competition has officially started!",
            invite=_invite_to_read(updated_inv or CompetitionInvite.model_validate(existing_incoming)),
        )

    # Create new pending challenge
    invite = CompetitionInvite(
        sender_user_id=user.id if user else device.id,
        sender_username=getattr(user, "username", "student"),
        sender_name=getattr(user, "display_name", device.name),
        sender_code=my_code,
        sender_device_id=device.id,
        sender_avatar=getattr(user, "avatar", "⚡") or "⚡",
        recipient_user_id=peer_user_id,
        recipient_username=peer_username,
        recipient_name=peer_name,
        recipient_code=input_code,
        recipient_device_id=peer_dev_id,
        recipient_avatar=peer_avatar,
        status=InviteStatus.PENDING,
    )
    await repo.insert(mongo.competition_invites, invite)

    await hub.publish(
        ev.COMPETITION_INVITE,
        invite.to_doc(),
        device_id=device.id,
        origin="dashboard",
    )

    return ChallengeResponse(
        ok=True,
        message=f"⚔️ Challenge sent to {peer_name}! The competition will start once they accept.",
        invite=_invite_to_read(invite),
    )


@router.get("/invites", response_model=InvitesListRead)
async def get_invites(device: DeviceDep) -> InvitesListRead:
    """Return all incoming and outgoing competition challenges for this account."""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    my_uid = user.id if user else device.id

    incoming_docs = await repo.find_many(
        mongo.competition_invites,
        CompetitionInvite,
        {
            "$or": [{"recipient_code": my_code}, {"recipient_user_id": my_uid}],
            "status": InviteStatus.PENDING.value,
        },
        sort=[("created_at", repo.DESC)],
    )

    outgoing_docs = await repo.find_many(
        mongo.competition_invites,
        CompetitionInvite,
        {
            "$or": [{"sender_code": my_code}, {"sender_user_id": my_uid}],
            "status": InviteStatus.PENDING.value,
        },
        sort=[("created_at", repo.DESC)],
    )

    return InvitesListRead(
        incoming=[_invite_to_read(i) for i in incoming_docs],
        outgoing=[_invite_to_read(i) for i in outgoing_docs],
    )


@router.post("/invites/{invite_id}/accept", response_model=InviteActionResponse)
async def accept_invite(device: DeviceDep, invite_id: str) -> InviteActionResponse:
    """Accept an incoming competition challenge. THE COMPETITION OFFICIALLY STARTS!"""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    my_uid = user.id if user else device.id

    invite = await repo.find_by_id(mongo.competition_invites, CompetitionInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge invite not found")

    if invite.recipient_code != my_code and invite.recipient_user_id != my_uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This challenge was not addressed to you")

    if invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Challenge is already {invite.status}")

    # Mark accepted in database
    await repo.patch(
        mongo.competition_invites,
        CompetitionInvite,
        invite.id,
        {"status": InviteStatus.ACCEPTED.value, "responded_at": utcnow()},
    )

    # Add each other mutually to competitors so the competition starts!
    my_competitors: list[str] = list(getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or [])
    if invite.sender_code not in my_competitors:
        my_competitors.append(invite.sender_code)
        if user:
            await repo.patch(mongo.users, User, user.id, {"competitors": my_competitors})
        await repo.patch(mongo.devices, Device, device.id, {"competitors": my_competitors})

    sender_user = await repo.find_by_id(mongo.users, User, invite.sender_user_id)
    if not sender_user:
        sender_user_doc = await mongo.users.find_one({"competition_code": invite.sender_code})
        if sender_user_doc:
            sender_user = User.model_validate(sender_user_doc)
    if sender_user:
        sender_comp = list(sender_user.competitors or [])
        if my_code not in sender_comp:
            sender_comp.append(my_code)
            await repo.patch(mongo.users, User, sender_user.id, {"competitors": sender_comp})

    sender_device = await repo.find_by_id(mongo.devices, Device, invite.sender_device_id)
    if sender_device:
        s_dev_comp = list(sender_device.competitors or [])
        if my_code not in s_dev_comp:
            s_dev_comp.append(my_code)
            await repo.patch(mongo.devices, Device, sender_device.id, {"competitors": s_dev_comp})

    # Publish real-time event to hub
    await hub.publish(
        ev.COMPETITION_ACCEPTED,
        {
            "invite_id": invite.id,
            "sender_code": invite.sender_code,
            "sender_name": invite.sender_name,
            "recipient_code": my_code,
            "recipient_name": getattr(user, "display_name", device.name),
        },
        device_id=device.id,
        origin="dashboard",
    )

    return InviteActionResponse(
        ok=True,
        message=f"🎉 Challenge accepted! The competition with {invite.sender_name} has officially started!",
        competitor_name=invite.sender_name,
        competitor_code=invite.sender_code,
    )


@router.post("/invites/{invite_id}/decline", response_model=InviteActionResponse)
async def decline_invite(device: DeviceDep, invite_id: str) -> InviteActionResponse:
    """Decline an incoming challenge."""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    my_uid = user.id if user else device.id

    invite = await repo.find_by_id(mongo.competition_invites, CompetitionInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge invite not found")

    if invite.recipient_code != my_code and invite.recipient_user_id != my_uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This challenge was not addressed to you")

    await repo.patch(
        mongo.competition_invites,
        CompetitionInvite,
        invite.id,
        {"status": InviteStatus.DECLINED.value, "responded_at": utcnow()},
    )

    return InviteActionResponse(
        ok=True,
        message="Challenge declined.",
        competitor_name=invite.sender_name,
        competitor_code=invite.sender_code,
    )


@router.post("/invites/{invite_id}/cancel", response_model=InviteActionResponse)
async def cancel_invite(device: DeviceDep, invite_id: str) -> InviteActionResponse:
    """Cancel an outgoing challenge."""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    my_uid = user.id if user else device.id

    invite = await repo.find_by_id(mongo.competition_invites, CompetitionInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge invite not found")

    if invite.sender_code != my_code and invite.sender_user_id != my_uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only cancel challenges sent by you")

    await repo.patch(
        mongo.competition_invites,
        CompetitionInvite,
        invite.id,
        {"status": InviteStatus.CANCELLED.value, "responded_at": utcnow()},
    )

    return InviteActionResponse(
        ok=True,
        message="Challenge cancelled.",
        competitor_name=invite.recipient_name,
        competitor_code=invite.recipient_code,
    )


@router.post("/competitors", response_model=CompetitorAddResponse)
async def add_competitor(
    device: DeviceDep, payload: CompetitorAddRequest
) -> CompetitorAddResponse:
    """Challenge a classmate to compete. Competition starts when accepted!"""
    res = await send_challenge(device, ChallengeRequest(competition_code=payload.competition_code))
    user = await _get_user_for_device(device)
    current_competitors: list[str] = list(getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or [])
    return CompetitorAddResponse(
        ok=True,
        message=res.message,
        competitor_name=res.invite.recipient_name,
        competitor_code=res.invite.recipient_code,
        competitors=current_competitors,
    )


@router.delete("/competitors/{competition_code}", response_model=OkResponse)
async def remove_competitor(device: DeviceDep, competition_code: str) -> OkResponse:
    """Remove a classmate from your competition circle."""
    code = competition_code.strip().upper()
    user = await _get_user_for_device(device)
    current_competitors: list[str] = list(getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or [])
    if code in current_competitors:
        current_competitors.remove(code)
        if user:
            await repo.patch(mongo.users, User, user.id, {"competitors": current_competitors})
        await repo.patch(mongo.devices, Device, device.id, {"competitors": current_competitors})

    return OkResponse(detail=f"Removed {code} from competition circle")


@router.get("/summary", response_model=CompetitiveSummaryRead)
async def get_summary(device: DeviceDep) -> CompetitiveSummaryRead:
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    stats = await compute_stats_for_device(device.id)

    competitors = getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or []

    # Calculate rank dynamically among real competitors in circle
    my_xp = stats["total_xp"]
    rank = 1
    for code in competitors:
        peer_doc = await mongo.users.find_one({"competition_code": code})
        peer_dev_id = peer_doc.get("device_id") if peer_doc else None
        if not peer_dev_id:
            peer_dev = await mongo.devices.find_one({"$or": [{"competition_code": code}, {"referral_code": code}]})
            if peer_dev:
                peer_dev_id = peer_dev["_id"]
        if peer_dev_id:
            peer_stats = await compute_stats_for_device(peer_dev_id)
            if peer_stats["total_xp"] > my_xp:
                rank += 1

    # Badges
    badges = [
        BadgeRead(
            id="first_step",
            name="First Milestone",
            description="Completed your first study activity",
            icon="🌱",
            unlocked=bool(
                stats["pomodoro_cycles"] > 0
                or stats["done_personal"] > 0
                or stats["done_competitive"] > 0
                or stats["total_questions"] > 0
            ),
        ),
        BadgeRead(
            id="peer_network",
            name="Study Circle",
            description="Added at least one classmate to your study competition circle",
            icon="🤝",
            unlocked=len(competitors) > 0,
        ),
        BadgeRead(
            id="pomodoro_focus",
            name="Focus Initiate",
            description="Completed at least one Pomodoro focus session",
            icon="🍅",
            unlocked=stats["pomodoro_cycles"] >= 1,
        ),
        BadgeRead(
            id="task_crusher",
            name="Task Crusher",
            description="Completed 3 or more competitive tasks",
            icon="⚔️",
            unlocked=stats["done_competitive"] >= 3,
        ),
        BadgeRead(
            id="quiz_ace",
            name="Quiz Prodigy",
            description="Achieved 80%+ accuracy across questions",
            icon="🎯",
            unlocked=stats["accuracy_pct"] >= 80 and stats["total_questions"] >= 3,
        ),
        BadgeRead(
            id="centurion",
            name="Centurion",
            description="Accumulated 100+ minutes of deep focus",
            icon="⏳",
            unlocked=stats["total_focus_minutes"] >= 100,
        ),
        BadgeRead(
            id="silver_tier",
            name="Scholar League",
            description="Reached Silver League or higher (500+ XP)",
            icon="🥈",
            unlocked=stats["total_xp"] >= 500,
        ),
        BadgeRead(
            id="diamond_tier",
            name="Grandmaster",
            description="Ascended to Diamond League (7000+ XP)",
            icon="💎",
            unlocked=stats["total_xp"] >= 7000,
        ),
    ]

    xp_per_level = 250
    current_level_xp = stats["total_xp"] % xp_per_level
    progress_pct = int((current_level_xp / xp_per_level) * 100)

    return CompetitiveSummaryRead(
        total_xp=stats["total_xp"],
        level=stats["level"],
        current_level_xp=current_level_xp,
        next_level_xp=xp_per_level,
        progress_pct=progress_pct,
        league=stats["league"],
        rank=rank,
        streak_days=stats["streak_days"],
        unlocked=True,
        my_referral_code=my_code,
        competition_code=my_code,
        competitors=competitors,
        referred_by=getattr(device, "referred_by", None),
        referrals_count=len(competitors),
        pomodoro=CompetitivePillarStats(
            xp=stats["pomodoro_xp"],
            details={
                "cycles": stats["pomodoro_cycles"],
                "focus_minutes": stats["total_focus_minutes"],
                "completed_sessions": stats["completed_focus"],
            },
        ),
        tasks=CompetitivePillarStats(
            xp=stats["task_xp"],
            details={
                "competitive_done": stats["done_competitive"],
                "competitive_total": stats["total_competitive"],
                "personal_done": stats["done_personal"],
                "personal_total": stats["total_personal"],
            },
        ),
        quizzes=CompetitivePillarStats(
            xp=stats["quiz_xp"],
            details={
                "quizzes_taken": stats["total_questions"] // 5 if stats["total_questions"] else 0,
                "questions_answered": stats["total_questions"],
                "correct_answers": stats["total_correct"],
                "accuracy_pct": stats["accuracy_pct"],
                "perfect_quizzes": stats["perfect_quizzes"],
            },
        ),
        badges=badges,
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(device: DeviceDep) -> list[LeaderboardEntry]:
    """Return strictly real accounts: the current user and their added competitors. NO MOCK DATA!"""
    user = await _get_user_for_device(device)
    my_code = getattr(user, "competition_code", None) or _get_device_code(device)
    my_stats = await compute_stats_for_device(device.id)

    competitor_codes: list[str] = list(
        getattr(user, "competitors", []) if user else getattr(device, "competitors", []) or []
    )

    entries: list[LeaderboardEntry] = []

    # 1. Current user entry
    my_name = getattr(user, "display_name", None) or f"{device.name} (You)"
    entries.append(
        LeaderboardEntry(
            rank=0,
            name=f"{my_name} (You)",
            avatar=getattr(user, "avatar", "⚡") or "⚡",
            league=my_stats["league"],
            level=my_stats["level"],
            total_xp=my_stats["total_xp"],
            streak_days=my_stats["streak_days"],
            is_user=True,
            status="Active Now",
            competition_code=my_code,
        )
    )

    # 2. Real added competitors ONLY (strictly no mock data!)
    seen_codes = {my_code}
    for code in competitor_codes:
        if code in seen_codes:
            continue
        seen_codes.add(code)

        peer_user_doc = await mongo.users.find_one({"competition_code": code})
        peer_dev_id = None
        peer_name = "Classmate"
        peer_avatar = "🎓"
        peer_status = "In Study League"

        if peer_user_doc:
            peer_dev_id = peer_user_doc.get("device_id") or peer_user_doc["_id"]
            peer_name = peer_user_doc.get("display_name") or peer_user_doc.get("username")
            peer_avatar = peer_user_doc.get("avatar") or "🎓"
            peer_status = peer_user_doc.get("status") or "In Study League"
        else:
            peer_dev_doc = await mongo.devices.find_one(
                {"$or": [{"competition_code": code}, {"referral_code": code}]}
            )
            if peer_dev_doc:
                peer_dev_id = peer_dev_doc["_id"]
                peer_name = peer_dev_doc.get("name", "DeskMate Peer")

        if peer_dev_id:
            peer_stats = await compute_stats_for_device(peer_dev_id)
            entries.append(
                LeaderboardEntry(
                    rank=0,
                    name=peer_name,
                    avatar=peer_avatar,
                    league=peer_stats["league"],
                    level=peer_stats["level"],
                    total_xp=peer_stats["total_xp"],
                    streak_days=peer_stats["streak_days"],
                    is_user=False,
                    status=peer_status,
                    competition_code=code,
                )
            )

    # Sort strictly by genuine total_xp descending
    entries.sort(key=lambda e: e.total_xp, reverse=True)
    for idx, e in enumerate(entries, start=1):
        e.rank = idx

    return entries


@router.get("/activity", response_model=list[CompetitiveActivityItem])
async def get_activity(device: DeviceDep) -> list[CompetitiveActivityItem]:
    """Return genuine recent activity feed from MongoDB."""
    items: list[CompetitiveActivityItem] = []

    # Focus sessions
    focus_sessions = await repo.find_many(
        mongo.focus_sessions,
        FocusSession,
        {"device_id": device.id, "completed": True},
        sort=[("started_at", repo.DESC)],
        limit=10,
    )
    for s in focus_sessions:
        mins = (s.actual_seconds or s.planned_seconds or 1500) // 60
        items.append(
            CompetitiveActivityItem(
                id=f"focus_{s.id}",
                kind="pomodoro",
                title="Completed Pomodoro Session",
                description=f"Focused for {mins} minutes without interruption",
                xp_earned=25 + (mins // 10) * 5,
                timestamp=s.ended_at or s.started_at,
            )
        )

    # Tasks
    tasks = await repo.find_many(
        mongo.tasks,
        Task,
        {"device_id": device.id, "done": True},
        sort=[("completed_at", repo.DESC)],
        limit=10,
    )
    for t in tasks:
        is_comp = getattr(t, "list_type", "personal") == "competitive"
        items.append(
            CompetitiveActivityItem(
                id=f"task_{t.id}",
                kind="task",
                title=f"{'⚔️ Competitive Challenge' if is_comp else '📋 Personal Task'} Completed",
                description=t.title,
                xp_earned=getattr(t, "xp", 50) or (50 if is_comp else 10),
                timestamp=t.completed_at or t.updated_at or t.created_at,
            )
        )

    # Quizzes
    quizzes = await repo.find_many(
        mongo.quiz_sessions,
        QuizSession,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=10,
    )
    for q in quizzes:
        tot = len(q.questions)
        cor = q.correct_count
        pct = int(round((cor / tot) * 100)) if tot > 0 else 0
        bonus = 50 if (tot > 0 and cor == tot) else 0
        items.append(
            CompetitiveActivityItem(
                id=f"quiz_{q.id}",
                kind="quiz",
                title=f"Quiz on {q.note_title or 'Notes'}",
                description=f"Scored {cor}/{tot} ({pct}%)"
                + (" · Perfect Score Bonus!" if bonus else ""),
                xp_earned=(cor * 30) + bonus,
                timestamp=q.updated_at or q.created_at,
            )
        )

    items.sort(key=lambda i: i.timestamp, reverse=True)
    return items[:20]
