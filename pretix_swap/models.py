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

    state = models.CharField(
        max_length=1, choices=SwapStates.choices, default=SwapStates.REQUESTED
    )
    swap_type = models.CharField(max_length=1, choices=SwapTypes.choices)
    swap_method = models.CharField(
        max_length=1,
        choices=SwapMethods.choices,
        default=SwapMethods.FREE,
        verbose_name=_("How do you want to handle the ticket?"),
    )

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

    swap_code = models.CharField(max_length=40, default=generate_swap_code)

    objects = ScopedManager(organizer="position__order__event__organizer")

    def get_notification(self):
        texts = {
            (self.SwapTypes.SWAP, self.SwapStates.REQUESTED, self.SwapMethods.FREE): _(
                "You have requested to swap this prodcut. Please wait until somebody requests a matching swap."
            ),
            (
                self.SwapTypes.SWAP,
                self.SwapStates.REQUESTED,
                self.SwapMethods.SPECIFIC,
            ): _(
                "You have requested to swap this product with somebody specific. Please wait until they enter the swap code that you have given them."
            ),
            (self.SwapTypes.SWAP, self.SwapStates.COMPLETED, self.SwapMethods.FREE): _(
                "You have completed the swap of this product."
            ),
            (
                self.SwapTypes.SWAP,
                self.SwapStates.COMPLETED,
                self.SwapMethods.SPECIFIC,
            ): _(
                "You have completed the swap of this product with your chosen partner."
            ),
            (
                self.SwapTypes.CANCELATION,
                self.SwapStates.REQUESTED,
                self.SwapMethods.FREE,
            ): _(
                "You have requested to cancel this product. Please wait until somebody from the waiting list orders and pays a matching product."
            ),
            (
                self.SwapTypes.CANCELATION,
                self.SwapStates.REQUESTED,
                self.SwapMethods.SPECIFIC,
            ): _(
                "You have requested to cancel this product and give your place to somebody else. Please wait until they have completed their registration."
            ),
            (
                self.SwapTypes.CANCELATION,
                self.SwapStates.COMPLETED,
                self.SwapMethods.FREE,
            ): _("You have completed the cancelation of this position."),
            (
                self.SwapTypes.CANCELATION,
                self.SwapStates.COMPLETED,
                self.SwapMethods.SPECIFIC,
            ): _(
                "You have completed the cancelation of this position with your chosen partner."
            ),
        }
        return texts[(self.swap_type, self.state, self.swap_method)]

    def get_notification_actions(self):
        if self.state == self.SwapStates.COMPLETED:
            return []
        if self.partner or self.partner_cart:
            return []  # ["view"]
        return ["abort"]  # ["view", "abort"]

    def swap_with(self, other):
        # TODO the actual swap method
        # Log what is happening
        # Make the swap
        # Send notification
        # Set state to complete
        pass

    def attempt_swap(self):
        # TODO attempt to find a swap partner
        # Must not be in specific mode
        if self.swap_method != self.SwapMethods.FREE:
            return
        # select items that would fit
        # and note the price matching setting

    def cancel_for(self, other):
        # TODO the actual cancel method
        # Log what is happening
        # Do the thing
        # Send notification
        # Set state to complete
        pass

    def attempt_cancelation(self):
        # TODO attempt to find a cancelation target
        if self.swap_method != self.SwapMethods.FREE:
            return
