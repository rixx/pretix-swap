from django.db import models
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField


class SwapGroup(models.Model):
    event = models.ForeignKey(
        "pretixbase.Event", related_name="swap_groups", on_delete=models.CASCADE
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Group name"),
    )

    left = models.ManyToManyField(
        "pretixbase.Item", blank=True, related_name="+", verbose_name=_("Group A")
    )
    right = models.ManyToManyField(
        "pretixbase.Item", blank=True, related_name="+", verbose_name=_("Group B")
    )

    only_same_price = models.BooleanField(
        default=True, verbose_name=_("Allow only swaps between equal priced items")
    )
    price_tolerance = models.DecimalField(
        default=2,
        decimal_places=2,
        max_digits=10,
        verbose_name=_("Price tolerance"),
        help_text=_("Allow this much tolerance when comparing prices"),
    )

    objects = ScopedManager(organizer="event__organizer")


class SwapState(models.Model):
    class SwapStates(models.TextChoices):
        SWAP_REQUESTED = "sr"
        SWAP_SPECIFIC_REQUESTED = "ss"
        SWAP_COMPLETED = "sc"

        CANCELATION_REQUESTED = "cr"
        CANCELATION_SPECIFIC_REQUESTED = "cs"
        CANCELATION_COMPLETED = "cc"

    position = models.ForeignKey(
        "pretixbase.OrderPosition", related_name="swap_state", on_delete=models.CASCADE
    )
    partner = models.ForeignKey(
        "pretixbase.OrderPosition",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
    )
    partner_cart = models.ForeignKey(
        "pretixbase.CartPosition",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
    )  # Cancellations and swaps can go towards cartpositions instead of orderpositions

    requested = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(null=True)

    state = models.CharField(max_length=2, choices=SwapStates.choices)

    objects = ScopedManager(organizer="position__order__event__organizer")
