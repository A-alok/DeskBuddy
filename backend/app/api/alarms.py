"""Alarm CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep
from ..models import Alarm
from ..realtime import hub
from ..schemas import AlarmCreate, AlarmRead, AlarmUpdate, OkResponse
from ..serializers import alarm_read
from ..services import alarms as alarm_service

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("", response_model=list[AlarmRead])
async def list_alarms(device: DeviceDep) -> list[AlarmRead]:
    alarms = await alarm_service.list_for_device(device.id)
    return [alarm_read(a) for a in alarms]


@router.post("", response_model=AlarmRead, status_code=status.HTTP_201_CREATED)
async def create_alarm(device: DeviceDep, payload: AlarmCreate) -> AlarmRead:
    alarm = Alarm(
        device_id=device.id,
        label=payload.label,
        time_of_day=payload.time_of_day,
        days_of_week=payload.days_of_week,
        enabled=payload.enabled,
        sound=payload.sound,
    )
    alarm.next_trigger_at = await alarm_service.compute_next_trigger(alarm)
    await repo.insert(mongo.alarms, alarm)

    read = alarm_read(alarm)
    await hub.publish(ev.ALARM_CREATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.patch("/{alarm_id}", response_model=AlarmRead)
async def update_alarm(device: DeviceDep, alarm_id: str, payload: AlarmUpdate) -> AlarmRead:
    alarm = await alarm_service.get(alarm_id)
    if alarm is None or alarm.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(alarm, field, value)
    # Any change to time, days or enabled invalidates the stored fire time.
    changes["next_trigger_at"] = await alarm_service.compute_next_trigger(alarm)

    updated = await repo.patch(mongo.alarms, Alarm, alarm_id, changes)
    read = alarm_read(updated or alarm)
    await hub.publish(ev.ALARM_UPDATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.delete("/{alarm_id}", response_model=OkResponse)
async def delete_alarm(device: DeviceDep, alarm_id: str) -> OkResponse:
    alarm = await alarm_service.get(alarm_id)
    if alarm is None or alarm.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found")
    await repo.delete_by_id(mongo.alarms, alarm_id)
    await hub.publish(ev.ALARM_DELETED, {"id": alarm_id}, device_id=device.id, origin="dashboard")
    return OkResponse(detail=alarm_id)
