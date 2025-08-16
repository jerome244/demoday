import pytest
from django.db import connection, transaction

@pytest.mark.django_db
def test_postgres_connection_and_version():
    # Django thinks this is Postgres
    assert connection.vendor == "postgresql"

    # The server reports itself as PostgreSQL
    with connection.cursor() as cur:
        cur.execute("SELECT version();")
        ver = cur.fetchone()[0]
    assert "PostgreSQL" in ver

@pytest.mark.django_db
def test_django_migrations_table_exists():
    # Sanity: schema was created by migrate
    tables = set(connection.introspection.table_names())
    assert "django_migrations" in tables

@pytest.mark.django_db
def test_crud_models_roundtrip():
    from django.contrib.auth import get_user_model
    from community.models import Project, ProjectFile

    User = get_user_model()

    u = User.objects.create_user(username="pg_tester", password="x")
    p = Project.objects.create(name="pgproj", creator=u)

    # Create a project file and read it back
    ProjectFile.objects.create(project=p, path="hello.py", content="print('hi')\n")
    assert Project.objects.count() == 1
    assert ProjectFile.objects.filter(project=p).count() == 1

    pf = ProjectFile.objects.get(project=p, path="hello.py")
    assert pf.content.strip() == "print('hi')"

@pytest.mark.django_db
def test_transaction_rollback():
    from django.contrib.auth import get_user_model
    from community.models import Project, ProjectFile

    User = get_user_model()
    u = User.objects.create_user(username="pg_tx", password="x")
    p = Project.objects.create(name="pgproj_tx", creator=u)

    before = ProjectFile.objects.filter(project=p).count()

    # Create inside an atomic block then force a rollback
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            ProjectFile.objects.create(project=p, path="boom.txt", content="boom")
            raise RuntimeError("force rollback")

    after = ProjectFile.objects.filter(project=p).count()
    assert after == before  # the insert rolled back

@pytest.mark.django_db
def test_raw_sql_roundtrip_with_params():
    # Simple parametrized SQL works
    with connection.cursor() as cur:
        cur.execute("SELECT %s::int + %s::int;", [2, 3])
        (val,) = cur.fetchone()
    assert val == 5
