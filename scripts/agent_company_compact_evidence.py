#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import parse_evidence_ref at every compact evidence boundary.
# ─────────────────

"""One fail-closed parser for canonical, Core, and source evidence refs."""

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import re
from typing import Final
from urllib.parse import unquote, urlsplit

from agent_company_deps import JsonValue
from agent_company_compact_safety import evidence_ref_is_valid, safe_text_is_valid
from agent_company_projection_policy import PolicyError


MAX_DECODE_LAYERS: Final[int] = 4
HEX_ESCAPE: Final = re.compile(r"[0-9A-Fa-f]{2}")


def contains_unsafe_control(value: str) -> bool:
    """Match the compact schema's forbidden control and bidi ranges."""
    return not safe_text_is_valid(value)


def _decode_once(value: str, label: str) -> str:
    offset = 0
    while True:
        marker = value.find("%", offset)
        if marker < 0:
            break
        escape = value[marker + 1 : marker + 3]
        if len(escape) != 2 or HEX_ESCAPE.fullmatch(escape) is None:
            raise PolicyError(f"{label}: evidence reference has a malformed percent escape")
        offset = marker + 3
    try:
        return unquote(value, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PolicyError(f"{label}: evidence reference has invalid encoded text") from exc


def _decode_layers(value: str, label: str) -> tuple[str, ...]:
    layers = [value]
    current = value
    _validate_layer(current, label)
    for _ in range(MAX_DECODE_LAYERS):
        expanded = _decode_once(current, label)
        if expanded == current:
            return tuple(layers)
        _validate_layer(expanded, label)
        layers.append(expanded)
        current = expanded
    if _decode_once(current, label) != current:
        raise PolicyError(f"{label}: evidence reference exceeds percent decode depth")
    return tuple(layers)


def _validate_layer(value: str, label: str) -> None:
    if not value:
        raise PolicyError(f"{label}: evidence reference must be non-empty")
    if (
        contains_unsafe_control(value)
        or any(character.isspace() for character in value)
        or "`" in value
        or "\\" in value
    ):
        raise PolicyError(f"{label}: evidence reference contains unsafe characters")
    lowered = value.casefold()
    if (
        value.startswith(("/", "~", "./", "../"))
        or lowered.startswith("file:")
        or "/users/" in lowered
        or "/home/" in lowered
        or ":/users/" in lowered
    ):
        raise PolicyError(f"{label}: evidence reference cannot expose an absolute or personal path")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise PolicyError(f"{label}: evidence reference has a malformed URI authority") from exc
    if (
        not parsed.scheme
        or not parsed.netloc
        or "@" in parsed.netloc
        or parsed.query
    ):
        raise PolicyError(f"{label}: evidence reference must be an authority-qualified URI")
    segments = (parsed.netloc, *parsed.path.split("/"))
    if any(segment in {".", ".."} for segment in segments):
        raise PolicyError(f"{label}: evidence reference cannot contain dot segments")


def parse_evidence_ref(value: JsonValue, label: str = "evidence reference") -> str:
    """Return a URI-like non-personal ref with no traversal or Markdown delimiter."""
    if not isinstance(value, str) or not value:
        raise PolicyError(f"{label}: evidence reference must be non-empty")
    layers = _decode_layers(value, label)
    if len(layers) > 2:
        raise PolicyError(f"{label}: evidence reference cannot use nested percent encoding")
    if not layers:
        raise PolicyError(f"{label}: evidence reference decoding produced no value")
    canonical = layers[-1]
    if not evidence_ref_is_valid(canonical):
        raise PolicyError(f"{label}: evidence reference is outside the canonical ASCII contract")
    return canonical
