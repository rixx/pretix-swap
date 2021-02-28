from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nModelForm
from pretix.base.forms import SettingsForm
from pretix.base.models import Item

from .models import SwapGroup


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
