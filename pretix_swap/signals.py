from django.dispatch import receiver
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

    icon_map = {"create": "plus", "view": "eye", "abort": "trash-o"}
    text_map = {
        "create": _("New request"),
        "view": _("View request"),
        "abort": _("Cancel request"),
    }
    from pretix.multidomain.urlreverse import eventreverse

    link_map = {
        "create": lambda pos: eventreverse(
            event,
            "plugins:pretix_swap:swap.new",
            kwargs={"order": pos.order.code, "secret": pos.order.secret},
        )
        + f"?position={pos.pk}",
        "view": lambda pos: eventreverse(
            event,
            "plugins:pretix_swap:swap.list",
            kwargs={"order": pos.order.code, "secret": pos.order.secret},
        ),
        "abort": lambda pos: eventreverse(
            event,
            "plugins:pretix_swap:swap.cancel",
            kwargs={"order": pos.order.code, "secret": pos.order.secret, "pk": pos.pk},
        ),
    }
    entries = []
    for position in order.positions.all().prefetch_related("swap_states"):
        states = position.swap_states.all()
        if states:
            # TODO more than one state
            state = states[0]
            entry = {
                "position": position,
                "text": state.get_notification(),
                "actions": state.get_notification_actions(),
            }
            if not entry["actions"] and position.item in items:
                entry["actions"].append("create")
        elif position.item in items:
            entry = {
                "position": position,
                "text": _("You can request to swap or cancel this product."),
                "actions": ["create"],
            }
        else:
            entry = {
                "position": position,
                "text": _("This product cannot be changed at the moment."),
                "actions": [],
            }

        entry["action_text"] = " ".join(
            f'<a href="{link_map[action](position)}" class="btn btn-default"><i class="fa fa-{icon_map[action]}"></i> {text_map[action]}</a>'
            for action in entry["actions"]
        )
        entry["attendee_name"] = (
            f" ({position.attendee_name})" if position.attendee_name else ""
        )
        entries.append(entry)

    entries_text = "".join(
        f"<li><b>{entry['position'].item.name}{entry['attendee_name']}:</b> {entry['text']}<br>{entry['action_text']}</li>"
        for entry in entries
    )

    heading = _("Swap items")
    result = f"""
    <div class="panel panel-primary">
        <div class="panel-heading">
            <h3 class="panel-title"> {heading} </h3>
        </div>
        <div class="panel-body">
            <ol>
                {entries_text}
            </ol>
        </div>
    </div>
    """

    return result


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
