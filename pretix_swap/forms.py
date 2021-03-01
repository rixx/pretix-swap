from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField
from i18nfield.forms import I18nModelForm
from pretix.base.forms import SettingsForm
from pretix.base.models import Item

from .models import SwapGroup, SwapState
from .utils import get_applicable_items


class SwapSettingsForm(SettingsForm):
    swap_orderpositions = forms.BooleanField(
        label=_("Allow customers to swap order positions"), required=False
    )
    swap_orderpositions_specific = forms.BooleanField(
        label=_("Allow customers to swap with a specific other order position"),
        required=False,
    )
    cancel_orderpositions = forms.BooleanField(
        label=_("Allow customers to request to cancel orderpositions"), required=False
    )
    cancel_orderpositions_specific = forms.BooleanField(
        label=_(
            "Allow customers to request to cancel orderpositions for a specific waiting list entry"
        ),
        required=False,
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


class SwapGroupForm(I18nModelForm):
    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        kwargs["locales"] = self.event.settings.locales if self.event else ["en"]
        super().__init__(*args, **kwargs)
        self.fields["left"].queryset = Item.objects.filter(event=event)
        self.fields["right"].queryset = Item.objects.filter(event=event)

    def save(self, *args, **kwargs):
        self.instance.event = self.event
        return super().save(*args, **kwargs)

    def clean_left(self):
        data = self.cleaned_data.get("left")
        if not data:
            raise ValidationError(
                _("Please select at least one item on the left side!")
            )
        return data

    def clean_right(self):
        data = self.cleaned_data.get("right")
        if not data:
            raise ValidationError(
                _("Please select at least one item on the right side!")
            )
        return data

    def clean(self):
        cleaned_data = super().clean()
        left = set(cleaned_data.get("left") or [])
        right = set(cleaned_data.get("right") or [])
        if left & right:
            items = ", ".join(str(item.name) for item in (left & right))
            raise ValidationError(
                str(
                    _(
                        "Please include every item only on one side! Incorrect item(s): {items}"
                    )
                ).format(items=items)
            )
        return cleaned_data

    class Meta:
        model = SwapGroup
        fields = ("name", "left", "right", "only_same_price", "price_tolerance")
        field_classes = {
            "left": SafeModelMultipleChoiceField,
            "right": SafeModelMultipleChoiceField,
        }


class SwapRequestForm(forms.ModelForm):
    def __init__(self, *args, order=None, swap_actions=None, **kwargs):
        self.order = order
        self.event = order.event
        initial_position = kwargs.pop("position", None)
        super().__init__(*args, **kwargs)
        items = get_applicable_items(self.event)
        positions = [
            position.pk
            for position in order.positions.all()
            if position.item in items
            and (
                all(
                    state.state == SwapState.SwapStates.COMPLETED
                    for state in position.swap_states.all()
                )
            )
        ]
        self.fields["position"] = forms.ModelChoiceField(
            self.order.positions.filter(pk__in=positions),
            initial=initial_position,
        )
        self.action = None
        if len(swap_actions) == 1:
            self.swap_type = swap_actions[0]
        else:  # We can both swap and cancel
            self.fields["swap_type"] = forms.ChoiceField(
                choices=[
                    (SwapState.SwapTypes.SWAP, _("Request a swap")),
                    (SwapState.SwapTypes.CANCELATION, _("Request to cancel")),
                ],
                label=_("Action"),
            )
        if (
            SwapState.SwapTypes.SWAP in swap_actions
            and self.event.settings.swap_orderpositions_specific
        ):
            self.fields["swap_code"] = forms.CharField(
                required=False,
                label=_("Swap code"),
                help_text=_(
                    "Do you already know who you want to swap with? Enter their swap code here!"
                ),
            )
        if (
            SwapState.SwapTypes.CANCELATION in swap_actions
            and self.event.settings.cancel_orderpositions_specific
        ):
            self.fields["cancel_code"] = forms.CharField(
                required=False,
                label=_("Cancel code"),
                help_text=_(
                    "Do you already know who should take your place? Enter their waiting list code here!"
                ),
            )
        if "cancel_code" not in self.fields and "swap_code" not in self.fields:
            self.fields.pop("swap_method")

    def save(self):
        data = self.cleaned_data
        instance = SwapState.objects.create(
            position=data["position"],
            state=SwapState.SwapStates.REQUESTED,
            swap_type=data.get("swap_type") or self.swap_type,
            swap_method=data.get("swap_method") or SwapState.SwapMethods.FREE,
        )
        if instance.swap_type == SwapState.SwapTypes.SWAP:
            if data.get("swap_code"):
                instance.swap_with(data.get("swap_code"))
            elif instance.swap_method == SwapState.SwapMethods.FREE:
                instance.attempt_swap()
        elif instance.swap_type == SwapState.SwapTypes.CANCELATION:
            if data.get("cancel_code"):
                instance.cancel_for(data.get("swap_code"))
            elif instance.swap_method == SwapState.SwapMethods.FREE:
                instance.attempt_swap()
        return instance

    def clean_swap_code(self):
        data = self.cleaned_data.get("swap_code")
        if not data:
            return data
        if self.action and self.action != SwapState.SwapTypes.SWAP:
            return
        if self.cleaned_data.get("action") != SwapState.SwapTypes.SWAP:
            return

        partner = SwapState.objects.filter(
            position__order__event=self.event,
            swap_code=data,
            state=SwapState.SwapStates.REQUESTED,
        ).first()
        if not partner:
            raise ValidationError(_("Unknown swap code!"))
        # TODO validate that the items are actually compatible!
        self.partner = partner
        return partner

    def clean_cancel_code(self):
        data = self.cleaned_data.get("cancel_code")
        if not data:
            return data
        if self.action and self.action != SwapState.SwapTypes.CANCELATION:
            return
        if self.cleaned_data.get("action") != SwapState.SwapTypes.CANCELATION:
            return

        # TODO find cart or … something? help?
        return data

    class Meta:
        model = SwapState
        field_classes = {
            "position": SafeModelChoiceField,
        }
        fields = ("swap_method",)
