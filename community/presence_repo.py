# presence_repo.py
import asyncio
import datetime
from typing import Dict, Any
from django.conf import settings
from motor.motor_asyncio import AsyncIOMotorClient

# Cache clients per event loop to avoid cross-loop reuse
_clients_by_loop: Dict[asyncio.AbstractEventLoop, AsyncIOMotorClient] = {}
_indexes_ready = False

def _get_client() -> AsyncIOMotorClient:
    loop = asyncio.get_running_loop()
    client = _clients_by_loop.get(loop)
    if client is None:
        uri = getattr(settings, "MONGO_URI", "mongodb://localhost:27017")
        client = AsyncIOMotorClient(uri)
        _clients_by_loop[loop] = client
    return client

def _get_collection():
    dbname = getattr(settings, "MONGO_DB_NAME", "appdb")
    return _get_client()[dbname]["presence"]

async def _ensure_indexes():
    global _indexes_ready
    if _indexes_ready:
        return
    col = _get_collection()
    await col.create_index([("project_id", 1), ("user_id", 1)], unique=True)
    ttl = int(getattr(settings, "PRESENCE_TTL_SECONDS", 300))
    await col.create_index("ts", expireAfterSeconds=ttl)
    _indexes_ready = True

async def upsert_presence(project_id: int, user_id: int, data: Dict[str, Any]) -> None:
    await _ensure_indexes()
    now = datetime.datetime.utcnow()
    col = _get_collection()
    doc = {"project_id": int(project_id), "user_id": int(user_id), "ts": now, **data}
    await col.update_one(
        {"project_id": int(project_id), "user_id": int(user_id)},
        {"$set": doc},
        upsert=True,
    )

async def get_presence_map(project_id: int) -> Dict[int, Dict[str, Any]]:
    await _ensure_indexes()
    col = _get_collection()
    cursor = col.find({"project_id": int(project_id)}, {"_id": 0})
    items = [doc async for doc in cursor]
    return {int(d["user_id"]): d for d in items}

# ✅ Optional: some tests reference get_roster(...) and expect a list
async def get_roster(project_id: int):
    await _ensure_indexes()
    col = _get_collection()
    cursor = col.find({"project_id": int(project_id)}, {"_id": 0})
    return [doc async for doc in cursor]

async def remove_presence(project_id: int, user_id: int) -> None:
    await _ensure_indexes()
    col = _get_collection()
    await col.delete_one({"project_id": int(project_id), "user_id": int(user_id)})

async def clear_project(project_id: int) -> None:
    await _ensure_indexes()
    col = _get_collection()
    await col.delete_many({"project_id": int(project_id)})
