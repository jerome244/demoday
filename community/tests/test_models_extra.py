import io, zipfile
import pytest
from django.contrib.auth import get_user_model
from community.models import Project, PrivateMessage, Conversation

pytestmark = pytest.mark.django_db

def test_user_display_info_and_block_cycle(user):
    txt = user.display_info()
    assert str(user.id) in txt and user.email in txt
    user.block()
    user.refresh_from_db()
    assert user.blocked is True
    user.unblock()
    user.refresh_from_db()
    assert user.blocked is False

def test_project_text_files_tree_zip(project):
    project.add_text_file("README.md", "# readme")
    project.add_text_file("src/app.py", "print(1)")
    tree = set(project.project_tree())
    assert {"README.md","src/app.py"} <= tree
    # zip bytes roundtrip
    z = project.as_zip_bytes()
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        assert set(zf.namelist()) == tree

def test_project_like_unlike(project, user):
    assert "liked the project" in project.like(user)
    assert "already liked" in project.like(user)
    assert "unliked" in project.unlike(user)

def test_private_message_like_unlike(user, other_user):
    conv = Conversation.objects.create(user1=user, user2=other_user, title="DM")
    pm = PrivateMessage.objects.create(conversation=conv, sender=user, receiver=other_user, content="hi")
    assert "liked" in pm.like(other_user)
    assert "already liked" in pm.like(other_user)
    assert "unliked" in pm.unlike(other_user)
