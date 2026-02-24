"""Core utilities for the generated library template."""

from __future__ import annotations

from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised when inputs violate contract expectations."""


def normalize_identifier(value: str) -> str:
    """Normalize user-facing identifiers to a safe canonical form."""
    if not value or not isinstance(value, str):
        raise ValidationError("identifier must be a non-empty string")

    normalized = value.strip().lower().replace(" ", "_")
    if not normalized or "." in normalized:
        raise ValidationError("identifier must not contain dots and must be non-empty")

    return normalized


def split_csv_items(raw: str | None) -> list[str]:
    """Split CSV strings into non-empty values."""
    if raw is None:
        return []
    if not isinstance(raw, str):
        raise ValidationError("csv input must be a string")

    values = [item.strip() for item in raw.split(",")]
    return [item for item in values if item]
