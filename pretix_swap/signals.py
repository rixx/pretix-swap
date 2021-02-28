from django.dispatch import receiver
from django.urls import resolve, reverse
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings

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
