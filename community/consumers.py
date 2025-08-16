# community/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import Project
from .views import _user_in_project, _get_or_create_project_chat
import time
import logging

# NEW: use Mongo-backed presence
from . import presence_repo

log = logging.getLogger(__name__)

def _hash_color(s: str) -> str:
    """Generate a deterministic pastel color string for a user."""
    h = abs(hash(s)) % 360
    return f"hsl({h} 90% 60%)"


class ProjectChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.project_id = int(self.scope["url_route"]["kwargs"]["project_id"])
        self.group = f"projectchat_{self.project_id}"
        self.user = self.scope.get("user")
        # cache identity once for consistent color
        self.display_name = getattr(self.user, "name", None) or getattr(self.user, "username", "user")
        self.color = _hash_color(f"{getattr(self.user, 'id', 'anon')}:{self.display_name}")

        allowed = await self._user_can_join(self.user, self.project_id)
        if not allowed:
            await self.close(code=4001)
            return

        self._last_move_ms = 0
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        try:
            uid = getattr(self.user, "id", None)
            if uid:
                try:
                    await presence_repo.remove_presence(self.project_id, uid)
                except Exception as e:
                    log.warning("presence remove failed: %s", e)
                await self.channel_layer.group_send(
                    self.group,
                    {"type": "presence.leave", "user_id": uid},
                )
        finally:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        t = content.get("type")

        # --- chat message ---
        if t == "message":
            text = (content.get("content") or "").strip()
            if not text:
                return
            msg = await self._persist_message(self.project_id, self.user, text)
            await self.channel_layer.group_send(
                self.group,
                {"type": "chat.message", **msg, "likes": 0},
            )
            return

        # --- typing indicator ---
        if t == "typing":
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "chat.typing",
                    "sender": self.display_name,
                },
            )
            return

        # --- presence announce ---
        if t == "presence.hello":
            name = self.display_name
            color = self.color
            me = {
                "user_id": self.user.id,
                "name": name,
                "color": color,
                "x": 0.5,
                "y": 0.5,
            }
            # upsert myself, then send roster (excluding me)
            try:
                await presence_repo.upsert_presence(self.project_id, self.user.id, me)
                pres_map = await presence_repo.get_presence_map(self.project_id)
            except Exception as e:
                log.error("presence hello failed: %s", e)
                pres_map = {}
            await self.send_json(
                {
                    "type": "presence.roster",
                    "users": [
                        {
                            "user_id": uid,
                            "name": data.get("name"),
                            "color": data.get("color", _hash_color(str(uid))),
                            "x": data.get("x", 0.5),
                            "y": data.get("y", 0.5),
                        }
                        for uid, data in pres_map.items()
                        if uid != self.user.id
                    ],
                }
            )
            # broadcast my join to others
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "presence.join",
                    "user_id": self.user.id,
                    "name": name,
                    "color": color,
                    "x": me["x"],
                    "y": me["y"],
                },
            )
            return

        # --- cursor movement ---
        if t == "cursor.move":
            x, y = content.get("x"), content.get("y")
            try:
                x = float(x)
                y = float(y)
            except (TypeError, ValueError):
                return
            x = min(1, max(0, x))
            y = min(1, max(0, y))

            # throttle ~30fps
            now_ms = int(time.time() * 1000)
            if now_ms - self._last_move_ms < 33:
                return
            self._last_move_ms = now_ms


            # update my coords + heartbeat in Mongo
            try:
                await presence_repo.upsert_presence(
                    self.project_id, self.user.id, {"name": self.display_name, "x": x, "y": y}
                )
            except Exception as e:
                log.warning("presence move failed: %s", e)


            await self.channel_layer.group_send(
                self.group,
                {"type": "cursor.update", "user_id": self.user.id, "x": x, "y": y},
            )
            return

    # --- event handlers from group_send -> WS ---
    async def chat_message(self, event):
        await self.send_json(
            {"type": "message", **{k: v for k, v in event.items() if k != "type"}}
        )

    async def chat_typing(self, event):
        await self.send_json({"type": "typing", "sender": event["sender"]})

    async def presence_join(self, event):
        await self.send_json(
            {"type": "presence.join", **{k: v for k, v in event.items() if k != "type"}}
        )

    async def presence_leave(self, event):
        await self.send_json({"type": "presence.leave", "user_id": event["user_id"]})

    async def cursor_update(self, event):
        if event.get("user_id") == self.user.id:
            return  # don't echo to sender
        await self.send_json(
            {
                "type": "cursor.update",
                "user_id": event["user_id"],
                "x": event["x"],
                "y": event["y"],
            }
        )

    # --- DB helpers ---
    @database_sync_to_async
    def _user_can_join(self, user, project_id: int) -> bool:
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return False
        project = Project.objects.get(pk=project_id)
        return _user_in_project(user, project)

    @database_sync_to_async
    def _persist_message(self, project_id: int, sender, content: str):
        project = Project.objects.get(pk=project_id)
        thread = _get_or_create_project_chat(project)
        msg = thread.add_message(sender=sender, content=content)
        s = msg.sender
        return {
            "id": msg.id,
            "sender_id": s.id,
            "sender": (getattr(s, "name", None) or getattr(s, "username", "")),
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat(),
        }
