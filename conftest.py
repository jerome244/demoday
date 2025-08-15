import pytest, io, zipfile
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from community.models import Project, Thread, Conversation

@pytest.fixture
def user(db):
    U = get_user_model()
    return U.objects.create_user(username="alice", email="alice@example.com", password="pass1234", name="Alice")

@pytest.fixture
def other_user(db):
    U = get_user_model()
    return U.objects.create_user(username="bob", email="bob@example.com", password="pass1234", name="Bob")

@pytest.fixture
def project(db, user):
    return Project.objects.create(name="DemoProject", description="Demo", creator=user)

@pytest.fixture
def thread(db, user, other_user):
    t = Thread.objects.create(title="General")
    t.participants.add(user, other_user)
    return t

@pytest.fixture
def admin_user(db):
    U = get_user_model()
    return U.objects.create_superuser(username="admin", email="admin@example.com", password="adminpass", name="Admin")

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def access_token(client, user):
    # obtain JWT for normal user
    r = client.post("/api/auth/token/", {"username": user.username, "password": "pass1234"}, content_type="application/json")
    return r.json()["access"]

@pytest.fixture
def admin_access_token(client, admin_user):
    r = client.post("/api/auth/token/", {"username": admin_user.username, "password": "adminpass"}, content_type="application/json")
    return r.json()["access"]

@pytest.fixture
def thread_with_participants(db, user, other_user):
    t = Thread.objects.create(title="t-v2")
    t.participants.add(user, other_user)
    return t

@pytest.fixture
def conversation_between(db, user, other_user):
    return Conversation.objects.create(user1=user, user2=other_user, title="DM v2")
