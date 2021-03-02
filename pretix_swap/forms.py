from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nModelForm
from pretix.base.forms import SettingsForm
from pretix.base.models import Item

from .models import SwapGroup, SwapRequest
from .utils import get_applicable_items, get_cancelable_items, get_swappable_items


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

        is_swap = cleaned_data.get("swap_type") == SwapGroup.Types.SWAP
        if is_swap:
            if left & right:
                items = ", ".join(str(item.name) for item in (left & right))
                raise ValidationError(
                    str(
                        _(
                            "Please include every item only on one side! Incorrect item(s): {items}"
                        )
                    ).format(items=items)
                )
        prices = set()
        for item in left | right:
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
            "left",
            "right",
        )
        field_classes = {
            "left": ItemModelMultipleChoiceField,
            "right": ItemModelMultipleChoiceField,
        }


class PositionModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, instance):
        label = str(instance)
        if instance.attendee_name:
            return f"{label} ({instance.attendee_name})"
        return label


class SwapRequestForm(forms.Form):
    def __init__(self, *args, order=None, swap_actions=None, **kwargs):
        self.order = order
        self.event = order.event
        initial_position = kwargs.pop("position", None)
        super().__init__(*args, **kwargs)
        items = get_applicable_items(self.event)
        relevant_positions = [
            position
            for position in order.positions.all()
            if position.item in items
            and (
                all(
                    state.state == SwapRequest.States.COMPLETED
                    for state in position.swap_states.all()
                )
            )
        ]
        self.fields["position"] = PositionModelChoiceField(
            self.order.positions.filter(pk__in=[p.pk for p in relevant_positions]),
            initial=initial_position,
            label=_("Which item do you want to change?"),
        )
        for position in relevant_positions:
            field = forms.ModelChoiceField(
                Item.objects.filter(
                    pk__in=[item.pk for item in get_swappable_items(position.item)]
                ),
                label=_("Which product do you want instead?"),
                required=False,
                initial=None,
            )
            field.position = position
            self.fields[f"position_choice_{position.pk}"] = field

        self.fields["swap_type"] = forms.ChoiceField(
            initial=swap_actions[0],
            choices=swap_actions,
            label=_("What do you want to do?"),
        )
        if (
            any(SwapRequest.Types.SWAP == action[0] for action in swap_actions)
            and self.event.settings.swap_orderpositions_specific
        ):
            self.fields["swap_code"] = forms.CharField(
                required=False,
                label=_("Swap code"),
                help_text=_(
                    "Do you already know who you want to swap with? Enter their swap code here!"
                ),
            )
            self.fields["swap_method"] = forms.ChoiceField(
                label=_("Swap method"),
                choices=(
                    (
                        SwapRequest.Methods.FREE,
                        _("Switch with the next interested person."),
                    ),
                    (
                        SwapRequest.Methods.SPECIFIC,
                        _("I want to switch with a specific person."),
                    ),
                ),
            )
        if (
            any(SwapRequest.Types.CANCELATION == action[0] for action in swap_actions)
            and self.event.settings.cancel_orderpositions_specific
        ):
            self.fields["cancel_code"] = forms.CharField(
                required=False,
                label=_("Cancel code"),
                help_text=_(
                    "Do you already know who should take your place? Enter their waiting list code here!"
                ),
            )
            self.fields["cancel_method"] = forms.ChoiceField(
                label=_("Cancelation method"),
                choices=(
                    (
                        SwapRequest.Methods.FREE,
                        _("Give my place to the next person in line."),
                    ),
                    (
                        SwapRequest.Methods.SPECIFIC,
                        _("I want my place to go to a specific person."),
                    ),
                ),
            )

    @property
    def position_fields(self):
        return [
            self[name]
            for name in self.fields.keys()
            if name.startswith("position_choice_")
        ]

    def save(self):
        data = self.cleaned_data
        swap_type = data.get("swap_type")
        swap_method = (
            data.get("cancel_method")
            if swap_type == SwapRequest.Types.CANCELATION
            else data.get("swap_method")
        )
        instance = SwapRequest.objects.create(
            position=data["position"],
            target_item=data.get(f"position{data['position'].pk}"),
            target_order=data.get("cancel_code"),
            state=SwapRequest.States.REQUESTED,
            swap_type=swap_type,
            swap_method=swap_method or SwapRequest.Methods.FREE,
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
            if data.get("swap_code"):
                instance.swap_with(data.get("swap_code"))
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
        return instance

    def clean(self):
        cleaned_data = super().clean()
        if not (
            cleaned_data["swap_type"] == SwapRequest.Types.SWAP
            and cleaned_data["swap_method"] == SwapRequest.Methods.SPECIFIC
        ):
            cleaned_data["swap_code"] = None
        if not (
            cleaned_data["swap_type"] == SwapRequest.Types.CANCELATION
            and cleaned_data["cancel_method"] == SwapRequest.Methods.SPECIFIC
        ):
            cleaned_data["cancel_code"] = None
        return cleaned_data

    def clean_swap_code(self):
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
        position = self.cleaned_data.get(
            "position"
        )  # TODO this is a potential error source
        items = get_swappable_items(position.item)
        if partner.position.item not in items:
            raise ValidationError(
                str(
                    _(
                        "The swap code you entered is for the item '{other_item}', "
                        "which is not compatible with your item '{your_item}'."
                    )
                ).format(other_item=partner.position.item, your_item=position.item)
            )
        self.partner = partner
        return partner

    def clean_cancel_code(self):
        data = self.cleaned_data.get("cancel_code")
        if not data:
            raise ValidationError(
                _(
                    "If you want to give your ticket to somebody specific, please provide a cancelation code."
                )
            )

        order = self.event.orders.filter(code__iexact=data).first()
        if not order:
            raise ValidationError(_("Unknown cancelation code."))

        position = self.cleaned_data.get(
            "position"
        )  # TODO this is a potential error source
        items = get_cancelable_items(position.item)
        other_position = (
            order.positions.first()
        )  # TODO we just assume that this order has only one position
        if other_position.item not in items:
            raise ValidationError(
                str(
                    _(
                        "The cancelation code you entered is for the item '{other_item}', "
                        "which is not compatible with your item '{your_item}'."
                    )
                ).format(other_item=other_position.item, your_item=position.item)
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


class CancelationForm(forms.Form):
    def __init__(self, *args, items=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.items = items
        for item in items:
            self.fields[f"item_{item['item'].pk}"] = forms.IntegerField(
                min_value=0,
                required=False,
                label="",
            )
