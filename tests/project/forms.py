"""Model forms for integration paths."""

from django import forms

from .models import Entry


class EntryForm(forms.ModelForm[Entry]):
    class Meta:
        model = Entry
        fields = ["title", "active"]
