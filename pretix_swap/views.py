from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    TemplateView,
    UpdateView,
)
from pretix.base.models.event import Event
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .forms import SwapGroupForm, SwapRequestForm, SwapSettingsForm
from .models import SwapGroup, SwapState


class SwapSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    permission = "can_change_settings"
    form_class = SwapSettingsForm
    template_name = "pretix_swap/control/settings.html"

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["swap_groups"] = self.request.event.swap_groups.all().prefetch_related(
            "left", "right"
        )
        return ctx

    def get_success_url(self, **kwargs):
        return reverse(
            "plugins:pretix_swap:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class SwapGroupCreate(EventPermissionRequiredMixin, CreateView):
    permission = "can_change_event_settings"
    form_class = SwapGroupForm
    template_name = "pretix_swap/control/create.html"
    model = SwapGroup

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["event"] = self.request.event
        return result

    def form_valid(self, form):
        self.form = form
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "plugins:pretix_swap:settings.detail",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
                "pk": self.form.instance.pk,
            },
        )


class SwapGroupEdit(EventPermissionRequiredMixin, UpdateView):
    permission = "can_change_event_settings"
    template_name = "pretix_swap/control/edit.html"
    form_class = SwapGroupForm
    model = SwapGroup

    def get_success_url(self):
        return reverse(
            "plugins:pretix_swap:settings.detail",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
                "pk": self.get_object().pk,
            },
        )

    def get_form_kwargs(self, **kwargs):
        result = super().get_form_kwargs(**kwargs)
        result["event"] = self.request.event
        result["locales"] = self.request.event.settings.locales
        return result

    def form_valid(self, form):
        super().form_valid(form)
        messages.success(self.request, _("Your changes have been saved."))
        return redirect(
            reverse(
                "plugins:pretix_swap:settings",
                kwargs={
                    "organizer": self.request.event.organizer.slug,
                    "event": self.request.event.slug,
                },
            )
            + "#tab-0-1-open"
        )


class SwapGroupDelete(EventPermissionRequiredMixin, DeleteView):
    permission = "can_change_event_settings"
    template_name = "pretix_swap/control/delete.html"
    model = SwapGroup

    def get_success_url(self):
        return reverse(
            "plugins:pretix_swap:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class SwapOverview(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretix_swap/presale/swap.html"


class SwapCancel(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretix_swap/presale/cancel.html"


class SwapCreate(EventViewMixin, OrderDetailMixin, FormView):
    template_name = "pretix_swap/presale/new.html"
    form_class = SwapRequestForm

    @cached_property
    def swap_actions(self):
        actions = []
        if self.request.event.settings.swap_orderpositions:
            actions.append(SwapState.SwapTypes.SWAP)
        if self.request.event.settings.cancel_orderpositions:
            actions.append(SwapState.SwapTypes.CANCELATION)
        return actions

    def get_form_kwargs(self, *args, **kwargs):
        result = super().get_form_kwargs(*args, **kwargs)
        result["swap_actions"] = self.swap_actions
        result["order"] = self.order
        result["position"] = self.request.GET.get("position")
        return result

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["order"] = self.order
        return ctx

    def dispatch(self, request, *args, **kwargs):
        if not self.swap_actions or not self.order.status == "p":
            raise Http404()
        return super().dispatch(request, *args, **kwargs)
