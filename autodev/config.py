from __future__ import annotations

from typing import Any, Dict, List

import yaml

from .schemas import VALIDATORS

_POLICY_SECTIONS = {"per_task", "final"}
_POLICY_KEYS = {"soft_fail"}

def _fmt_path(path_parts: List[str]) -> str:
    if not path_parts:
        return "<root>"
    return ".".join(path_parts)

def _validate_string_list(value: Any, path_parts: List[str], errors: List[str]) -> List[str]:
    if not isinstance(value, list):
        errors.append(f"{_fmt_path(path_parts)} must be a list of strings.")
        return []
    out: List[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{_fmt_path(path_parts + [f'[{i}]'])} must be a string.")
            continue
        out.append(item)
    return out

def _validate_validator_policy(
    profile_name: str,
    policy: Any,
    errors: List[str],
) -> None:
    base = ["profiles", profile_name, "validator_policy"]
    if policy is None:
        return
    if not isinstance(policy, dict):
        errors.append(f"{_fmt_path(base)} must be an object.")
        return

    unknown_sections = sorted(set(policy.keys()) - _POLICY_SECTIONS)
    if unknown_sections:
        errors.append(
            f"{_fmt_path(base)} has unknown section(s): {unknown_sections}. "
            f"Allowed sections: {sorted(_POLICY_SECTIONS)}."
        )

    known_set = set(VALIDATORS)
    for section in sorted(_POLICY_SECTIONS):
        if section not in policy:
            continue
        section_value = policy[section]
        section_path = base + [section]
        if not isinstance(section_value, dict):
            errors.append(f"{_fmt_path(section_path)} must be an object.")
            continue
        unknown_keys = sorted(set(section_value.keys()) - _POLICY_KEYS)
        if unknown_keys:
            errors.append(
                f"{_fmt_path(section_path)} has unknown key(s): {unknown_keys}. "
                f"Allowed keys: {sorted(_POLICY_KEYS)}."
            )

        if "soft_fail" not in section_value:
            continue
        soft_fail = _validate_string_list(section_value["soft_fail"], section_path + ["soft_fail"], errors)
        for i, name in enumerate(soft_fail):
            item_path = _fmt_path(section_path + [f"soft_fail[{i}]"])
            if name not in known_set:
                errors.append(
                    f"{item_path} has unknown validator '{name}'. "
                    f"Allowed validators: {VALIDATORS}."
                )

def _validate_config(config: Any) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(config, dict):
        raise ValueError("Invalid config: top-level YAML must be an object.")

    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        errors.append("profiles must be an object mapping profile name to settings.")
        profiles = {}

    known_set = set(VALIDATORS)
    for profile_name, profile in profiles.items():
        profile_path = ["profiles", str(profile_name)]
        if not isinstance(profile, dict):
            errors.append(f"{_fmt_path(profile_path)} must be an object.")
            continue

        validators_value = profile.get("validators")
        validators: List[str] = _validate_string_list(validators_value, profile_path + ["validators"], errors)
        for i, name in enumerate(validators):
            item_path = _fmt_path(profile_path + [f"validators[{i}]"])
            if name not in known_set:
                errors.append(
                    f"{item_path} has unknown validator '{name}'. "
                    f"Allowed validators: {VALIDATORS}."
                )

        _validate_validator_policy(
            profile_name=str(profile_name),
            policy=profile.get("validator_policy"),
            errors=errors,
        )

    if errors:
        msg = "Invalid config:\n- " + "\n- ".join(errors)
        raise ValueError(msg)
    return config

def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _validate_config(raw)
