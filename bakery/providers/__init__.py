"""Provider contract for Bakery backends."""

from bakery.providers.registry import (
    get_provider,
    list_providers,
)

__all__ = ["get_provider", "list_providers"]
