# community/tests/test_presence_ws.py
import asyncio
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken
from flowchart.asgi import application
from community.models import Project, User

pytestmark = pytest.mark.django_db(transaction=True)

async def recv_until(comm: WebsocketCommunicator, want: set[str], timeout: float = 3.0):
    """Receive frames until one of `want` types arrives, or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Did not receive any of {want} before timeout")
        msg = await comm.receive_json_from(timeout=remaining)
        if msg.get("type") in want:
            return msg
        # else: keep draining (presence.join / presence.roster / typing / etc.)

@pytest.mark.asyncio
async def test_presence_and_cursor(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    a = await sync_to_async(User.objects.create_user)(username="a", password="x")
    b = await sync_to_async(User.objects.create_user)(username="b", password="x")
    p = await sync_to_async(Project.objects.create)(name="p", creator=a)
    await sync_to_async(p.participants.add)(b)

    ca = WebsocketCommunicator(application, f"/ws/chat/project/{p.id}/?token={str(AccessToken.for_user(a))}")
    cb = WebsocketCommunicator(application, f"/ws/chat/project/{p.id}/?token={str(AccessToken.for_user(b))}")
    ok, _ = await ca.connect(); assert ok
    ok, _ = await cb.connect(); assert ok

    # Announce presence
    await ca.send_json_to({"type": "presence.hello"})
    await cb.send_json_to({"type": "presence.hello"})
    # Each side will first get a 'presence.roster' (and possibly 'presence.join' from the other)
    _ = await recv_until(ca, {"presence.roster"})
    _ = await recv_until(cb, {"presence.roster"})

    # Move A's cursor, B should eventually see 'cursor.update'
    await ca.send_json_to({"type": "cursor.move", "x": 0.25, "y": 0.75})
    msg = await recv_until(cb, {"cursor.update"}, timeout=3.0)
    assert 0 <= msg["x"] <= 1 and 0 <= msg["y"] <= 1

    await ca.disconnect(); await cb.disconnect()
