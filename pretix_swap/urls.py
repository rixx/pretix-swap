from django.conf.urls import url

from . import views

urlpatterns = [
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/swap$",
        views.SwapSettings.as_view(),
        name="settings",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/swap/new/$",
        views.SwapGroupCreate.as_view(),
        name="settings.new",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/swap/(?P<pk>[0-9]+)/$",
        views.SwapGroupEdit.as_view(),
        name="settings.detail",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/swap/(?P<pk>[0-9]+)/delete/",
        views.SwapGroupDelete.as_view(),
        name="settings.delete",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/swap$",
        views.SwapStats.as_view(),
        name="stats",
    ),
]

from pretix.multidomain import event_url

event_patterns = [
    event_url(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/swap/$",
        views.SwapOverview.as_view(),
        name="swap.list",
    ),
    event_url(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/swap/new$",
        views.SwapCreate.as_view(),
        name="swap.new",
    ),
    event_url(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/swap/(?P<pk>[0-9]+)/cancel$",
        views.SwapCancel.as_view(),
        name="swap.cancel",
    ),
]
