# Generated by Django 3.0.11 on 2021-03-01 00:45

import django.db.models.deletion
from django.db import migrations, models

import pretix_swap.models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0174_merge_20201222_1031"),
        ("pretix_swap", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="swapstate",
            name="swap_code",
            field=models.CharField(
                default=pretix_swap.models.generate_swap_code, max_length=40
            ),
        ),
        migrations.AddField(
            model_name="swapstate",
            name="swap_method",
            field=models.CharField(default="s", max_length=1),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="swapstate",
            name="swap_type",
            field=models.CharField(default="f", max_length=1),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="swapstate",
            name="position",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="swap_states",
                to="pretixbase.OrderPosition",
            ),
        ),
        migrations.AlterField(
            model_name="swapstate",
            name="state",
            field=models.CharField(default="r", max_length=1),
        ),
    ]
