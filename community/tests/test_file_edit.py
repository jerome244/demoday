import json
import pytest
from django.contrib.auth import get_user_model
from community.models import Project, ProjectFile

@pytest.mark.django_db
def test_project_file_detail_get_and_put(client):
    User = get_user_model()
    user = User.objects.create_user(username="demo", password="demo")
    project = Project.objects.create(name="DemoProj", creator=user)
    pf = ProjectFile.objects.create(
        project=project,
        path="src/app.py",
        content='print("hello")\n'
    )

    url = f"/api/community/projects/{project.id}/files/{pf.path}/"

    # --- GET ---
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"].startswith("print")

    # --- PUT (update content) ---
    new_code = 'print("changed!")\n'
    resp2 = client.put(
        url,
        data=json.dumps({"content": new_code}),
        content_type="application/json"
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["content"] == new_code

    # confirm DB was updated
    pf.refresh_from_db()
    assert pf.content == new_code


@pytest.mark.django_db
def test_bulk_fetch(client):
    User = get_user_model()
    user = User.objects.create_user(username="bob", password="pw")
    project = Project.objects.create(name="BulkProj", creator=user)
    ProjectFile.objects.create(project=project, path="a.py", content="a=1")
    ProjectFile.objects.create(project=project, path="b/c.py", content="c=3")

    url = f"/api/community/projects/{project.id}/files/bulk/?paths=a.py,b/c.py,missing.py"
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()["files"]

    assert data["a.py"]["found"] is True
    assert "a=1" in data["a.py"]["content"]

    assert data["b/c.py"]["found"] is True
    assert "c=3" in data["b/c.py"]["content"]

    assert data["missing.py"]["found"] is False
