from decimal import Decimal
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nModelForm
from pretix.base.forms import SettingsForm
from pretix.base.models import Item, SubEvent

from .models import SwapGroup, SwapRequest
from .utils import get_target_subevents, get_valid_swap_types


class SwapSettingsForm(SettingsForm):
    swap_orderpositions = forms.BooleanField(
        label=_("Allow customers to swap order positions"),
        required=False,
        help_text=_(
            "Products included in a swap group will be available for swap requests. Swaps will be performed automatically."
        ),
    )
    swap_orderpositions_specific = forms.BooleanField(
        label=_("Allow customers to swap with a specific other order position"),
        required=False,
        help_text=_(
            "Users can enter a code to swap their ticket with somebody specific."
        ),
    )
    cancel_orderpositions = forms.BooleanField(
        label=_("Allow customers to request to cancel orderpositions"),
        required=False,
        help_text=_(
            "Products included in a cancel group will be available for cancelation requests. Cancelations will be performed only when you trigger them."
        ),
    )
    cancel_orderpositions_specific = forms.BooleanField(
        label=_(
            "Allow customers to request to cancel orderpositions for a specific waiting list entry"
        ),
        required=False,
        help_text=_(
            "Users can enter a code to hand their ticket to somebody specific."
        ),
    )
    cancel_orderpositions_verified_only = forms.BooleanField(
        label=_("Require verified email for cancellations"),
        required=False,
        help_text=_(
            "Allow customers to request to cancel orderpositions only with a known-to-work email address"
        ),
    )
    swap_cancellation_fee = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        localize=True,
        label=_("Keep a cancellation fee of"),
        help_text=_(
            "Please always enter a gross value, tax will be calculated automatically."
        ),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.get("obj")
        super().__init__(*args, **kwargs)

    def clean(self):
        data = self.cleaned_data
        if not data.get("swap_orderpositions"):
            data["swap_orderpositions_specific"] = False
        if not data.get("cancel_orderpositions"):
            data["cancel_orderpositions_specific"] = False

    def clean_cancellation_fee(self):
        val = self.cleaned_data["cancellation_fee"] or Decimal("0.00")
        return val


class ItemModelMultipleChoiceField(SafeModelMultipleChoiceField):
    def label_from_instance(self, instance):
        label = str(instance)
        if instance.default_price:
            return f"{label} ({instance.default_price}€)"
        return f"{label} ({_('free')})"


class SwapGroupForm(I18nModelForm):
    def __init__(self, *args, event=None, request=None, **kwargs):
        self.event = event
        self.request = request
        kwargs["locales"] = self.event.settings.locales if self.event else ["en"]
        super().__init__(*args, **kwargs)
        self.fields["items"].queryset = Item.objects.filter(event=event)
        self.fields["subevents"].queryset = SubEvent.objects.filter(event=event)

    def save(self, *args, **kwargs):
        self.instance.event = self.event
        return super().save(*args, **kwargs)

    def clean_items(self):
        data = self.cleaned_data.get("items")
        if not data:
            raise ValidationError(_("Please select at least one item!"))
        return data

    def clean(self):
        cleaned_data = super().clean()
        items = set(cleaned_data.get("items") or [])

        is_swap = cleaned_data.get("swap_type") == SwapGroup.Types.SWAP
        prices = set()
        for item in items:
            prices.add(item.default_price)
        if len(prices) > 1:
            if is_swap:
                raise ValidationError(
                    _("You can only swap elements with the same price!")
                )
            elif self.request:
                messages.warning(
                    self.request,
                    _(
                        "Your products include elements with different prices. "
                        "Please note that cancelations will only be allowed when the new product "
                        "has at least the same price as the canceled one, so that you will not lose money."
                    ),
                )
        return cleaned_data

    class Meta:
        model = SwapGroup
        fields = (
            "name",
            "swap_type",
            "items",
            "subevents",
        )
        field_classes = {
            "items": ItemModelMultipleChoiceField,
            "subevents": SafeModelMultipleChoiceField,
        }


class PositionModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, instance):
        label = str(instance)
        if instance.subevent:
            label = f"{label}, {instance.subevent.date_from.date().isoformat()}"
        if instance.attendee_name:
            return f"{label} ({instance.attendee_name})"
        return label


class SwapWizardPositionForm(forms.Form):
    def __init__(self, *args, order, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        text = {
            SwapRequest.Types.SWAP: _("Request a team/festival date swap"),
            SwapRequest.Types.CANCELATION: _("Request to sell your ticket"),
        }
        relevant_positions = [
            (position, text[position])
            for position in order.positions.all()
            if get_valid_swap_types(position)
        ]
        self.fields["position"] = PositionModelChoiceField(
            self.order.positions.filter(pk__in=[p.pk for p in relevant_positions]),
            label=_("Which item do you want to change?"),
            widget=forms.RadioSelect,
        )


class SwapWizardTypeForm(forms.Form):
    def __init__(self, *args, swap_types, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["swap_type"] = forms.ChoiceField(
            initial=swap_types[0],
            choices=swap_types,
            label=_("What do you want to do?"),
            required=True,
            widget=forms.RadioSelect,
        )


class SwapWizardDetailsForm(forms.Form):
    """Can contain some of these fields:

    - method (depending on swap_type and allowed actions)
    - target_order (when the type is cancel, will only show when the non-free method is chosen)
    - swap_code (when the type is swap, will only show when the non-free method is chosen)
    - target_subevent (when the type is swap)
    """

    def __init__(self, *args, position, swap_type, **kwargs):
        self.position = position
        self.swap_type = swap_type
        self.event = position.order.event
        super().__init__(*args, **kwargs)
        if self.swap_type == SwapRequest.Types.SWAP:
            self.fields["target_subevent"] = forms.ModelChoiceField(
                required=True,
                label=_("Date"),
                queryset=get_target_subevents(self.position, self.swap_type),
                widget=forms.RadioSelect,
                empty_label=None,
            )
        if (
            swap_type == SwapRequest.Types.SWAP
            and self.event.settings.swap_orderpositions_specific
        ):
            self.fields["swap_method"] = forms.ChoiceField(
                label=_("Do you want to swap your ticket:"),
                choices=(
                    (
                        SwapRequest.Methods.FREE,
                        _("With the next interested person."),
                    ),
                    (
                        SwapRequest.Methods.SPECIFIC,
                        _("With a specific person."),
                    ),
                ),
            )
            self.fields["swap_code"] = forms.CharField(
                required=False,
                label=_("Direct Code"),
                help_text=_(
                    "Do you already know who you want to swap with? Enter their Direct Code here!"
                ),
            )
        elif (
            swap_type == SwapRequest.Types.CANCELATION
            and self.event.settings.cancel_orderpositions_specific
        ):
            self.fields["swap_method"] = forms.ChoiceField(
                label=_("Do you want to sell your ticket:"),
                choices=(
                    (
                        SwapRequest.Methods.FREE,
                        _("To the next person in line."),
                    ),
                    (
                        SwapRequest.Methods.SPECIFIC,
                        _("To a specific person."),
                    ),
                ),
            )
            self.fields["cancel_code"] = forms.CharField(
                required=False,
                label=_("Direct Code"),
                help_text=_(
                    "Do you already know who should take your place? Enter their Direct Code here! "
                    "A code will be created after you chose to swap with a specific person and once you send your swap request."
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        if (
            "swap_code" in self.fields
            and cleaned_data.get("swap_method") == SwapRequest.Methods.SPECIFIC
        ):
            cleaned_data["swap_code"] = self._clean_swap_code(
                subevent=cleaned_data.get("target_subevent")
            )
        else:
            cleaned_data["swap_code"] = None
        if (
            "cancel_code" in self.fields
            and cleaned_data.get("swap_method") == SwapRequest.Methods.SPECIFIC
        ):
            cleaned_data["cancel_code"] = self._clean_cancel_code()
        else:
            cleaned_data["cancel_code"] = None
        return cleaned_data

    def _clean_swap_code(self, subevent):
        data = self.cleaned_data.get("swap_code")
        if not data:
            return data
        partner = SwapRequest.objects.filter(
            position__order__event=self.event,
            swap_code=data,
            state=SwapRequest.States.REQUESTED,
        ).first()
        if not partner:
            raise ValidationError(_("Unknown swap code!"))
        if (partner.position.item != self.position.item) or (
            partner.position.variation != self.position.variation
        ):
            raise ValidationError(
                str(
                    _(
                        "The swap code you entered is for a different ticket than yours. You can only swap with the same ticket type."
                    )
                )
            )
        if partner.position.subevent == self.position.subevent:
            raise ValidationError(
                _(
                    "The swap code you entered is for the same event date as your ticket."
                )
            )
        if partner.position.subevent != subevent:
            raise ValidationError(
                str(
                    _(
                        "The swap code you entered is for a different date than you selected: {subevent}."
                    )
                ).format(subevent=partner.position.subevent)
            )
        self.partner = partner
        return partner

    def _clean_cancel_code(self):
        data = self.cleaned_data.get("cancel_code")
        if not data:
            raise ValidationError(
                _(
                    "If you want to sell your ticket to somebody specific, please provide a direct code."
                )
            )

        order = self.event.orders.filter(code__iexact=data).first()
        if not order:
            raise ValidationError(_("Unknown cancelation code."))

        other_position = (
            order.positions.first()
        )  # TODO we just assume that this pending order has only one position
        if other_position.item != self.position.item:
            raise ValidationError(
                str(
                    _(
                        "The cancelation code you entered is for a different ticket type than yours."
                    )
                )
            )
        if other_position.subevent != self.position.subevent:
            raise ValidationError(
                str(
                    _(
                        "The cancelation code you entered is for a ticket on a different date than yours."
                    )
                )
            )

        if SwapRequest.objects.filter(
            target_order=order,
            state=SwapRequest.States.REQUESTED,
            swap_type=SwapRequest.Types.CANCELATION,
            swap_method=SwapRequest.Methods.SPECIFIC,
        ).exists():
            raise ValidationError(
                _(
                    "Somebody else has already requested to pass their ticket to this order."
                )
            )
        return order


class SwapWizardConfirmForm(forms.Form):
    pass


class CancelationForm(forms.Form):
    def __init__(self, *args, subevents=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.subevents = subevents
        for subevent in subevents:
            self.fields[f"subevent_{subevent['subevent'].pk}"] = forms.IntegerField(
                min_value=0,
                required=False,
                label="",
            )


class OrderSearchForm(forms.Form):
    swap_requests = forms.ChoiceField(
        required=False,
        label=_("Swap requests"),
        choices=(
            ("", "--------"),
            ("1", _("Has open swap request")),
            ("2", _("Has finalized swap request")),
            ("3", _("Has open or finalized swap request")),
            ("4", _("Has no swap requests")),
        ),
    )
    cancellation_requests = forms.ChoiceField(
        required=False,
        label=_("Cancellation requests"),
        choices=(
            ("", "--------"),
            ("1", _("Has open cancellation request")),
            ("2", _("Has finalized cancellation request")),
            ("3", _("Has open or finalized cancellation request")),
            ("4", _("Has no cancellation requests")),
        ),
    )

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    def filter_qs(self, queryset):
        swaps = self.cleaned_data.get("swap_requests")
        cancels = self.cleaned_data.get("cancellation_requests")
        if swaps:
            if swaps == "4":
                queryset = queryset.exclude(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.SWAP,
                        )
                    )
                )
            elif swaps == "1":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.SWAP,
                            state=SwapRequest.States.REQUESTED,
                        )
                    )
                )
            elif swaps == "2":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.SWAP,
                            state=SwapRequest.States.COMPLETED,
                        )
                    )
                )
            elif swaps == "3":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.SWAP,
                        )
                    )
                )

        if cancels:
            if cancels == "4":
                queryset = queryset.exclude(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.CANCELATION,
                        )
                    )
                )
            elif cancels == "1":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.CANCELATION,
                            state=SwapRequest.States.REQUESTED,
                        )
                    )
                )
            elif cancels == "2":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.CANCELATION,
                            state=SwapRequest.States.COMPLETED,
                        )
                    )
                )
            elif cancels == "3":
                queryset = queryset.filter(
                    Exists(
                        SwapRequest.objects.filter(
                            position__order_id=OuterRef("pk"),
                            swap_type=SwapRequest.Types.CANCELATION,
                        )
                    )
                )
        return queryset

    def filter_to_strings(self):
        swaps = self.cleaned_data.get("swap_requests")
        cancels = self.cleaned_data.get("cancellation_requests")
        result = []
        swap_string = {
            "": "",
            "1": _("Orders with open swap requests"),
            "2": _("Orders with finalized swap requests"),
            "3": _("Orders with open or finalized swap requests"),
            "4": _("Orders without swap requests"),
        }[swaps]
        cancel_string = {
            "": "",
            "1": _("Orders with open cancellation requests"),
            "2": _("Orders with finalized cancellation requests"),
            "3": _("Orders with open or finalized cancellation requests"),
            "4": _("Orders without cancellation requests"),
        }[cancels]
        if swap_string:
            result.append(swap_string)
        if cancel_string:
            result.append(cancel_string)
        return result
