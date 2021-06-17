from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
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
from formtools.wizard.views import SessionWizardView
from pretix.base.models.event import Event
from pretix.base.models.orders import OrderPosition
from pretix.base.services.orders import OrderError, approve_order
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .forms import (
    CancelationForm,
    SwapGroupForm,
    SwapSettingsForm,
    SwapWizardConfirmForm,
    SwapWizardDetailsForm,
    SwapWizardPositionForm,
    SwapWizardTypeForm,
)
from .models import SwapApproval, SwapGroup, SwapRequest
from .utils import get_valid_swap_types


class SwapStats(EventPermissionRequiredMixin, FormView):
    permission = "can_change_event_settings"
    template_name = "pretix_swap/control/stats.html"
    form_class = CancelationForm

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["overview"] = self.requests_by_state
        products = self.requests_by_product
        form = ctx["form"]
        for line in products:
            line["form_field"] = form[f"item_{line['item'].pk}"]
        ctx["by_products"] = products
        ctx["subevents"] = self.subevents
        return ctx

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["items"] = self.requests_by_product
        return result

    def get_success_url(self):
        return reverse(
            "plugins:pretix_swap:stats",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    @transaction.atomic
    def form_valid(self, form):
        orders_approved = 0
        data = form.cleaned_data
        for row in self.requests_by_product:
            approvable = row["approval_orders"]
            to_approve = data.get(f"item_{row['item'].pk}")
            if not approvable or not to_approve:
                continue
            positions = OrderPosition.objects.filter(
                order__status="n",  # Pending orders with and without approval
                order__event=self.request.event,
                order__require_approval=True,
                item=row["item"],
            )
            if self.request.event.settings.cancel_orderpositions_verified_only:
                positions = positions.filter(order__email_known_to_work=True)

            positions = positions.annotate(
                has_request=Count("order__cancelation_request")
            ).order_by(
                "-has_request",
                "order__datetime",
            )  # Ones with matching requests first, then oldest
            orders_approved += self.approve_orders(positions, to_approve)

        messages.success(
            self.request,
            str(_("Approved {orders_approved} orders.")).format(
                orders_approved=orders_approved
            ),
        )
        return super().form_valid(form)

    def approve_orders(self, positions, count):
        """WARNING DANGER ATTENTION This only works when there is only one
        orderposition per order!!!"""
        approved = 0
        for position in positions:
            if approved >= count:
                break
            try:
                SwapApproval.objects.create(order=position.order)
                approve_order(
                    position.order,
                    user=self.request.user,
                    send_mail=True,
                )
                approved += 1
            except OrderError as e:
                position.order.log_action(
                    "pretix_swap.cancelation.approve_failed",
                    data={"detail": str(e)},
                    user=self.request.user,
                )
        return approved

    @cached_property
    def subevents(self):
        return list(self.request.event.subevents.all()) or [None]

    @cached_property
    def requests_by_product(self):
        requests = SwapRequest.objects.filter(
            position__order__event=self.request.event,
            state=SwapRequest.States.REQUESTED,
            partner__isnull=True,
            position__order__status="p",  # Should already be the case, but hey
            swap_type=SwapRequest.Types.CANCELATION,
        ).select_related("position", "position__item")
        positions = OrderPosition.objects.filter(
            order__status="n",  # Pending orders with and without approval
            order__event=self.request.event,
        )
        items = list(
            set(requests.values_list("position__item", flat=True))
            | set(positions.values_list("item", flat=True))
        )
        result = []
        for item in items:
            item = self.request.event.items.get(pk=item)
            availabilities = []
            for subevent in self.subevents:
                availability = item.check_quotas(subevent=subevent)
                if not availability[1] and availability[0] == 100:
                    availability = "∞"
                else:
                    availability = availability[1]
                availabilities.append(availability)
            result.append(
                {
                    "item": item,
                    "available_in_quota": availabilities,
                    "open_cancelation_requests": requests.filter(
                        position__item=item,
                    ).count(),
                    "approval_orders": positions.filter(
                        item=item, order__require_approval=True
                    ).count(),
                    "pending_orders": positions.filter(
                        item=item, order__require_approval=False
                    ).count(),
                }
            )
        return result

    @cached_property
    def requests_by_state(self):
        requests = SwapRequest.objects.filter(position__order__event=self.request.event)
        items = list(set(requests.values_list("position__item", flat=True)))
        result = []
        for item in items:
            item = self.request.event.items.get(pk=item)
            result.append(
                {
                    "item": item,
                    "open_swap_requests": requests.filter(
                        swap_type=SwapRequest.Types.SWAP,
                        state=SwapRequest.States.REQUESTED,
                        position__item=item,
                    ).count(),
                    "completed_swap_requests": requests.filter(
                        swap_type=SwapRequest.Types.SWAP,
                        state=SwapRequest.States.COMPLETED,
                        position__item=item,
                    ).count(),
                    "open_cancelation_requests": requests.filter(
                        swap_type=SwapRequest.Types.CANCELATION,
                        state=SwapRequest.States.REQUESTED,
                        position__item=item,
                    ).count(),
                    "completed_cancelation_requests": requests.filter(
                        swap_type=SwapRequest.Types.CANCELATION,
                        state=SwapRequest.States.COMPLETED,
                        position__item=item,
                    ).count(),
                }
            )
        return result


class SwapSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    permission = "can_change_settings"
    form_class = SwapSettingsForm
    template_name = "pretix_swap/control/settings.html"

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["swap_groups"] = (
            self.request.event.swap_groups.all()
            .prefetch_related("items")
            .order_by("swap_type")
        )
        swap_groups = ctx["swap_groups"].filter(swap_type="s")
        cancel_groups = ctx["swap_groups"].filter(swap_type="c")
        ctx["warn_multiple_items"] = self.request.event.settings.max_items_per_order > 1
        ctx["warn_no_swap_groups"] = (
            self.request.event.settings.swap_orderpositions and not swap_groups
        )
        ctx["warn_no_cancel_groups"] = (
            self.request.event.settings.cancel_orderpositions and not cancel_groups
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
        result["request"] = self.request  # Only used for warnings
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
        result["request"] = self.request  # Only used for warnings
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

    def delete(self, request, *args, **kwargs):
        position = self.get_object().position
        result = super().delete(request, *args, **kwargs)
        position.order.log_action(
            "pretix_swap.swap.cancel",
            data={
                "position": position.pk,
                "positionid": position.positionid,
            },
        )
        return result

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

    def dispatch(self, request, *args, **kwargs):
        if not self.order.status == "p":
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class SwapCancel(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretix_swap/presale/cancel.html"

    def dispatch(self, request, *args, **kwargs):
        if not self.order.status == "p":
            raise Http404()
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        return get_object_or_404(
            SwapRequest,
            position__order=self.order,
            pk=self.kwargs["pk"],
            state=SwapRequest.States.REQUESTED,
            swap_type=SwapRequest.Types.SWAP,
            position__order__status="p",
        )

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["obj"] = self.object
        ctx["order"] = self.order
        return ctx

    def post(self, request, *args, **kwargs):
        self.object.delete()
        messages.success(request, _("We have canceled your request."))
        return redirect(
            eventreverse(
                self.request.event,
                "presale:event.order",
                kwargs={"order": self.order.code, "secret": self.order.secret},
            )
        )


def condition_position(wizard):
    return len(wizard.order.positions.all()) > 1


def condition_type(wizard):
    actions = get_valid_swap_types(wizard.position)
    return len(actions) > 1


class SwapCreate(EventViewMixin, OrderDetailMixin, SessionWizardView):

    form_list = [
        ("position", SwapWizardPositionForm),
        ("type", SwapWizardTypeForm),
        (
            "details",
            SwapWizardDetailsForm,
        ),  # contains swap method if possible, swap code, subevent always
        ("confirm", SwapWizardConfirmForm),
    ]
    condition_dict = {
        "position": condition_position,
        "type": condition_type,
    }

    @cached_property
    def position(self):
        positions = self.order.positions.all()
        if len(positions) == 1:
            return positions.first()
        try:
            return self.get_cleaned_data_for_step("position").get("position")
        except Exception:  # not filled in or not valid
            return None

    @cached_property
    def swap_type(self):
        actions = get_valid_swap_types(self.position)
        if len(actions) == 1:
            return actions[0]
        try:
            return self.get_cleaned_data_for_step("type").get("swap_type")
        except Exception:  # not filled in or not valid
            return None

    def dispatch(self, request, *args, **kwargs):
        if not self.order.status == "p":
            raise Http404()
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        return f"pretix_swap/presale/new_{self.steps.current}.html"

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["order"] = self.order
        ctx["order_url"] = eventreverse(
            self.request.event,
            "presale:event.order",
            kwargs={"order": self.order.code, "secret": self.order.secret},
        )
        ctx["position"] = self.position
        ctx["swap_type"] = self.swap_type
        ctx["details"] = self.get_cleaned_data_for_step("details")
        return ctx

    def get_form_kwargs(self, step=None):
        if step == "position":
            return {"order": self.order}
        if step == "type":
            return {"swap_types": get_valid_swap_types(self.position)}
        if step == "details":
            return {"position": self.position, "swap_type": self.swap_type}
        return {}

    @transaction.atomic()
    def done(self, form_list, *args, **kwargs):
        position = self.position
        swap_type = self.swap_type
        details = self.get_cleaned_data_for_step("details")

        # TODO more validation

        instance = SwapRequest.objects.create(
            position=position,
            state=SwapRequest.States.REQUESTED,
            swap_type=swap_type,
            swap_method=details.get("swap_method"),
            target_order=details.get("cancel_code"),
            target_subevent=details.get("target_subevent"),
        )
        instance.position.order.log_action(
            "pretix_swap.swap.request",
            data={
                "position": instance.position.pk,
                "positionid": instance.position.positionid,
                "swap_type": instance.swap_type,
                "swap_method": instance.swap_method,
            },
        )
        if instance.swap_type == SwapRequest.Types.SWAP:  # Only swaps are instantaneous
            if details.get("swap_code"):
                instance.swap_with(details.get("swap_code"))
            elif instance.swap_method == SwapRequest.Methods.FREE:
                instance.attempt_swap()
        elif instance.target_order:
            instance.target_order.log_action(
                "pretix_swap.cancelation.offer_created",
                data={
                    "other_order": instance.position.order.code,
                    "other_position": instance.position.id,
                    "other_positionid": instance.position.positionid,
                },
            )
        if instance.state == SwapRequest.States.COMPLETED:
            messages.success(
                self.request, _("We received your request and matched you directly!")
            )
        elif instance.swap_method == SwapRequest.Methods.FREE:
            messages.success(
                self.request,
                _(
                    "We have received your request – please wait while we try to find a match for you."
                ),
            )
        else:
            messages.success(
                self.request,
                _(
                    "We received your request. "
                    "Once you enter a swapping code or give your code to somebody else, this process can continue. "
                    "We will notify you then."
                ),
            )
        return redirect(
            eventreverse(
                self.request.event,
                "presale:event.order",
                kwargs={"order": self.order.code, "secret": self.order.secret},
            )
        )
