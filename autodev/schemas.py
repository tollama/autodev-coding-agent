from __future__ import annotations

from typing import Any

ROLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["role", "summary", "writes", "next_role", "notes"],
    "properties": {
        "role": {"type": "string"},
        "summary": {"type": "string"},
        "writes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "next_role": {"type": ["string", "null"]},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

