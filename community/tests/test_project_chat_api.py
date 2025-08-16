# tests/test_project_chat_api.py
import pytest
from django.urls import reverse
from community.models import Project, User

@pytest.mark.django_db
def test_post_message(client):
    user = User.objects.create_user(username="alice", password="pw")
    project = Project.objects.create(name="p1", creator=user)
    project.participants.add(user)

    url = url = reverse("community:project-chat-post", args=[project.id])

    resp = client.post(url, {"sender_id": user.id, "content": "hello"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "hello"
