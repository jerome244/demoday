# community/presence_repo_sql.py
from django.utils import timezone
from datetime import timedelta
from .models import Presence, Project

def upsert_presence(project_id: int, user_id: int, data: dict):
    Presence.objects.update_or_create(
        project=Project.objects.get(pk=project_id),
        user_id=user_id,
        defaults={**data, "updated_at": timezone.now()},
    )

def get_presence_map(project_id: int) -> dict[int, dict]:
    rows = (Presence.objects
            .filter(project_id=project_id)
            .values("user_id", "name", "color", "x", "y", "updated_at"))
    return {r["user_id"]: r for r in rows}

def remove_presence(project_id: int, user_id: int):
    Presence.objects.filter(project_id=project_id, user_id=user_id).delete()

def cleanup_stale(seconds: int = 300):
    cutoff = timezone.now() - timedelta(seconds=seconds)
    Presence.objects.filter(updated_at__lt=cutoff).delete()
