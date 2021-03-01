import string
from django.db import models
from django.utils.crypto import get_random_string
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


def generate_swap_code():
    return get_random_string(
        length=20, allowed_chars=string.ascii_lowercase + string.digits
    )


class SwapState(models.Model):
    class SwapStates(models.TextChoices):
        REQUESTED = "r"
        COMPLETED = "c"

    class SwapTypes(models.TextChoices):
        SWAP = "s"
        CANCELATION = "c"

    class SwapMethods(models.TextChoices):
        FREE = "f", _("I know who to swap with.")
        SPECIFIC = "s", _("Give my place to the next person in line.")

    position = models.ForeignKey(
        "pretixbase.OrderPosition", related_name="swap_states", on_delete=models.CASCADE
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

    state = models.CharField(
        max_length=1, choices=SwapStates.choices, default=SwapStates.REQUESTED
    )
    swap_type = models.CharField(max_length=1, choices=SwapTypes.choices)
    swap_method = models.CharField(max_length=1, choices=SwapMethods.choices)
    swap_code = models.CharField(max_length=40, default=generate_swap_code)

    objects = ScopedManager(organizer="position__order__event__organizer")

    def get_notification(self):
        texts = {
            self.SWAP_REQUESTED: _(
                "You have requested to swap this prodcut. Please wait until somebody requests a matching swap."
            ),
            self.SWAP_SPECIFIC_REQUESTED: _(
                "You have requested to swap this product with somebody specific. Please wait until they enter the swap code that you have given them."
            ),
            self.SWAP_COMPLETED: _("You have completed the swap of this product."),
            self.CANCELATION_REQUESTED: _(
                "You have requested to cancel this product. Please wait until somebody from the waiting list orders and pays a matching product."
            ),
            self.CANCELATION_SPECIFIC_REQUESTED: _(
                "You have requested to cancel this product and give your place to somebody else. Please wait until they have completed their registration."
            ),
            self.CANCELATION_COMPLETED: _(
                "You have completed the cancelation of this position."
            ),
        }
        return texts[self.state]

    def get_notification_actions(self):
        if self.state in [self.SWAP_COMPLETED, self.CANCELATION_COMPLETED]:
            return []
        if self.partner or self.partner_cart:
            return ["view"]
        return ["view", "abort"]
