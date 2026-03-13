"""
coding_agent.xai — XAI Integration for Coding Agent

v3.8: Agent decision chain tracing.
PRD → Plan → Implement → Validate → Fix 루프의
각 단계에서 왜 이런 결정이 내려졌는지 추적.

Phase 4-5: Domain Agent SDK의 설명 인프라.
모든 도메인 에이전트가 공유하는 decision audit trail 구조.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional


class AgentDecisionTracer:
    """
    Traces and explains coding agent's autonomous decisions.

    Each step in the PRD → Code → Validate → Fix loop generates
    a decision record with rationale, alternatives considered,
    and confidence level.

    v3.8 principle: "Human-in-the-Loop First"
    Full audit trail for every autonomous action.
    """

    def __init__(self):
        self.trace: list[dict[str, Any]] = []
        self.session_id = ""

    def start_session(self, prd_summary: str = "") -> str:
        """Start a new tracing session."""
        self.session_id = hashlib.sha256(
            f"{datetime.now(timezone.utc).isoformat()}{prd_summary}".encode()
        ).hexdigest()[:16]
        self.trace = []

        self.record_decision(
            step="session_start",
            action="Initialize agent session",
            rationale=f"PRD received: {prd_summary[:200]}",
            confidence=1.0,
        )
        return self.session_id

    def record_decision(
        self,
        step: str,
        action: str,
        rationale: str,
        confidence: float = 0.0,
        alternatives: Optional[list[dict[str, str]]] = None,
        evidence: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Record an agent decision with explanation.

        Parameters
        ----------
        step : str
            Pipeline step: "parsing", "planning", "code_generation",
            "validation", "auto_fix", "reporting"
        action : str
            What the agent decided to do
        rationale : str
            Why this action was chosen
        confidence : float
            0-1 confidence in the decision
        alternatives : list, optional
            Other options considered and why they were rejected
        evidence : dict, optional
            Supporting data for the decision
        metadata : dict, optional
            Additional context
        """
        record = {
            "session_id": self.session_id,
            "sequence": len(self.trace),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "action": action,
            "rationale": rationale,
            "confidence": confidence,
            "alternatives_considered": alternatives or [],
            "evidence": evidence or {},
            "metadata": metadata or {},
        }

        self.trace.append(record)
        return record

    def record_parsing_decision(
        self,
        prd_sections: list[str],
        requirements_extracted: int,
        ambiguities_found: list[str] = None,
    ) -> dict[str, Any]:
        """Record PRD parsing decisions."""
        return self.record_decision(
            step="parsing",
            action=f"Extracted {requirements_extracted} requirements from {len(prd_sections)} sections",
            rationale="Parsed PRD structure to identify functional and non-functional requirements",
            confidence=0.9 if not ambiguities_found else 0.7,
            evidence={
                "sections": prd_sections,
                "n_requirements": requirements_extracted,
                "ambiguities": ambiguities_found or [],
            },
        )

    def record_planning_decision(
        self,
        architecture: str,
        components: list[str],
        tech_stack: dict[str, str],
        alternatives_rejected: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        """Record architecture/planning decisions."""
        return self.record_decision(
            step="planning",
            action=f"Selected {architecture} architecture with {len(components)} components",
            rationale=(
                f"Architecture chosen based on PRD requirements: "
                f"scalability, maintainability, and deployment constraints"
            ),
            confidence=0.85,
            alternatives=alternatives_rejected,
            evidence={
                "architecture": architecture,
                "components": components,
                "tech_stack": tech_stack,
            },
        )

    def record_code_generation_decision(
        self,
        file_path: str,
        language: str,
        lines_generated: int,
        patterns_used: list[str] = None,
    ) -> dict[str, Any]:
        """Record code generation decisions."""
        return self.record_decision(
            step="code_generation",
            action=f"Generated {file_path} ({lines_generated} lines, {language})",
            rationale=f"Code generated following {', '.join(patterns_used or ['standard'])} patterns",
            confidence=0.8,
            evidence={
                "file": file_path,
                "language": language,
                "lines": lines_generated,
                "patterns": patterns_used or [],
            },
        )

    def record_validation_decision(
        self,
        validator: str,
        passed: bool,
        issues_found: int = 0,
        severity_summary: Optional[dict[str, int]] = None,
    ) -> dict[str, Any]:
        """Record validation decisions."""
        return self.record_decision(
            step="validation",
            action=f"{'PASSED' if passed else 'FAILED'}: {validator} ({issues_found} issues)",
            rationale=f"Validation with {validator} {'completed successfully' if passed else 'found issues requiring fix'}",
            confidence=1.0 if passed else 0.6,
            evidence={
                "validator": validator,
                "passed": passed,
                "issues_found": issues_found,
                "severity": severity_summary or {},
            },
        )

    def record_autofix_decision(
        self,
        issue: str,
        fix_applied: str,
        fix_attempt: int = 1,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Record auto-fix decisions."""
        return self.record_decision(
            step="auto_fix",
            action=f"Fix attempt {fix_attempt}/{max_attempts}: {fix_applied[:100]}",
            rationale=f"Auto-fix for: {issue[:200]}",
            confidence=max(0.3, 1.0 - (fix_attempt - 1) * 0.2),
            evidence={
                "issue": issue,
                "fix": fix_applied,
                "attempt": fix_attempt,
                "max_attempts": max_attempts,
                "bounded": True,  # v3.8: bounded auto-fix
            },
        )

    def get_trace(self) -> dict[str, Any]:
        """Get full decision trace."""
        return {
            "session_id": self.session_id,
            "n_decisions": len(self.trace),
            "trace": self.trace,
            "summary": self._generate_trace_summary(),
        }

    def get_audit_report(self) -> dict[str, Any]:
        """
        Generate audit-ready decision report.

        v3.8: Decision Evidence Trail
        Phase 5 target: EU AI Act 대응 자동 생성.
        """
        trace = self.get_trace()

        # Compute decision statistics
        steps = {}
        for record in self.trace:
            step = record.get("step", "unknown")
            if step not in steps:
                steps[step] = {"count": 0, "avg_confidence": 0, "decisions": []}
            steps[step]["count"] += 1
            steps[step]["avg_confidence"] += record.get("confidence", 0)
            steps[step]["decisions"].append({
                "action": record.get("action", ""),
                "confidence": record.get("confidence", 0),
            })

        for step in steps:
            count = steps[step]["count"]
            if count > 0:
                steps[step]["avg_confidence"] = round(
                    steps[step]["avg_confidence"] / count, 2
                )

        # Low confidence decisions
        low_confidence = [
            r for r in self.trace if r.get("confidence", 0) < 0.7
        ]

        return {
            "audit_report": {
                "session_id": self.session_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_decisions": len(self.trace),
                "step_summary": steps,
                "low_confidence_decisions": [
                    {
                        "step": r.get("step"),
                        "action": r.get("action"),
                        "confidence": r.get("confidence"),
                        "rationale": r.get("rationale"),
                    }
                    for r in low_confidence
                ],
                "human_review_needed": len(low_confidence) > 0,
                "review_reason": (
                    f"{len(low_confidence)} decision(s) below confidence threshold"
                    if low_confidence
                    else "All decisions above confidence threshold"
                ),
            },
            "full_trace": trace,
        }

    def _generate_trace_summary(self) -> str:
        if not self.trace:
            return "No decisions recorded."

        n = len(self.trace)
        steps = set(r.get("step", "") for r in self.trace)
        avg_conf = sum(r.get("confidence", 0) for r in self.trace) / n

        summary = (
            f"{n} decisions across {len(steps)} pipeline stages. "
            f"Average confidence: {avg_conf:.2f}. "
        )

        low = sum(1 for r in self.trace if r.get("confidence", 0) < 0.7)
        if low > 0:
            summary += f"{low} decision(s) flagged for human review."
        else:
            summary += "All decisions within confidence bounds."

        return summary
