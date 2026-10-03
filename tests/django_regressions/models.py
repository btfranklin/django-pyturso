"""Models for the selected Django regressions, with a separate app registry."""

from django.apps.registry import Apps
from django.db import models

regression_apps = Apps()


class Record(models.Model):
    objects: models.Manager["Record"] = models.Manager()
    name = models.CharField(max_length=100, unique=True, db_column="record_name")
    number = models.IntegerField(default=0)
    other = models.IntegerField(default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payload = models.JSONField(null=True)

    class Meta:
        app_label = "django_regressions"
        apps = regression_apps
        db_table = "django_regression_record"


class NamedRank(models.Model):
    objects: models.Manager["NamedRank"] = models.Manager()
    rank = models.IntegerField(unique=True, db_column="rank_value")
    name = models.CharField(max_length=100, db_column="display_name")

    class Meta:
        app_label = "django_regressions"
        apps = regression_apps
        db_table = "django_regression_named_rank"
