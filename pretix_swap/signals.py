from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings
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


@receiver(order_info_top, dispatch_uid="swap_order_info_top")
def notifications_order_info_top(sender, request, order, **kwargs):
    from .models import SwapState

    if not order.status == "p":
        return
    event = request.event
    notifications = []

    states = SwapState.objects.filter(position__order=order).order_by("state")
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

    from .models import SwapState
    from .utils import get_applicable_items

    event = request.event
    items = get_applicable_items(event)

    states = SwapState.objects.filter(position__order=order).order_by(
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
            "plugins:pretix_swap:swap.list",
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
        entries.append(entry)

    entries_text = "".join(
        f"<li><b>{entry['position'].item.name}:</b> {entry['text']}<br>{entry['action_text']}</li>"
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
