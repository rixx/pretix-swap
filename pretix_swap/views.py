from django.urls import reverse
from pretix.base.models.event import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin

from .forms import SwapSettingsForm


class SwapSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    permission = "can_change_settings"
    form_class = SwapSettingsForm
    template_name = "pretix_swap/settings.html"

    def get_success_url(self, **kwargs):
        return reverse(
            "plugins:pretix_swap:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
