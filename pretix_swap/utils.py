def get_applicable_items(event):
    result = set()
    for swap_group in event.swap_groups.all().prefetch_related("items"):
        result |= set(swap_group.items.all())
    return result


def get_swappable_items(item, groups=None):
    from .models import SwapGroup

    groups = groups or item.event.swap_groups.filter(
        swap_type=SwapGroup.Types.SWAP
    ).prefetch_related("items")
    result = set()
    for group in groups:
        if item in group.items.all():
            result |= set(group.items.all())
    return result


def get_cancelable_items(item, groups=None):
    from .models import SwapGroup

    groups = groups or item.event.swap_groups.filter(
        swap_type=SwapGroup.Types.CANCELATION
    ).prefetch_related("items")
    result = set()
    for group in groups:
        if item in group.items.all():
            result |= set(group.items.all())
    return result


def match_open_swap_requests(event):
    """Can be used in admin actions and runperiodic.

    Attempts to find matches for all open requests. A bit stupid about
    it.
    """
    from .models import SwapGroup, SwapRequest

    groups = event.swap_groups.filter(swap_type=SwapGroup.Types.SWAP).prefetch_related(
        "items"
    )
    open_requests = (
        SwapRequest.objects.filter(
            position__order__event_id=event.pk,
            state=SwapRequest.States.REQUESTED,
            swap_method=SwapRequest.Methods.FREE,
            swap_type=SwapRequest.Types.SWAP,
        )
        .select_related("position", "position__item")
        .order_by("requested")
    )  # TODO is this the right ordering
    requested_items = set(open_requests.values_list("position__item", flat=True))

    for item in requested_items:
        swappables = get_swappable_items(item, groups=groups)
        if not swappables:
            # TODO warn or yell or … do something. These are orphaned requests!
            continue
        for request, other in zip(
            open_requests.filter(position__item=item),
            open_requests.filter(position__item__in=swappables),
        ):
            request.swap_with(other)
