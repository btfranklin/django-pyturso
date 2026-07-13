"""Representative models for backend integration tests."""

import uuid

from django.db import models


class Entry(models.Model):
    title = models.CharField(max_length=200)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = "pyturso_test_project"


class ScalarValues(models.Model):
    date_value = models.DateField()
    datetime_value = models.DateTimeField()
    time_value = models.TimeField()
    decimal_value = models.DecimalField(max_digits=12, decimal_places=4)
    duration_value = models.DurationField()
    boolean_value = models.BooleanField()
    uuid_value = models.UUIDField(default=uuid.uuid4)
    json_value = models.JSONField()
    binary_value = models.BinaryField(null=True)

    class Meta:
        app_label = "pyturso_test_project"
