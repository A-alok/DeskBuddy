"""Reminder CRUD."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep
from ..models import Reminder
from ..realtime import hub
from ..schemas import OkResponse, ReminderCreate, ReminderRead, ReminderUpdate
from ..serializers import reminder_read
from ..utils import utcnow

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderRead])
async def list_reminders(
    device: DeviceDep,
    done: Optional[bool] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[ReminderRead]:
    filt: dict = {"device_id": device.id}
    if done is not None:
        filt["done"] = done
    reminders = await repo.find_many(
        mongo.reminders, Reminder, filt, sort=[("remind_at", repo.ASC)], limit=limit
    )
    return [reminder_read(r) for r in reminders]


@router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
async def create_reminder(device: DeviceDep, payload: ReminderCreate) -> ReminderRead:
    if payload.remind_at is None and payload.in_minutes is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either remind_at or in_minutes",
        )
    remind_at = payload.remind_at or (utcnow() + timedelta(minutes=payload.in_minutes or 10))

    reminder = Reminder(
        device_id=device.id, text=payload.text, remind_at=remind_at, source=payload.source
    )
    await repo.insert(mongo.reminders, reminder)

    read = reminder_read(reminder)
    await hub.publish(
        ev.REMINDER_CREATED,
        read.model_dump(mode="json"),
        device_id=device.id,
        origin=payload.source.value,
    )
    return read


@router.patch("/{reminder_id}", response_model=ReminderRead)
async def update_reminder(
    device: DeviceDep, reminder_id: str, payload: ReminderUpdate
) -> ReminderRead:
    reminder = await repo.find_by_id(mongo.reminders, Reminder, reminder_id)
    if reminder is None or reminder.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "remind_at" in changes:
        # Rescheduled: let it fire again.
        changes["notified_at"] = None

    updated = await repo.patch(mongo.reminders, Reminder, reminder_id, changes)
    read = reminder_read(updated or reminder)
    await hub.publish(ev.REMINDER_UPDATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.delete("/{reminder_id}", response_model=OkResponse)
async def delete_reminder(device: DeviceDep, reminder_id: str) -> OkResponse:
    reminder = await repo.find_by_id(mongo.reminders, Reminder, reminder_id)
    if reminder is None or reminder.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    await repo.delete_by_id(mongo.reminders, reminder_id)
    await hub.publish(ev.REMINDER_DELETED, {"id": reminder_id}, device_id=device.id, origin="dashboard")
    return OkResponse(detail=reminder_id)
