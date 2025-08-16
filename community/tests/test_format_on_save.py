# community/tests/test_format_on_save.py
import json, pytest
from django.urls import reverse
from community.models import Project, User, ProjectFile

pytestmark = pytest.mark.django_db

def test_python_format_on_save(client, monkeypatch):
    u = User.objects.create_user(username="a", password="x")
    p = Project.objects.create(name="p", creator=u)
    # seed a .py file
    ProjectFile.objects.create(project=p, path="main.py", content="x=1\n")

    url = reverse("community:project-file-detail", args=[p.id, "main.py"])
    messy = "def  f (  ):\n    return  (1+2)\n"
    r = client.put(url + "?format=1", data=json.dumps({"content": messy}),
                   content_type="application/json")
    assert r.status_code == 200
    data = r.json()
    assert data["saved"] is True
    assert data.get("tool") in ("black", "none")  # black if available
    # If black is present, it should normalize spaces around parens
    if data["tool"] == "black":
        assert "def f()" in data["content"]
