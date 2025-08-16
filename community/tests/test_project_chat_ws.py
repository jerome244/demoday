# community/tests/test_project_chat_ws.py
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from flowchart.asgi import application
from community.models import Project, User

pytestmark = pytest.mark.django_db(transaction=True)

@pytest.mark.asyncio
async def test_ws_chat_message(settings):
    # Make sure we use the in-memory channel layer in tests
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

    # Create user & project via sync_to_async (ORM is synchronous)
    user = await sync_to_async(User.objects.create_user)(
        username="bob", password="pw"
    )
    project = await sync_to_async(Project.objects.create)(
        name="proj", creator=user
    )
    # m2m add is also sync
    await sync_to_async(project.participants.add)(user)

    # JWT for your JwtQueryAuthMiddleware
    token = str(AccessToken.for_user(user))

    communicator = WebsocketCommunicator(
        application, f"/ws/chat/project/{project.id}/?token={token}"
    )
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "message", "content": "hi there"})

    msg = await communicator.receive_json_from()
    assert msg["type"] == "message"
    assert msg["content"] == "hi there"
    assert msg["sender"] == "bob"

    await communicator.disconnect()
