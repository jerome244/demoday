import math
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from community.consumers import ProjectChatConsumer
from community.models import Project
from community import presence_repo


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


async def _connect_consumer(user, project_id: int):
    app = ProjectChatConsumer.as_asgi()
    comm = WebsocketCommunicator(app, "/ws/anything/")
    comm.scope["user"] = user
    comm.scope["url_route"] = {"kwargs": {"project_id": project_id}}
    connected, _ = await comm.connect()
    assert connected is True
    return comm


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_presence_roster_join_and_cursor_updates(settings):
    User = get_user_model()

    # Setup in sync world
    def _setup_sync():
        a = User.objects.create_user(username="alice", password="x")
        b = User.objects.create_user(username="bob", password="x")
        p = Project.objects.create(name="pres-test", creator=a)
        p.participants.add(b)
        return a.pk, b.pk, p.pk

    a_id, b_id, project_id = await sync_to_async(_setup_sync)()
    a = await sync_to_async(User.objects.get)(pk=a_id)
    b = await sync_to_async(User.objects.get)(pk=b_id)

    # Clean Mongo presence
    await presence_repo.remove_presence(project_id, a_id)
    await presence_repo.remove_presence(project_id, b_id)

    # A connects + hello
    comm_a = await _connect_consumer(a, project_id)
    await comm_a.send_json_to({"type": "presence.hello"})
    msg = await comm_a.receive_json_from(timeout=1)
    assert msg["type"] == "presence.roster"
    assert not any(u["user_id"] == a_id for u in msg["users"])

    # Drain any self-join echo for A (optional depending on consumer)
    try:
        m2 = await comm_a.receive_json_from(timeout=0.2)
        if m2.get("type") == "presence.join" and m2.get("user_id") == a_id:
            pass  # ignore self-join
        else:
            # If it's something else, we can push it back by asserting it later; for now ignore.
            pass
    except Exception:
        # No extra message — fine.
        pass

    # B connects + hello
    comm_b = await _connect_consumer(b, project_id)
    await comm_b.send_json_to({"type": "presence.hello"})
    msg_b = await comm_b.receive_json_from(timeout=1)
    assert msg_b["type"] == "presence.roster"
    ids_b = {u["user_id"] for u in msg_b["users"]}
    assert a_id in ids_b

    # A should (eventually) receive presence.join for B
    found_b_join = False
    for _ in range(5):
        msg_a = await comm_a.receive_json_from(timeout=1)
        if msg_a.get("type") == "presence.join" and msg_a.get("user_id") == b_id:
            found_b_join = True
            break
        # Ignore any other late messages (e.g., self-join, typing, etc.)
    assert found_b_join, "Did not receive presence.join for B"

    # Presence has both
    pres = await presence_repo.get_presence_map(project_id)
    assert a_id in pres and b_id in pres

    # B moves cursor -> A sees update
    x, y = 0.33, 0.77
    await comm_b.send_json_to({"type": "cursor.move", "x": x, "y": y})
    upd = await comm_a.receive_json_from(timeout=1)
    assert upd["type"] == "cursor.update"
    assert upd["user_id"] == b_id
    assert math.isclose(upd["x"], x, rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(upd["y"], y, rel_tol=1e-6, abs_tol=1e-6)

    # Disconnect B; A sees leave
    await comm_b.disconnect()
    leave = await comm_a.receive_json_from(timeout=1)
    assert leave["type"] == "presence.leave"
    assert leave["user_id"] == b_id

    await comm_a.disconnect()
    pres_after = await presence_repo.get_presence_map(project_id)
    assert a_id not in pres_after and b_id not in pres_after
