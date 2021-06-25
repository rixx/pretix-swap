from django.db.models import Q


def get_target_subevents(position, swap_type):
    from pretix.base.models.event import SubEvent

    result = set()
    groups = position.order.event.swap_groups.all().filter(
        Q(items__isnull=True) | Q(items__in=[position.item]),
        swap_type=swap_type,
    )
    for group in groups:
        result |= set(group.subevents.all().values_list("id", flat=True))
    return SubEvent.objects.filter(pk__in=result).exclude(pk=position.subevent.pk)


def get_valid_swap_types(position):
    from .models import SwapRequest

    actions = set(
        position.order.event.swap_groups.all()
        .filter(
            Q(items__isnull=True) | Q(items__in=[position.item]),
            subevents__in=[position.subevent],
        )
        .values_list("swap_type", flat=True)
    )
    result = []
    event = position.order.event
    if event.settings.swap_orderpositions and SwapRequest.Types.SWAP in actions:
        result.append(SwapRequest.Types.SWAP)
    if (
        event.settings.cancel_orderpositions
        and SwapRequest.Types.CANCELATION in actions
    ):
        result.append(SwapRequest.Types.CANCELATION)
    return result


def test_swap_groups(groups, item, subevent, other_subevent=None):
    for group in groups:
        if group.items.all() and item not in group.items.all():
            continue
        if subevent not in group.subevents.all():
            continue
        if not other_subevent or other_subevent in group.subevents.all():
            return True
    return False


def can_be_swapped(event, item, subevent, other_subevent):
    from .models import SwapGroup

    groups = event.swap_groups.filter(swap_type=SwapGroup.Types.SWAP).prefetch_related(
        "subevents", "items"
    )
    return test_swap_groups(groups, item, subevent, other_subevent)


def can_be_canceled(event, item, subevent):
    from .models import SwapGroup

    groups = event.swap_groups.filter(
        swap_type=SwapGroup.Types.CANCELATION
    ).prefetch_related("subevents", "items")
    return test_swap_groups(groups, item, subevent)


def get_applicable_subevents(event):
    result = set()
    for swap_group in event.swap_groups.all().prefetch_related("subevents"):
        result |= set(swap_group.subevents.all())
    return result


def get_swappable_subevents(item, groups=None):
    from .models import SwapGroup

    groups = groups or item.event.swap_groups.filter(
        swap_type=SwapGroup.Types.SWAP
    ).prefetch_related("subevents")
    result = set()
    for group in groups:
        if item in group.subevents.all():
            result |= set(group.subevents.all())
    return result


def get_cancelable_subevents(item, groups=None):
    from .models import SwapGroup

    groups = groups or item.event.swap_groups.filter(
        swap_type=SwapGroup.Types.CANCELATION
    ).prefetch_related("subevents")
    result = set()
    for group in groups:
        if item in group.subevents.all():
            result |= set(group.subevents.all())
    return result


def match_open_swap_requests(event):
    """Can be used in admin actions and runperiodic.

    Attempts to find matches for all open requests. Shouldn't be many,
    usually these will get caught on request creation.
    """
    from .models import SwapRequest

    # This is only an approximation of legal swaps. There is a detailed check run when the swap is about to be performed
    subevents = get_swappable_subevents()
    open_requests = (
        SwapRequest.objects.filter(
            position__order__event_id=event.pk,
            state=SwapRequest.States.REQUESTED,
            swap_method=SwapRequest.Methods.FREE,
            swap_type=SwapRequest.Types.SWAP,
            position__subevent__in=subevents,
            target_subevent__in=subevents,
            partner__isnull=True,
        )
        .select_related("position", "position__item", "position__subevent")
        .order_by("requested")
    )

    matched_requests = set()

    for request in open_requests:
        if request.pk in matched_requests:
            continue

        matches = open_requests.exclude(pk__in=matched_requests,).filter(
            target_subevent=request.position.subevent,
            position__subevent=request.target_subevent,
            position__item=request.position.item,
        )
        if request.position.variation:
            matches = matches.filter(position__variation=request.position.variation)

        for other in matches:
            try:
                request.swap_with(other)
                matched_requests.add(request.pk)
                matched_requests.add(other.pk)
                break
            except Exception:
                continue
