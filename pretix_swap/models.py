import string
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
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

    objects = ScopedManager(organizer="event__organizer")


def generate_swap_code():
    return get_random_string(
        length=20, allowed_chars=string.ascii_lowercase + string.digits
    )


class SwapRequest(models.Model):
    class States(models.TextChoices):
        REQUESTED = "r"
        COMPLETED = "c"

    class Types(models.TextChoices):
        SWAP = "s"
        CANCELATION = "c"

    class Methods(models.TextChoices):
        FREE = "f", _("I know who to swap with.")
        SPECIFIC = "s", _("Give my place to the next person in line.")

    state = models.CharField(
        max_length=1, choices=States.choices, default=States.REQUESTED
    )
    swap_type = models.CharField(max_length=1, choices=Types.choices)
    swap_method = models.CharField(
        max_length=1,
        choices=Methods.choices,
        default=Methods.FREE,
        verbose_name=_("How do you want to handle the ticket?"),
    )

    position = models.ForeignKey(
        "pretixbase.OrderPosition", related_name="swap_states", on_delete=models.CASCADE
    )
    target_item = models.ForeignKey(
        "pretixbase.Item",
        related_name="+",
        on_delete=models.CASCADE,
        null=True,
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

    @cached_property
    def event(self):
        return self.position.order.event

    def get_notification(self):
        texts = {
            (self.Types.SWAP, self.States.REQUESTED, self.Methods.FREE): _(
                "You have requested to swap this prodcut. Please wait until somebody requests a matching swap."
            ),
            (self.Types.SWAP, self.States.REQUESTED, self.Methods.SPECIFIC,): _(
                "You have requested to swap this product with somebody specific. Please wait until they enter the swap code that you have given them."
            ),
            (self.Types.SWAP, self.States.COMPLETED, self.Methods.FREE): _(
                "You have completed the swap of this product."
            ),
            (self.Types.SWAP, self.States.COMPLETED, self.Methods.SPECIFIC,): _(
                "You have completed the swap of this product with your chosen partner."
            ),
            (self.Types.CANCELATION, self.States.REQUESTED, self.Methods.FREE,): _(
                "You have requested to cancel this product. Please wait until somebody from the waiting list orders and pays a matching product."
            ),
            (self.Types.CANCELATION, self.States.REQUESTED, self.Methods.SPECIFIC,): _(
                "You have requested to cancel this product and give your place to somebody else. Please wait until they have completed their registration."
            ),
            (
                self.Types.CANCELATION,
                self.States.COMPLETED,
                self.Methods.FREE,
            ): _("You have completed the cancelation of this position."),
            (self.Types.CANCELATION, self.States.COMPLETED, self.Methods.SPECIFIC,): _(
                "You have completed the cancelation of this position with your chosen partner."
            ),
        }
        return texts[(self.swap_type, self.state, self.swap_method)]

    def get_notification_actions(self):
        if self.state == self.States.COMPLETED:
            return []
        if self.partner or self.partner_cart:
            return []  # ["view"]
        return ["abort"]  # ["view", "abort"]

    def swap_with(self, other):
        # TODO the actual swap method
        # Make sure AGAIN that the state is alright, because timings
        # Make the swap
        # Send notification
        # Set state to complete
        # Log what is happening
        pass

    def attempt_swap(self):
        """Find a swap partner.
        Do not use for bulk action – use utils.match_open_swap_requests instead!"""
        if self.swap_method != self.Methods.FREE:
            return

        from .utils import get_swappable_items

        items = get_swappable_items(self.position.item)
        other = SwapRequest.objects.filter(
            state=SwapRequest.States.REQUESTED,
            swap_method=SwapRequest.Methods.FREE,
            swap_type=SwapRequest.Types.SWAP,
            position__order__event_id=self.event.pk,
            position__item__in=items,
        ).first()
        if other:
            self.swap_with(other)

    def cancel_for(self, other):
        # TODO the actual cancel method
        # Log what is happening
        # Do the thing
        # Send notification
        # Set state to complete
        # Make sure AGAIN that the state is alright, because timings
        pass

    def attempt_cancelation(self):
        # TODO attempt to find a cancelation target
        if self.swap_method != self.Methods.FREE:
            return
