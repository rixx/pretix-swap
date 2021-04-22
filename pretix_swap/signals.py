from decimal import Decimal
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import logentry_display, logentry_object_link, order_paid
from pretix.control.signals import nav_event, nav_event_settings
from pretix.presale.signals import order_info, order_info_top

BOOLEAN_SETTINGS = [
    "swap_orderpositions",
    "swap_orderpositions_specific",
    "cancel_orderpositions",
    "cancel_orderpositions_specific",
]

for settings_name in BOOLEAN_SETTINGS:
    settings_hierarkey.add_default(settings_name, "False", bool)
settings_hierarkey.add_default("swap_cancellation_fee", "0.00", Decimal)


@receiver(nav_event_settings, dispatch_uid="swap_nav_settings")
def navbar_settings(sender, request, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": "Swap",
            "icon": "random",
            "url": reverse(
                "plugins:pretix_swap:settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_swap"
            and "settings" in url.url_name,
        }
    ]


@receiver(nav_event, dispatch_uid="swap_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_change_event_settings"
    ):
        return []
    return [
        {
            "label": _("Swap overview"),
            "icon": "random",
            "url": reverse(
                "plugins:pretix_swap:stats",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_swap"
            and url.url_name == "stats",
        }
    ]


@receiver(order_info_top, dispatch_uid="swap_order_info_top")
def notifications_order_info_top(sender, request, order, **kwargs):
    from .models import SwapRequest

    if not order.status == "p":
        return
    event = request.event
    notifications = []

    states = SwapRequest.objects.filter(position__order=order).order_by("state")
    if states:
        notifications.append(
            {
                "type": "info",
                "text": _("Please see below for information on your swap requests."),
            }
        )
    elif event.settings.swap_orderpositions or event.settings.cancel_orderpositions:
        from .utils import get_applicable_items

        items = get_applicable_items(event)
        if any(pos.item in items for pos in order.positions.all()):
            if (
                event.settings.swap_orderpositions
                and event.settings.cancel_orderpositions
            ):
                text = _(
                    "You can currently request to swap or cancel some of your ordered products!"
                )
            elif event.settings.swap_orderpositions:
                text = _(
                    "You can currently request to swap some of your ordered products!"
                )
            else:
                text = _(
                    "You can currently request to cancel some of your ordered products!"
                )
            notifications.append({"type": "info", "text": text})

    result = ""
    for notification in notifications:
        result += f'<div class="alert alert-{notification["type"]}">{notification["text"]}</div>'
    return result


@receiver(order_info, dispatch_uid="swap_order_info")
def order_info_bottom(sender, request, order, **kwargs):
    from .models import SwapRequest
    from .utils import get_applicable_items

    event = request.event

    if not order.status == "p":
        if order.status != "n" or not order.require_approval:
            return
        if not (
            event.settings.cancel_orderpositions
            and event.settings.cancel_orderpositions_specific
        ):
            return
        template = get_template("pretix_swap/presale/require_approval_box.html")
        in_progress = SwapRequest.objects.filter(
            target_order=order,
            state=SwapRequest.States.REQUESTED,
            swap_type=SwapRequest.Types.CANCELATION,
            swap_method=SwapRequest.Methods.SPECIFIC,
        ).exists()
        return template.render({"secret": order.code, "in_progress": in_progress})

    items = get_applicable_items(event)

    states = SwapRequest.objects.filter(position__order=order).order_by(
        "position__positionid"
    )
    can_swap = (
        event.settings.swap_orderpositions or event.settings.cancel_orderpositions
    )

    if not states and not can_swap:
        return

    positions = order.positions.all().prefetch_related("swap_states")
    for position in positions:
        position.no_active_requests = not position.swap_states.filter(
            state=SwapRequest.States.REQUESTED
        ).exists()
        position.ordered_requests = position.swap_states.order_by("requested")
    template = get_template("pretix_swap/presale/order_box.html")
    ctx = {
        "request": request,
        "positions": positions,
        "items": items,
        "specific_swap_allowed": event.settings.swap_orderpositions
        and event.settings.swap_orderpositions_specific,
    }
    return template.render(ctx)


@receiver(logentry_display, dispatch_uid="swap_logentries")
def swap_logentry_display(sender, logentry, *args, **kwargs):
    simple_displays = {
        "pretix_swap.cancelation.no_partner": _(
            "The order was marked as paid and expected "
            "to match a cancelation request, but no matching cancelation request was found."
        ),
    }
    if logentry.action_type in simple_displays:
        return simple_displays.get(logentry.action_type)
    if logentry.action_type == "pretix_swap.swap.cancel":
        return str(_("The request to swap position #{id} has been canceled.")).format(
            id=logentry.parsed_data["positionid"]
        )
    if logentry.action_type == "pretix_swap.swap.request":
        swap_type = logentry.parsed_data.get("swap_type") or "s"
        if swap_type == "s":
            return str(_("The user has requested to swap position #{id}.")).format(
                id=logentry.parsed_data["positionid"]
            )
        else:
            return str(_("The user has requested to cancel position #{id}.")).format(
                id=logentry.parsed_data["positionid"]
            )
    if logentry.action_type == "pretix_swap.swap.complete":
        return str(
            _(
                "Order position #{id} has been swapped with position #{other_id} of order {order}."
            )
        ).format(
            id=logentry.parsed_data["positionid"],
            other_id=logentry.parsed_data["other_positionid"],
            order=logentry.parsed_data["other_order"],
        )
    if logentry.action_type == "pretix_swap.cancelation.offer_created":
        return str(
            _(
                "The order {order}#{position} has requested to cancel in favour of this order."
            )
        ).format(
            position=logentry.parsed_data["other_positionid"],
            order=logentry.parsed_data["other_order"],
        )
    if logentry.action_type == "pretix_swap.cancelation.complete":
        return str(
            _(
                "Order position #{id} has been canceled after order {order} was marked as paid."
            )
        ).format(
            id=logentry.parsed_data["positionid"],
            order=logentry.parsed_data["other_order"],
        )
    if logentry.action_type == "pretix_swap.cancelation.approve_failed":
        return str(_("Approval failed with error message: {e}")).format(
            e=logentry.parsed_data["detail"]
        )
    if logentry.action_type == "pretix_swap.cancelation.cancelation_failed":
        return str(_("Approval failed with error message: {e}")).format(
            e=logentry.parsed_data["detail"]
        )


@receiver(logentry_object_link, dispatch_uid="swap_logentries_link")
def swap_logentry_display_link(logentry, sender, *args, **kwargs):
    if logentry.action_type == "pretix_swap.swap.complete":
        a_text = _("Order {val}#{position}")
        a_map = {
            "href": reverse(
                "control:event.order",
                kwargs={
                    "event": sender.slug,
                    "organizer": sender.organizer.slug,
                    "code": logentry.parsed_data["other_order"],
                },
            ),
            "val": logentry.content_object.parsed_data["other_order"],
            "position": logentry.content_object.parsed_data["other_positionid"],
        }
        a_map["val"] = '<a href="{href}">{val}</a>'.format_map(a_map)
        return a_text.format_map(a_map)


@receiver(order_paid, dispatch_uid="swap_order_paid")
def swap_order_paid(order, sender, *args, **kwargs):
    swap_approval = getattr(order, "swap_approval", None)
    if not order.event.settings.cancel_orderpositions:
        return
    if not swap_approval or not swap_approval.approved_for_cancelation_request:
        return

    from .models import SwapRequest
    from .utils import get_cancelable_items

    for position in order.positions.all():
        items = [
            i
            for i in get_cancelable_items(position.item)
            if i.default_price <= position.price
        ]
        # First, check if there are specific cancelation request, if
        # if not order.event.settings.cancel_orderpositions_specific:
        specific_request = SwapRequest.objects.filter(
            state=SwapRequest.States.REQUESTED,
            swap_type=SwapRequest.Types.CANCELATION,
            swap_method=SwapRequest.Methods.SPECIFIC,
            target_order=order,
            position__order__status="p",
        ).first()
        if specific_request:
            try:
                specific_request.cancel_for(position)
                continue
            except Exception as e:
                order.log_action(
                    "pretix_swap.cancelation.cancelation_failed",
                    data={"detail": str(e)},
                )
        # Next go through the oldest cancelation requests that are compatible
        requests = SwapRequest.objects.filter(
            state=SwapRequest.States.REQUESTED,
            swap_type=SwapRequest.Types.CANCELATION,
            swap_method=SwapRequest.Methods.FREE,
            position__item__in=items,
            position__order__status="p",
        )
        if not requests:
            order.log_action(
                "pretix_swap.cancelation.no_partner",
                data={
                    "position": position.pk,
                    "positionid": position.positionid,
                },
            )
            return
        for request in requests:  # Try until we succeed or run out of requests
            try:
                request.cancel_for(position)
                break
            except Exception as e:
                order.log_action(
                    "pretix_swap.cancelation.cancelation_failed",
                    data={"detail": str(e)},
                )
