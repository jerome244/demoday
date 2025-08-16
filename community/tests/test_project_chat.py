# community/tests/test_project_chat.py

import json
import pytest
from django.contrib.auth import get_user_model
from community.models import Project

@pytest.mark.django_db
def test_project_chat_flow(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner", password="pw")
    member = User.objects.create_user(username="member", password="pw")
    outsider = User.objects.create_user(username="x", password="pw")

    project = Project.objects.create(name="ChatProj", creator=owner)
    project.participants.add(member)

    # Login as an allowed user for GET endpoints
    client.force_login(owner)

    # info creates/returns the chat thread and adds participants
    r_info = client.get(f"/api/community/projects/{project.id}/chat/")
    assert r_info.status_code == 200
    thread_id = r_info.json()["thread_id"]
    assert thread_id

    # post by member (no login switch needed because view validates sender_id membership)
    r_post1 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data=json.dumps({"sender_id": member.id, "content": "hi owner"}),
        content_type="application/json",
    )
    assert r_post1.status_code == 200

    # post by owner
    r_post2 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data={"sender_id": owner.id, "content": "hi member"},
    )
    assert r_post2.status_code == 200

    # outsider should be forbidden (sender not in project)
    r_post3 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data={"sender_id": outsider.id, "content": "let me in"},
    )
    assert r_post3.status_code == 403

    # list messages (as logged-in owner)
    r_list = client.get(f"/api/community/projects/{project.id}/chat/messages/?page=1&per_page=10")
    assert r_list.status_code == 200
    data = r_list.json()
    assert data["count"] >= 2
    assert len(data["results"]) >= 2

    # incremental fetch using after_id of the first message
    first_id = data["results"][-1]["id"]
    r_inc = client.get(f"/api/community/projects/{project.id}/chat/messages/?after_id={first_id}")
    assert r_inc.status_code == 200
    inc = r_inc.json()["results"]
    assert all(m["id"] > first_id for m in inc)
