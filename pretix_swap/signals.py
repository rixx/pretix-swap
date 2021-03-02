from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import logentry_display, logentry_object_link
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
    if not order.status == "p":
        return

    from .models import SwapRequest
    from .utils import get_applicable_items

    event = request.event
    items = get_applicable_items(event)

    states = SwapRequest.objects.filter(position__order=order).order_by(
        "position__positionid"
    )
    can_swap = (
        event.settings.swap_orderpositions or event.settings.cancel_orderpositions
    )

    if not states and not can_swap:
        return

    template = get_template("pretix_swap/presale/order_box.html")
    ctx = {
        "request": request,
        "positions": order.positions.all().prefetch_related("swap_states"),
        "items": items,
        "specific_swap_allowed": event.settings.swap_orderpositions
        and event.settings.swap_orderpositions_specific,
    }
    return template.render(ctx)


@receiver(logentry_display, dispatch_uid="swap_logentries")
def swap_logentry_display(sender, logentry, *args, **kwargs):
    if logentry.action_type == "pretix_swap.swap.cancel":
        return str(_("The request to swap position #{id} has been canceled.")).format(
            id=logentry.parsed_data["positionid"]
        )
    if logentry.action_type == "pretix_swap.swap.request":
        return str(_("The user has requested to swap position #{id}.")).format(
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
    if logentry.action_type == "pretix_swap.cancelation.approve_failed":
        return str(_("Approval failed with error message: {e}")).format(
            e=logentry.parsed_data["detail"]
        )


@receiver(logentry_object_link, dispatch_uid="swap_logentries_link")
def swap_logentry_display_link(sender, logentry, *args, **kwargs):
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
