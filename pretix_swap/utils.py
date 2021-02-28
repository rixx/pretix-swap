def get_applicable_items(event):
    result = set()
    for swap_group in event.swap_groups.all().prefetch_related("left", "right"):
        result |= set(swap_group.left.all())
        result |= set(swap_group.right.all())
    return result
