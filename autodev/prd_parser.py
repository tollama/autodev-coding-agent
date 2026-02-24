from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PRDStruct:
    title: str
    goals: list[str]
    non_goals: list[str]
    features: list[dict[str, object]]
    nfr: dict[str, str]
    acceptance_criteria: list[str]
    performance_targets: dict[str, str]
    expected_load: dict[str, str]
    latency_sensitive_paths: list[str]
    cost_priority: str


def parse_prd_markdown(md: str) -> PRDStruct:
    title = "PRD"
    title_match = re.search(r"^#\s+(.+)$", md, flags=re.M)
    if title_match:
        title = title_match.group(1).strip()

    def extract_section(heading: str) -> str:
        pattern = rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)"
        section_match = re.search(pattern, md, flags=re.M)
        return section_match.group(1).strip() if section_match else ""

    def bullets(text: str) -> list[str]:
        items: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "*")):
                items.append(stripped[1:].strip())
        return items

    goals = bullets(extract_section("Goals"))
    non_goals = bullets(extract_section("Non-Goals"))
    acceptance_criteria = bullets(extract_section("Acceptance Criteria"))

    features_blob = extract_section("Features")
    features: list[dict[str, object]] = []
    for feature_match in re.finditer(
        r"^###\s+(.+)$([\s\S]*?)(?=^###\s+|\Z)", features_blob, flags=re.M
    ):
        name = feature_match.group(1).strip()
        body = feature_match.group(2).strip()
        features.append(
            {
                "name": name,
                "description": body[:1000],
                "bullets": bullets(body),
            }
        )

    nfr_blob = extract_section("Non-Functional Requirements")
    nfr: dict[str, str] = {}
    for line in nfr_blob.splitlines():
        stripped = line.strip()
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            nfr[key.strip()] = value.strip()

    performance_targets: dict[str, str] = {}
    for line in extract_section("Performance Targets").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            performance_targets[key.strip()] = value.strip()
        elif stripped.startswith(("-", "*")):
            bullet = stripped[1:].strip()
            if ":" in bullet:
                key, value = bullet.split(":", 1)
                performance_targets[key.strip()] = value.strip()
            else:
                performance_targets[bullet] = ""

    expected_load: dict[str, str] = {}
    for line in extract_section("Expected Load").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            expected_load[key.strip()] = value.strip()
        elif stripped.startswith(("-", "*")):
            bullet = stripped[1:].strip()
            if ":" in bullet:
                key, value = bullet.split(":", 1)
                expected_load[key.strip()] = value.strip()
            else:
                expected_load[bullet] = ""

    latency_sensitive_paths = bullets(extract_section("Latency Sensitive Paths"))

    cost_priority = ""
    cost_blob = extract_section("Cost Priority").strip()
    if cost_blob:
        cost_priority = cost_blob.splitlines()[0].strip().strip("- *")

    return PRDStruct(
        title=title,
        goals=goals,
        non_goals=non_goals,
        features=features,
        nfr=nfr,
        acceptance_criteria=acceptance_criteria,
        performance_targets=performance_targets,
        expected_load=expected_load,
        latency_sensitive_paths=latency_sensitive_paths,
        cost_priority=cost_priority,
    )

