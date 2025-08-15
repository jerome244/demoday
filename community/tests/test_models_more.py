import io, zipfile, jwt, pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from community.models import Conversation, Project, ProjectFile, Notification, Thread, Message

pytestmark = pytest.mark.django_db

def test_conversation_add_message_rejects_non_participant(user, other_user):
    outsider = get_user_model().objects.create_user("eve", email="eve@example.com", password="x")
    conv = Conversation.objects.create(user1=user, user2=other_user, title="DM")
    with pytest.raises(ValueError):
        conv.add_message(sender=outsider, content="nope")

def test_project_delete_with_notifications_sends(project, user, other_user):
    project.participants.add(other_user)
    name = project.name
    project.delete_with_notifications()
    assert not Project.objects.filter(name=name).exists()
    # creator notified
    assert "deleted" in user.notifications.latest("created_at").message.lower()
    # participant notified
    assert "deleted" in other_user.notifications.latest("created_at").message.lower()

def test_add_remove_participant_edges(project, user, other_user):
    # already participant
    msg = project.add_participant(user)
    assert "already a participant" in msg
    # remove non-participant
    msg2 = project.remove_participant(other_user)  # not yet added
    assert "is not a participant" in msg2

def test_user_generate_jwt_decodes(user):
    token = user.generate_jwt()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
    assert payload["id"] == user.id and payload["email"] == user.email

def test_project_file_helpers(project):
    project.add_text_file("README.md", "# readme")
    assert project.get_file_content("README.md") == "# readme"
    # __str__
    pf = ProjectFile.objects.get(project=project, path="README.md")
    assert project.name in str(pf)

def test_str_helpers_and_messages(user, other_user):
    t = Thread.objects.create(title="General")
    t.participants.add(user, other_user)
    msg = Message.objects.create(thread=t, sender=user, content="hello world")
    # __str__ for Thread/Message/Notification
    assert str(t) == "General"
    assert "hello" in str(msg).lower()
    Notification.objects.create(user=user, message="sample note")
    assert "sample note" in str(Notification.objects.latest("created_at"))
