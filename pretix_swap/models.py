import string
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField
from pretix.base.services.orders import OrderChangeManager, OrderError, cancel_order

from .utils import can_be_canceled, can_be_swapped


class SwapGroup(models.Model):
    class Types(models.TextChoices):
        SWAP = "s", _("Swap")
        CANCELATION = "c", _("Cancelation")

    event = models.ForeignKey(
        "pretixbase.Event", related_name="swap_groups", on_delete=models.CASCADE
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Group name"),
    )
    swap_type = models.CharField(
        max_length=1, choices=Types.choices, verbose_name=_("Group type")
    )

    items = models.ManyToManyField(
        "pretixbase.Item",
        blank=True,
        related_name="+",
        verbose_name=_("Products"),
        help_text=_(
            "Settings apply to all selected items. Every swap or cancelation can only take "
            "place with the exact same item in both orders. For swaps, the event date is "
            "the only difference, for cancelations, even the event date needs to be the same. "
            "Leave empty to permit all items."
        ),
    )
    subevents = models.ManyToManyField(
        "pretixbase.SubEvent",
        blank=True,
        related_name="+",
        verbose_name=_("Subevents"),
        help_text=_("For swaps, tickets can be swapped between all selected events."),
    )

    objects = ScopedManager(organizer="event__organizer")


def generate_swap_code():
    return get_random_string(
        length=20, allowed_chars=string.ascii_lowercase + string.digits
    )


class SwapApproval(models.Model):
    order = models.OneToOneField(
        "pretixbase.Order", related_name="swap_approval", on_delete=models.CASCADE
    )  # TODO: move to OrderPosition once we have multiple tickets per order, and change `approve_orders()`
    approved_for_cancelation_request = models.BooleanField(
        default=True
    )  # Currently always True


class SwapRequest(models.Model):
    class States(models.TextChoices):
        REQUESTED = "r"
        COMPLETED = "c"

    class Types(models.TextChoices):
        SWAP = "s"
        CANCELATION = "c"

    class Methods(models.TextChoices):
        FREE = "f", _("Give my place to the next person in line.")
        SPECIFIC = "s", _("I know who to swap with.")

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
    target_subevent = models.ForeignKey(
        "pretixbase.SubEvent",
        related_name="+",
        on_delete=models.CASCADE,
        null=True,  # Only nullable for legacy reasons, should never be null
    )
    # WARNING: this works only as long as the waiting list allows only one item per pending order  # Used on specific (non-free) cancelation requests
    target_order = models.ForeignKey(
        "pretixbase.Order",
        related_name="cancelation_request",
        on_delete=models.CASCADE,
        null=True,
    )
    partner = models.ForeignKey(  # Only set on completed swaps. Not used except for auditability.
        "self",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
    )

    requested = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(null=True)

    swap_code = models.CharField(max_length=40, default=generate_swap_code)

    objects = ScopedManager(organizer="position__order__event__organizer")

    @cached_property
    def event(self):
        return self.position.order.event

    def get_notification(self):
        texts = {
            (self.Types.SWAP, self.States.REQUESTED, self.Methods.FREE): str(
                _(
                    "You have requested to swap this product. Please wait until somebody with a "
                    "matching ticket ({self.target_subevent}) requests a matching swap."
                )
            ).format(self=self),
            (self.Types.SWAP, self.States.REQUESTED, self.Methods.SPECIFIC,): str(
                _(
                    "You have requested to swap this product with somebody specific ({self.target_subevent}). "
                    "Please wait until they enter the swap code that you have given them."
                )
            ).format(self=self),
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

    def swap_with(self, other):
        if not self.event.settings.swap_orderpositions:
            raise Exception("Order position swapping is currently not allowed")

        my_item = self.position.item
        my_variation = self.position.variation
        my_subevent = self.position.subevent
        other_item = other.position.item
        other_variation = other.position.variation
        other_subevent = other.position.subevent

        if not (my_item == other_item):
            raise Exception(f"Items do not match: {my_item} vs {other_item}.")
        if not (my_variation == other_variation):
            raise Exception(
                f"Item variations do not match: {my_variation} vs {other_variation}."
            )
        if my_subevent == other_subevent:
            raise Exception("Can't swap within the same subevent.")
        if not can_be_swapped(self.event, my_item, my_subevent, other_subevent):
            raise Exception("This swap is currently not allowed.")

        my_change_manager = OrderChangeManager(order=self.position.order)
        other_change_manager = OrderChangeManager(order=other.position.order)

        # Make sure AGAIN that the state is alright, because timings
        self.refresh_from_db()
        other.refresh_from_db()
        if self.state != self.States.REQUESTED or other.state != self.States.REQUESTED:
            raise Exception("Both requests have to be in the 'requesting' state.")
        if not self.position.price == other.position.price:
            raise Exception("Both requests have to have the same price.")
        my_change_manager.change_item_and_subevent(
            position=self.position,
            item=my_item,
            variation=my_variation,
            subevent=other_subevent,
        )
        other_change_manager.change_item_and_subevent(
            position=other.position,
            item=my_item,
            variation=my_variation,
            subevent=my_subevent,
        )
        my_change_manager.commit()
        other_change_manager.commit()
        self.state = self.States.COMPLETED
        self.partner = other
        self.save()
        other.state = self.States.COMPLETED
        other.partner = self
        other.save()
        self.position.order.log_action(
            "pretix_swap.swap.complete",
            data={
                "position": self.position.pk,
                "positionid": self.position.positionid,
                "other_position": other.position,
                "other_positionid": other.position.positionid,
                "other_order": other.position.order.code,
            },
        )
        other.position.order.log_action(
            "pretix_swap.swap.complete",
            data={
                "position": other.position.pk,
                "positionid": other.position.positionid,
                "other_position": self.position,
                "other_positionid": self.position.positionid,
                "other_order": self.position.order.code,
            },
        )

    def attempt_swap(self):
        """Find a swap partner.

        Do not use for bulk action – use utils.match_open_swap_requests
        instead!
        """
        if self.swap_method != self.Methods.FREE:
            return

        item = self.position.item
        variation = self.position.variation
        other = SwapRequest.objects.filter(
            position__order__event_id=self.event.pk,
            state=SwapRequest.States.REQUESTED,
            swap_method=SwapRequest.Methods.FREE,
            swap_type=SwapRequest.Types.SWAP,
            partner__isnull=True,
            target_subevent=self.position.subevent,
            position__subevent=self.target_subevent,
            position__item=item,
        )
        if variation:
            other = other.filter(position__variation=variation)

        other = other.exclude(pk=self.pk).first()
        if other:
            self.swap_with(other)

    def cancel_for(self, other):
        """Called when an order is marked as paid.

        Makes sure that item, variation and subevent match before
        calling this method.
        """

        if not self.event.settings.cancel_orderpositions:
            raise Exception("Order position canceling is currently not allowed")

        if (
            self.position.subevent != other.subevent
            or self.position.item != other.item
            or self.position.variation != other.variation
        ):
            raise Exception("Cancelation failed, orders are not equal")
        if not can_be_canceled(self.event, self.position.item, self.position.subevent):
            raise Exception("Cancelation failed, currently not allowed")

        # Make sure AGAIN that the state is alright, because timings
        self.refresh_from_db()
        if not self.state == self.States.REQUESTED:
            raise Exception("Not in 'requesting' state.")
        if self.position.price > other.price:
            raise Exception("Cannot cancel for a cheaper product.")

        try:
            change_manager = OrderChangeManager(order=self.position.order)
            change_manager.cancel(position=self.position)
            change_manager.commit()
        except OrderError:  # Let's hope this order error is because we're trying to empty the order
            cancel_order(
                self.position.order.pk,
                cancellation_fee=self.event.settings.swap_cancellation_fee,
                try_auto_refund=True,
            )
        self.state = self.States.COMPLETED
        self.target_order = other.order  # Should be set already, let's just make sure
        self.save()
        self.position.order.log_action(
            "pretix_swap.cancelation.complete",
            data={
                "position": self.position.pk,
                "positionid": self.position.positionid,
                "other_position": other.pk,
                "other_positionid": other.positionid,
                "other_order": other.order.code,
            },
        )
