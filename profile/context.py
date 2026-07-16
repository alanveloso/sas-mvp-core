"""Active spectrum profile selection via SAS_PROFILE."""

from __future__ import annotations

from config import get_settings
from profile.loader import clear_profile_cache, load_profile
from profile.schema import SpectrumProfile

DEFAULT_PROFILE_ID = "cbrs_winnforum"

_override_id: str | None = None


def active_profile_id() -> str:
    if _override_id:
        return _override_id
    profile_id = (get_settings().sas_profile or DEFAULT_PROFILE_ID).strip()
    return profile_id or DEFAULT_PROFILE_ID


def get_active_profile() -> SpectrumProfile:
    return load_profile(active_profile_id())


def set_active_profile(profile_id: str) -> SpectrumProfile:
    """Force-select a profile (tests / admin). Clears loader cache for that id."""
    global _override_id
    _override_id = profile_id
    clear_profile_cache()
    return get_active_profile()


def reload_active_profile() -> SpectrumProfile:
    clear_profile_cache()
    return get_active_profile()


def clear_profile_override() -> None:
    global _override_id
    _override_id = None
    clear_profile_cache()
