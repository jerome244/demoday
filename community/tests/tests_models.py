import io, zipfile
import pytest
from community.models import Thread

def test_user_block_unblock(db, user):
    assert user.blocked is False
    msg1 = user.block()
    user.refresh_from_db()
    assert user.blocked is True
    assert "blocked" in msg1
    msg2 = user.unblock()
    user.refresh_from_db()
    assert user.blocked is False
    assert "unblocked" in msg2
    # Notifications were created
    assert user.notifications.count() >= 2

def test_thread_add_message_sends_notifications(db, user, other_user):
    t = Thread.objects.create(title="General")
    t.participants.add(user, other_user)
    t.add_message(sender=user, content="hello pytest")
    note = other_user.notifications.latest("created_at")
    assert "hello pytest" in note.message

def test_project_zip_ingest(db, project):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "hi")
        zf.writestr("src/b.py", "print(1)")
    buf.seek(0)
    count = project.ingest_zip(buf)
    assert count == 2
    assert project.files.count() == 2
