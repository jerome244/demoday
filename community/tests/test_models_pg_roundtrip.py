import io
import zipfile
import pytest
from django.db import transaction
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_user_creation_and_password():
    User = get_user_model()
    u = User.objects.create_user(username="alice", email="a@example.com", password="secret123")
    assert u.id is not None
    assert u.check_password("secret123") is True
    assert u.check_password("wrong") is False

@pytest.mark.django_db
def test_project_and_files_save_and_cascade():
    from community.models import Project, ProjectFile

    User = get_user_model()
    u = User.objects.create_user(username="bob", password="x")

    p = Project.objects.create(name="demo", creator=u)
    f1 = ProjectFile.objects.create(project=p, path="a.py", content="print(1)\n")
    f2 = ProjectFile.objects.create(project=p, path="dir/b.py", content="print(2)\n")

    # saved correctly
    assert Project.objects.count() == 1
    assert ProjectFile.objects.filter(project=p).count() == 2

    # update content and save
    f1.content = "print('updated')\n"
    f1.save()
    assert ProjectFile.objects.get(pk=f1.pk).content.strip() == "print('updated')"

    # deleting project cascades to files
    p.delete()
    assert Project.objects.count() == 0
    assert ProjectFile.objects.count() == 0

@pytest.mark.django_db
def test_ingest_zip_and_as_zip_bytes_roundtrip():
    from community.models import Project, ProjectFile

    User = get_user_model()
    u = User.objects.create_user(username="charlie", password="x")
    p = Project.objects.create(name="zipper", creator=u)

    # build a small zip in-memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("app/main.py", "def run():\n    return 1\n")
        z.writestr("static/index.html", "<div id='root'></div>\n")
    data = io.BytesIO(buf.getvalue())

    # ingest and verify files created
    count = p.ingest_zip(data)
    assert count == 2
    paths = set(ProjectFile.objects.filter(project=p).values_list("path", flat=True))
    assert paths == {"app/main.py", "static/index.html"}

    # export back to zip and verify filenames inside
    out = p.as_zip_bytes()
    with zipfile.ZipFile(io.BytesIO(out), "r") as z:
        names = set(z.namelist())
    assert {"app/main.py", "static/index.html"}.issubset(names)

@pytest.mark.django_db
def test_transaction_rollback_does_not_persist_partial_writes():
    from community.models import Project, ProjectFile

    User = get_user_model()
    u = User.objects.create_user(username="dana", password="x")
    p = Project.objects.create(name="tx", creator=u)

    before = ProjectFile.objects.filter(project=p).count()
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            ProjectFile.objects.create(project=p, path="boom.txt", content="boom")
            # Any exception should rollback the insert above
            raise RuntimeError("force rollback")

    after = ProjectFile.objects.filter(project=p).count()
    assert after == before

@pytest.mark.django_db
def test_get_or_create_project_chat_thread_and_membership():
    """Uses the helper from views to ensure a single deterministic chat thread is created and membership set."""
    from community.models import Project
    from community.views import _get_or_create_project_chat

    User = get_user_model()
    u = User.objects.create_user(username="eve", password="x")
    p = Project.objects.create(name="chatty", creator=u)

    t1 = _get_or_create_project_chat(p)
    t2 = _get_or_create_project_chat(p)  # idempotent

    assert t1.id == t2.id
    # creator should be a participant
    user_ids = set(t1.participants.values_list("id", flat=True))
    assert u.id in user_ids
