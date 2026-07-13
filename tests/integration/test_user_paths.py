"""Django contrib, form, session, and admin integration paths."""

from typing import Any

import pytest
from django.contrib.auth import authenticate
from django.urls import reverse

from tests.project.forms import EntryForm
from tests.project.models import Entry


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_auth_sessions_forms_and_admin(client: Any, django_user_model: Any) -> None:
    user = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="secret"
    )
    authenticated = authenticate(username="admin", password="secret")
    assert authenticated == user

    session = client.session
    session["django-pyturso"] = "verified"
    session.save()
    assert client.session["django-pyturso"] == "verified"

    form = EntryForm({"title": "From form", "active": True})
    assert form.is_valid(), form.errors
    entry = form.save()
    assert Entry.objects.get(pk=entry.pk).title == "From form"

    assert client.login(username="admin", password="secret")
    assert client.get(reverse("admin:index")).status_code == 200
    assert client.get(reverse("admin:pyturso_test_project_entry_changelist")).status_code == 200
    response = client.post(
        reverse("admin:pyturso_test_project_entry_add"),
        {"title": "From admin", "active": "on", "_save": "Save"},
    )
    assert response.status_code == 302
    assert Entry.objects.filter(title="From admin").exists()
