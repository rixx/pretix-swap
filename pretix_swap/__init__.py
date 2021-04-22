from django.utils.translation import gettext_lazy

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")

__version__ = "0.1.0"


class PluginApp(PluginConfig):
    name = "pretix_swap"
    verbose_name = "Swap tickets with other attendees"

    class PretixPluginMeta:
        name = gettext_lazy("Swap tickets with other attendees")
        author = "Tobias Kunze"
        description = gettext_lazy(
            "Swap tickets, anonymously or with specific other attendees. Also supports canceling tickets if (and only if) another ticket is purchased."
        )
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2.7.0"

    def ready(self):
        from . import signals  # NOQA


default_app_config = "pretix_swap.PluginApp"
