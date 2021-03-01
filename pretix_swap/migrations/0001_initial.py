# Generated by Django 3.0.11 on 2021-03-01 02:33

import django.db.models.deletion
import i18nfield.fields
from django.db import migrations, models

import pretix_swap.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("pretixbase", "0174_merge_20201222_1031"),
    ]

    operations = [
        migrations.CreateModel(
            name="SwapRequest",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("state", models.CharField(default="r", max_length=1)),
                ("swap_type", models.CharField(max_length=1)),
                ("swap_method", models.CharField(default="f", max_length=1)),
                ("requested", models.DateTimeField(auto_now_add=True)),
                ("completed", models.DateTimeField(null=True)),
                (
                    "swap_code",
                    models.CharField(
                        default=pretix_swap.models.generate_swap_code, max_length=40
                    ),
                ),
                (
                    "partner",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="pretixbase.OrderPosition",
                    ),
                ),
                (
                    "partner_cart",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="pretixbase.CartPosition",
                    ),
                ),
                (
                    "position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="swap_states",
                        to="pretixbase.OrderPosition",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SwapGroup",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("name", i18nfield.fields.I18nCharField(max_length=255)),
                ("only_same_price", models.BooleanField(default=True)),
                (
                    "price_tolerance",
                    models.DecimalField(decimal_places=2, default=2, max_digits=10),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="swap_groups",
                        to="pretixbase.Event",
                    ),
                ),
                (
                    "left",
                    models.ManyToManyField(
                        related_name="_swapgroup_left_+", to="pretixbase.Item"
                    ),
                ),
                (
                    "right",
                    models.ManyToManyField(
                        related_name="_swapgroup_right_+", to="pretixbase.Item"
                    ),
                ),
            ],
        ),
    ]
