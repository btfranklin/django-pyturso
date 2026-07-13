"""Admin registrations for integration paths."""

from django.contrib import admin

from .models import Entry


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin[Entry]):
    list_display = ("title", "active")
    search_fields = ("title",)
