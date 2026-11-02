"""Task CRUD."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep
from ..models import Task
from ..realtime import hub
from ..schemas import OkResponse, TaskCreate, TaskRead, TaskUpdate
from ..serializers import task_read
from ..utils import utcnow

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    device: DeviceDep,
    done: Optional[bool] = Query(default=None),
    list_type: Optional[str] = Query(default=None, description="personal or competitive"),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[TaskRead]:
    filt: dict = {"device_id": device.id}
    if done is not None:
        filt["done"] = done
    if list_type:
        if list_type == "personal":
            # Include legacy tasks that did not have list_type set yet
            filt["$or"] = [{"list_type": "personal"}, {"list_type": {"$exists": False}}]
        else:
            filt["list_type"] = list_type
    tasks = await repo.find_many(
        mongo.tasks,
        Task,
        filt,
        sort=[("done", repo.ASC), ("created_at", repo.DESC)],
        limit=limit,
    )
    return [task_read(t) for t in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(device: DeviceDep, payload: TaskCreate) -> TaskRead:
    task = Task(
        device_id=device.id,
        title=payload.title,
        notes=payload.notes,
        priority=payload.priority,
        due_at=payload.due_at,
        list_type=payload.list_type or "personal",
        xp=payload.xp if payload.xp is not None else (50 if payload.list_type == "competitive" else 20),
        source=payload.source,
    )
    await repo.insert(mongo.tasks, task)

    read = task_read(task)
    await hub.publish(
        ev.TASK_CREATED, read.model_dump(mode="json"), device_id=device.id, origin=payload.source.value
    )
    return read


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(device: DeviceDep, task_id: str, payload: TaskUpdate) -> TaskRead:
    task = await repo.find_by_id(mongo.tasks, Task, task_id)
    if task is None or task.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    data = payload.model_dump(exclude_unset=True)
    changes: dict = {}
    for field, value in data.items():
        # notes and due_at are explicitly nullable; everything else ignores None.
        if value is not None or field in {"notes", "due_at"}:
            changes[field] = value

    if "done" in changes and changes["done"] is not None and changes["done"] != task.done:
        changes["completed_at"] = utcnow() if changes["done"] else None

    changes["updated_at"] = utcnow()
    updated = await repo.patch(mongo.tasks, Task, task_id, changes)

    read = task_read(updated or task)
    await hub.publish(ev.TASK_UPDATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.delete("/{task_id}", response_model=OkResponse)
async def delete_task(device: DeviceDep, task_id: str) -> OkResponse:
    task = await repo.find_by_id(mongo.tasks, Task, task_id)
    if task is None or task.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await repo.delete_by_id(mongo.tasks, task_id)
    await hub.publish(ev.TASK_DELETED, {"id": task_id}, device_id=device.id, origin="dashboard")
    return OkResponse(detail=task_id)
