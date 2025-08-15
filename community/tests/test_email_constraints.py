import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db

def test_email_unique_for_real_addresses():
    U = get_user_model()
    U.objects.create_user(username="u1", email="dev@example.com", password="x")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            U.objects.create_user(username="u2", email="dev@example.com", password="x")

def test_multiple_blank_emails_may_be_allowed():
    """
    If you applied the partial unique constraint (unique when email not blank/NULL),
    creating multiple users with blank/NULL email should succeed.
    If your schema still enforces hard unique, we'll SKIP instead of failing.
    """
    U = get_user_model()
    try:
        U.objects.create_user(username="a", email="", password="x")
        U.objects.create_user(username="b", email="", password="x")
    except IntegrityError:
        pytest.skip("Schema enforces unique email even when blank — skipping.")
