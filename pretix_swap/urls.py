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
]
