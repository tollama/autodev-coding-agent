from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml

from .schemas import VALIDATORS

_POLICY_SECTIONS = {"per_task", "final"}
_POLICY_KEYS = {"soft_fail"}
_QUALITY_PROFILE_KEYS = {
    "name",
    "validator_policy",
    "per_task_soft",
    "final_soft",
    "by_level",
    "escalation",
}
_AUTODEV_API_KEY_ENV = "AUTODEV_LLM_API_KEY"
_AUTODEV_API_KEY_PLACEHOLDER = f"${{{_AUTODEV_API_KEY_ENV}}}"


def _resolve_api_key(value: Any) -> Any:
    if isinstance(value, str) and value == _AUTODEV_API_KEY_PLACEHOLDER:
        return os.getenv(_AUTODEV_API_KEY_ENV)
    return value


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
    path_prefix: List[str] | None = None,
) -> None:
    base = path_prefix or ["profiles", profile_name, "validator_policy"]
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


def _validate_profile_soft_lists(
    quality_obj: Any,
    errors: List[str],
    base: List[str],
) -> None:
    """Validate compact quality profile fields (per_task_soft, final_soft)."""
    known_set = set(VALIDATORS)
    if not isinstance(quality_obj, dict):
        return
    for key in ("per_task_soft", "final_soft"):
        if key not in quality_obj:
            continue
        values = _validate_string_list(quality_obj[key], base + [key], errors)
        for i, name in enumerate(values):
            if name not in known_set:
                errors.append(
                    f"{_fmt_path(base + [key, f'[{i}]'])} has unknown validator '{name}'. "
                    f"Allowed validators: {VALIDATORS}."
                )


def _validate_by_level_profiles(
    profile_name: str,
    by_level: Any,
    errors: List[str],
    path_prefix: List[str],
) -> None:
    if by_level is None:
        return
    if not isinstance(by_level, dict):
        errors.append(f"{_fmt_path(path_prefix)} must be an object.")
        return

    for level_name, level_config in by_level.items():
        level_path = path_prefix + [str(level_name)]
        if not isinstance(level_config, dict):
            errors.append(f"{_fmt_path(level_path)} must be an object.")
            continue

        unknown_level_keys = sorted(set(level_config.keys()) - _QUALITY_PROFILE_KEYS)
        if unknown_level_keys:
            errors.append(
                f"{_fmt_path(level_path)} has unknown key(s): {unknown_level_keys}. "
                f"Allowed keys: {sorted(_QUALITY_PROFILE_KEYS)}."
            )

        _validate_profile_soft_lists(level_config, errors, level_path)
        _validate_validator_policy(
            profile_name=f"{profile_name}:{level_name}",
            policy=level_config.get("validator_policy"),
            errors=errors,
            path_prefix=level_path + ["validator_policy"],
        )

        level_esc = level_config.get("escalation")
        if level_esc is None:
            continue
        if not isinstance(level_esc, dict):
            errors.append(f"{_fmt_path(level_path + ['escalation'])} must be an object.")
            continue

        unknown = sorted(set(level_esc.keys()) - {"repeat_failure_guard"})
        if unknown:
            errors.append(
                f"{_fmt_path(level_path + ['escalation'])} has unknown key(s): {unknown}. "
                "Allowed keys: ['repeat_failure_guard']."
            )

        repeat_guard = level_esc.get("repeat_failure_guard")
        if repeat_guard is None:
            continue
        if not isinstance(repeat_guard, dict):
            errors.append(f"{_fmt_path(level_path + ['escalation', 'repeat_failure_guard'])} must be an object.")
            continue

        enabled = repeat_guard.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            errors.append(
                f"{_fmt_path(level_path + ['escalation', 'repeat_failure_guard', 'enabled'])} must be a boolean."
            )

        repeats = repeat_guard.get("max_retries_before_targeted_fix")
        if repeats is not None:
            if not isinstance(repeats, int) or repeats < 0:
                errors.append(
                    f"{_fmt_path(level_path + ['escalation', 'repeat_failure_guard', 'max_retries_before_targeted_fix'])} "
                    "must be a non-negative integer."
                )


def _validate_quality_profile(profile_name: str, quality_profile: Any, errors: List[str]) -> None:
    base = ["profiles", str(profile_name), "quality_profile"]
    if quality_profile is None:
        return
    if not isinstance(quality_profile, dict):
        errors.append(f"{_fmt_path(base)} must be an object.")
        return

    unknown_keys = sorted(set(quality_profile.keys()) - _QUALITY_PROFILE_KEYS)
    if unknown_keys:
        errors.append(
            f"{_fmt_path(base)} has unknown key(s): {unknown_keys}. "
            f"Allowed keys: {sorted(_QUALITY_PROFILE_KEYS)}."
        )

    name = quality_profile.get("name")
    if name is not None and name not in {"minimal", "balanced", "strict"}:
        errors.append(f"{_fmt_path(base + ['name'])} must be one of ['minimal', 'balanced', 'strict']")

    _validate_validator_policy(
        profile_name=profile_name,
        policy=quality_profile.get("validator_policy"),
        errors=errors,
        path_prefix=base + ["validator_policy"],
    )

    _validate_profile_soft_lists(quality_profile, errors, base)

    _validate_by_level_profiles(
        profile_name=str(profile_name),
        by_level=quality_profile.get("by_level"),
        errors=errors,
        path_prefix=base + ["by_level"],
    )

    escalation = quality_profile.get("escalation")
    if escalation is None:
        return
    if not isinstance(escalation, dict):
        errors.append(f"{_fmt_path(base + ['escalation'])} must be an object.")
        return

    unknown_guard_sections = sorted(set(escalation.keys()) - {"repeat_failure_guard"})
    if unknown_guard_sections:
        errors.append(
            f"{_fmt_path(base + ['escalation'])} has unknown key(s): {unknown_guard_sections}. "
            "Allowed keys: ['repeat_failure_guard']."
        )

    repeat_guard = escalation.get("repeat_failure_guard")
    if repeat_guard is None:
        return
    if not isinstance(repeat_guard, dict):
        errors.append(f"{_fmt_path(base + ['escalation', 'repeat_failure_guard'])} must be an object.")
        return

    enabled = repeat_guard.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        errors.append(
            f"{_fmt_path(base + ['escalation', 'repeat_failure_guard', 'enabled'])} must be a boolean."
        )

    repeats = repeat_guard.get("max_retries_before_targeted_fix")
    if repeats is not None:
        if not isinstance(repeats, int) or repeats < 0:
            errors.append(
                f"{_fmt_path(base + ['escalation', 'repeat_failure_guard', 'max_retries_before_targeted_fix'])} "
                "must be a non-negative integer."
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
        _validate_quality_profile(
            profile_name=str(profile_name),
            quality_profile=profile.get("quality_profile"),
            errors=errors,
        )

    llm_cfg = config.get("llm")
    if isinstance(llm_cfg, dict):
        llm_cfg["api_key"] = _resolve_api_key(llm_cfg.get("api_key"))

    if errors:
        msg = "Invalid config:\n- " + "\n- ".join(errors)
        raise ValueError(msg)
    return config


def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _validate_config(raw)
