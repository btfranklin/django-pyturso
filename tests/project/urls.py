"""URLs for the integration project."""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path

from tests.project.models import Entry


def entry_title(request: HttpRequest) -> HttpResponse:
    entry = Entry.objects.get(pk=1)
    return HttpResponse(entry.title)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("entry-title/", entry_title),
]
