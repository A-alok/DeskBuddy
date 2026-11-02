"""Thin document <-> model helpers.

Not an ORM. Just the four or five shapes of Mongo call this app actually makes,
typed against the pydantic models, so services read as domain logic instead of
driver plumbing.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, TypeVar

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from .models import Document

T = TypeVar("T", bound=Document)

ASC = ASCENDING
DESC = DESCENDING


async def find_one(
    collection: AsyncCollection, model: type[T], filt: dict[str, Any]
) -> Optional[T]:
    doc = await collection.find_one(filt)
    return model.model_validate(doc) if doc is not None else None


async def find_by_id(collection: AsyncCollection, model: type[T], doc_id: str) -> Optional[T]:
    return await find_one(collection, model, {"_id": doc_id})


async def find_many(
    collection: AsyncCollection,
    model: type[T],
    filt: dict[str, Any],
    *,
    sort: Optional[Sequence[tuple[str, int]]] = None,
    limit: int = 0,
    skip: int = 0,
) -> list[T]:
    cursor = collection.find(filt)
    if sort:
        cursor = cursor.sort(list(sort))
    if skip:
        cursor = cursor.skip(skip)
    if limit:
        cursor = cursor.limit(limit)
    return [model.model_validate(doc) async for doc in cursor]


async def insert(collection: AsyncCollection, document: Document) -> None:
    await collection.insert_one(document.to_doc())


async def insert_many(collection: AsyncCollection, documents: Sequence[Document]) -> None:
    if not documents:
        return
    await collection.insert_many([d.to_doc() for d in documents])


async def replace(collection: AsyncCollection, document: Document, *, upsert: bool = True) -> None:
    """Write the whole document back. Used after a service mutates a model."""
    await collection.replace_one(
        {"_id": document.to_doc()["_id"]}, document.to_doc(), upsert=upsert
    )


async def patch(
    collection: AsyncCollection, model: type[T], doc_id: str, changes: dict[str, Any]
) -> Optional[T]:
    """`$set` specific fields and return the updated document."""
    if not changes:
        return await find_by_id(collection, model, doc_id)
    doc = await collection.find_one_and_update(
        {"_id": doc_id}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    return model.model_validate(doc) if doc is not None else None


async def get_or_create(
    collection: AsyncCollection, model: type[T], doc_id: str, factory
) -> T:
    """Fetch a singleton document, creating it on first touch.

    Uses an upsert with `$setOnInsert` so two concurrent callers cannot both
    insert — the ESP32 and a dashboard often connect in the same instant.
    """
    existing = await collection.find_one({"_id": doc_id})
    if existing is not None:
        return model.model_validate(existing)

    fresh: T = factory()
    doc = fresh.to_doc()
    doc.pop("_id", None)
    await collection.update_one({"_id": doc_id}, {"$setOnInsert": doc}, upsert=True)
    created = await collection.find_one({"_id": doc_id})
    return model.model_validate(created) if created is not None else fresh


async def delete_by_id(collection: AsyncCollection, doc_id: str) -> bool:
    result = await collection.delete_one({"_id": doc_id})
    return result.deleted_count > 0


async def count(collection: AsyncCollection, filt: dict[str, Any], *, limit: int = 0) -> int:
    return await collection.count_documents(filt, limit=limit) if limit else await collection.count_documents(filt)
