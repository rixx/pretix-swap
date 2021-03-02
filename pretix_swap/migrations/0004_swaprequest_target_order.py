# Generated by Django 3.0.11 on 2021-03-02 12:24

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0174_merge_20201222_1031"),
        ("pretix_swap", "0003_auto_20210302_1013"),
    ]

    operations = [
        migrations.AddField(
            model_name="swaprequest",
            name="target_order",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cancelation_request",
                to="pretixbase.Order",
            ),
        ),
    ]
