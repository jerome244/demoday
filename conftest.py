import pytest
from django.contrib.auth import get_user_model
from community.models import Project, Thread

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
