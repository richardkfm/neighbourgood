"""Blue Sky / Red Sky mode resolution.

Every community stores its own mode (changed by admin toggles and member
votes). ``NG_PLATFORM_MODE=red`` puts the whole instance into Red Sky: every
community then *behaves* as red, while its stored mode is kept and applies
again once the instance returns to blue. All behaviour checks go through
``effective_mode``; only toggles and votes read or write ``Community.mode``.
"""

from app.config import settings


def is_global_red() -> bool:
    """Whether the instance-wide mode forces Red Sky on every community."""
    return settings.platform_mode == "red"


def effective_mode(community) -> str:
    """The mode a community behaves as: "red" if the instance or the community is red."""
    if is_global_red():
        return "red"
    stored = getattr(community, "mode", None) if community is not None else None
    return "red" if stored == "red" else "blue"


def is_red(community) -> bool:
    return effective_mode(community) == "red"
