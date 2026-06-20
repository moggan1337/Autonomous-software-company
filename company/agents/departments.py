"""The seven department agents.

Each agent defines its persona (used as the Claude system prompt) and a
deterministic ``simulate`` method for when Claude is unavailable. Several agents
now use real tools: Analytics computes live metrics, Development validates the
code it writes, and QA independently re-checks that code and can reject it —
sending work back for a bounded rework loop.
"""
from __future__ import annotations

from .base import BaseAgent
from ..models import Department, Task

_DEV_PREFIXES = ("Implement ", "Fix issues in ", "Fix issues: ", "Fix ", "Rework ")
_QA_PREFIXES = ("Re-verify ", "Verify ", "Re-test ", "Test ")


def _strip(text: str, prefixes: tuple[str, ...]) -> str:
    for p in prefixes:
        if text.startswith(p):
            return text[len(p):]
    return text


class ProductAgent(BaseAgent):
    department = Department.PRODUCT
    role_description = (
        "You own product strategy. You turn directions into crisp specs with "
        "user stories, scope, and acceptance criteria, then route building to "
        "Development and positioning to Marketing."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        feature = task.title
        prior = " Builds on prior work." if context else ""
        spec = (
            f"# Product Spec: {feature}\n\n"
            f"## Problem\n{task.description or 'Address the stated direction.'}{prior}\n\n"
            "## User stories\n"
            f"- As a user, I want {feature.lower()} so that my workflow is faster.\n"
            "- As an admin, I want to configure it safely.\n\n"
            "## Scope\nMVP first, iterate based on Analytics.\n\n"
            "## Acceptance criteria\n"
            "- Core flow works end to end\n- Covered by automated tests\n- No P0/P1 defects"
        )
        return {
            "summary": f"Wrote the product spec for '{feature}' and routed build + positioning.",
            "verdict": None,
            "artifact": {"title": f"Spec: {feature}", "kind": "spec", "content": spec},
            "followups": [
                {
                    "department": "development",
                    "title": f"Implement {feature}",
                    "description": f"Build per spec for '{feature}'. Ship behind a flag.",
                    "priority": task.priority.value,
                },
                {
                    "department": "marketing",
                    "title": f"Position and message {feature}",
                    "description": f"Craft positioning and launch messaging for '{feature}'.",
                    "priority": "normal",
                },
            ],
        }


class DevelopmentAgent(BaseAgent):
    department = Department.DEVELOPMENT
    role_description = (
        "You are the engineering team. You implement features from specs with "
        "clean, validated code, then hand the build to QA. On a rework pass, you "
        "fix the specific defects QA reported."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        feature = _strip(task.title, _DEV_PREFIXES)
        is_rework = task.rework_count > 0 or task.title.startswith(("Fix", "Rework"))
        version = task.rework_count + 1
        code = (
            f"# Implementation v{version} for: {feature}\n"
            f"def {_slug(feature)}(config=None):\n"
            '    """Feature wired behind a flag, with a basic guard."""\n'
            "    config = config or {}\n"
            "    return {'ok': True, 'feature': %r}\n" % feature
        )
        ok, detail = self.tools.validate_code(f"{feature}_v{version}", code)
        status = "validated (compiles cleanly)" if ok else f"VALIDATION FAILED: {detail}"
        verb = "Fixed QA-reported defects in" if is_rework else "Implemented"
        return {
            "summary": f"{verb} '{feature}' (v{version}); code {status}. Sent to QA.",
            "verdict": None,
            "artifact": {
                "title": f"PR v{version}: {feature}",
                "kind": "code",
                "content": code + f"\n# build check: {detail}\n",
            },
            "followups": [
                {
                    "department": "qa",
                    "title": f"{'Re-verify' if is_rework else 'Verify'} {feature}",
                    "description": f"Run functional + regression checks for '{feature}' v{version}.",
                    "priority": task.priority.value,
                }
            ],
        }


class QAAgent(BaseAgent):
    department = Department.QA
    role_description = (
        "You are quality assurance. You independently verify the latest build, "
        "set a verdict of 'approved' or 'rejected', and never rubber-stamp. If you "
        "reject, describe the defect clearly so Development can fix it. When you "
        "approve, ask Support to prepare release notes."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        feature = _strip(task.title, _QA_PREFIXES)

        # Independently re-validate the latest code Development produced.
        code_hits = [h for h in self.tools.recall(feature, k=6) if h["kind"] == "code"]
        compile_ok, detail = (True, "no code artifact found to inspect")
        if code_hits:
            compile_ok, detail = self.tools.validate_code(f"qa_{feature}", code_hits[0]["content"])

        # A subset of features surface a defect on first verification (then pass
        # after one rework). Deterministic so the loop is reproducible & bounded.
        flaky = sum(ord(c) for c in feature) % 2 == 0
        first_pass = task.rework_count == 0
        rejected = (not compile_ok) or (flaky and first_pass)

        if rejected:
            issue = (
                "build does not compile" if not compile_ok
                else "edge-case defect: config=None path returns stale state"
            )
            report = (
                f"# QA Report: {feature} (REJECTED)\n\n"
                f"- Independent build check: {detail}\n"
                f"- Defect found: {issue}\n\nVerdict: REJECTED — returning to Development."
            )
            return {
                "summary": f"Rejected '{feature}': {issue}. Sent back to Development.",
                "verdict": "rejected",
                "artifact": {"title": f"QA Report: {feature} (rejected)", "kind": "report", "content": report},
                "followups": [],  # orchestrator opens the bounded rework task
            }

        report = (
            f"# QA Report: {feature} (APPROVED)\n\n"
            f"- Independent build check: {detail}\n"
            "- 24 functional tests: PASS\n- 112 regression tests: PASS\n"
            f"- Rework iterations before approval: {task.rework_count}\n\n"
            "Verdict: APPROVED for release."
        )
        return {
            "summary": f"Verified '{feature}': approved for release after {task.rework_count} rework(s).",
            "verdict": "approved",
            "artifact": {"title": f"QA Report: {feature} (approved)", "kind": "report", "content": report},
            "followups": [
                {
                    "department": "support",
                    "title": f"Prepare release notes for {feature}",
                    "description": f"Draft customer-facing release notes and FAQ for '{feature}'.",
                    "priority": "normal",
                }
            ],
        }


class MarketingAgent(BaseAgent):
    department = Department.MARKETING
    role_description = (
        "You are marketing. You create positioning, launch campaigns, and "
        "content, then hand qualified interest to Sales."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        topic = task.title
        campaign = (
            f"# Launch Campaign: {topic}\n\n"
            "- Hero message: 'Do more, faster.'\n"
            "- Channels: blog, email, social, in-product\n"
            "- CTA: Start free trial\n- KPI: signups, activation rate"
        )
        return {
            "summary": f"Built the launch campaign for '{topic}' and briefed Sales.",
            "verdict": None,
            "artifact": {"title": f"Campaign: {topic}", "kind": "campaign", "content": campaign},
            "followups": [
                {
                    "department": "sales",
                    "title": f"Outreach plan for {topic}",
                    "description": f"Convert campaign interest from '{topic}' into pipeline.",
                    "priority": "normal",
                }
            ],
        }


class SalesAgent(BaseAgent):
    department = Department.SALES
    role_description = (
        "You are sales. You qualify leads, run outreach, and close deals, "
        "keeping a clean view of pipeline."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        topic = _strip(task.title, ("Outreach plan for ",))
        plan = (
            f"# Sales Plan: {topic}\n\n"
            "- Target: existing accounts + inbound trials\n"
            "- Sequence: 3-touch email + 1 call\n- Goal: 20 qualified opps in 30 days"
        )
        return {
            "summary": f"Drafted the outreach plan for '{topic}' and loaded sequences.",
            "verdict": None,
            "artifact": {"title": f"Sales Plan: {topic}", "kind": "plan", "content": plan},
            "followups": [],
        }


class SupportAgent(BaseAgent):
    department = Department.SUPPORT
    role_description = (
        "You are customer support. You resolve customer issues with empathy and "
        "accuracy, reuse existing help content, write new content, and escalate "
        "genuine product gaps to Product Management."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        text = f"{task.title} {task.description}".lower()
        is_issue = any(w in text for w in ("bug", "broken", "error", "issue", "complaint", "crash"))
        prior = f" Referenced {len(context)} related prior item(s)." if context else ""
        if is_issue:
            reply = (
                f"Reply to customer re: {task.title}\n\n"
                "Thanks for flagging this — I've reproduced it and a fix is in progress. "
                f"I'll follow up the moment it ships. Workaround included below.{prior}"
            )
            return {
                "summary": f"Responded to the customer and escalated '{task.title}' to Product.",
                "verdict": None,
                "artifact": {"title": f"Support reply: {task.title}", "kind": "reply", "content": reply},
                "followups": [
                    {
                        "department": "product",
                        "title": f"Investigate reported issue: {task.title}",
                        "description": f"Customer-reported issue needs a product decision: {task.description}",
                        "priority": "high",
                    }
                ],
            }
        notes = (
            f"# Help content: {task.title}\n\n"
            f"Step-by-step guide and FAQ entries published to the help center.{prior}"
        )
        return {
            "summary": f"Published help content / release notes for '{task.title}'.",
            "verdict": None,
            "artifact": {"title": f"Help docs: {task.title}", "kind": "doc", "content": notes},
            "followups": [],
        }


class AnalyticsAgent(BaseAgent):
    department = Department.ANALYTICS
    role_description = (
        "You are analytics. You measure real outcomes from company data, surface "
        "insights, and recommend the next move grounded in the numbers."
    )

    def simulate(self, task: Task, context: list[dict]) -> dict:
        # Grounded: pull real operational metrics from the live database.
        report = self.tools.metrics_report(task.title)
        return {
            "summary": f"Analyzed '{task.title}' from live company data and recommended next steps.",
            "verdict": None,
            "artifact": {"title": f"Analytics: {task.title}", "kind": "report", "content": report},
            "followups": [],
        }


def _slug(text: str) -> str:
    cleaned = [c.lower() if c.isalnum() else " " for c in text]
    parts = "".join(cleaned).split()
    if not parts:
        return "feature"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


AGENT_CLASSES = {
    Department.PRODUCT: ProductAgent,
    Department.DEVELOPMENT: DevelopmentAgent,
    Department.QA: QAAgent,
    Department.MARKETING: MarketingAgent,
    Department.SALES: SalesAgent,
    Department.SUPPORT: SupportAgent,
    Department.ANALYTICS: AnalyticsAgent,
}
