"""The seven department agents.

Each agent defines its persona (used as the Claude system prompt) and a
deterministic ``simulate`` method that produces realistic output — including the
follow-up tasks that make work cascade across the company — when Claude is not
available.
"""
from __future__ import annotations

from .base import BaseAgent
from ..models import Department, Task


class ProductAgent(BaseAgent):
    department = Department.PRODUCT
    role_description = (
        "You own product strategy. You turn directions into crisp specs with "
        "user stories, scope, and acceptance criteria, then route building to "
        "Development and positioning to Marketing."
    )

    def simulate(self, task: Task) -> dict:
        feature = task.title
        spec = (
            f"# Product Spec: {feature}\n\n"
            f"## Problem\n{task.description or 'Address the stated direction.'}\n\n"
            "## User stories\n"
            f"- As a user, I want {feature.lower()} so that my workflow is faster.\n"
            "- As an admin, I want to configure it safely.\n\n"
            "## Scope\nMVP first, iterate based on Analytics.\n\n"
            "## Acceptance criteria\n"
            "- Core flow works end to end\n- Covered by automated tests\n- No P0/P1 defects"
        )
        return {
            "summary": f"Wrote the product spec for '{feature}' and routed build + positioning.",
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
        "clean, tested code, then hand the build to QA for verification."
    )

    def simulate(self, task: Task) -> dict:
        feature = task.title.replace("Implement ", "")
        code = (
            f"// Implementation for: {feature}\n"
            f"export function {_slug(feature)}() {{\n"
            "  // wired behind a feature flag, unit tests included\n"
            "  return { ok: true };\n}\n"
        )
        return {
            "summary": f"Implemented '{feature}' behind a feature flag and opened a PR.",
            "artifact": {"title": f"PR: {feature}", "kind": "code", "content": code},
            "followups": [
                {
                    "department": "qa",
                    "title": f"Verify {feature}",
                    "description": f"Run functional + regression tests for '{feature}'.",
                    "priority": task.priority.value,
                }
            ],
        }


class QAAgent(BaseAgent):
    department = Department.QA
    role_description = (
        "You are quality assurance. You verify builds with functional and "
        "regression tests, report results, and only sign off when quality bars "
        "are met. When a feature passes, ask Support to prep release notes."
    )

    def simulate(self, task: Task) -> dict:
        feature = task.title.replace("Verify ", "")
        report = (
            f"# QA Report: {feature}\n\n"
            "- 24 functional tests: PASS\n- 112 regression tests: PASS\n"
            "- 0 P0/P1 defects, 2 cosmetic issues filed\n\nVerdict: APPROVED for release."
        )
        return {
            "summary": f"Verified '{feature}': all suites green, approved for release.",
            "artifact": {"title": f"QA Report: {feature}", "kind": "report", "content": report},
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

    def simulate(self, task: Task) -> dict:
        topic = task.title
        campaign = (
            f"# Launch Campaign: {topic}\n\n"
            "- Hero message: 'Do more, faster.'\n"
            "- Channels: blog, email, social, in-product\n"
            "- CTA: Start free trial\n- KPI: signups, activation rate"
        )
        return {
            "summary": f"Built the launch campaign for '{topic}' and briefed Sales.",
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

    def simulate(self, task: Task) -> dict:
        topic = task.title.replace("Outreach plan for ", "")
        plan = (
            f"# Sales Plan: {topic}\n\n"
            "- Target: existing accounts + inbound trials\n"
            "- Sequence: 3-touch email + 1 call\n- Goal: 20 qualified opps in 30 days"
        )
        return {
            "summary": f"Drafted the outreach plan for '{topic}' and loaded sequences.",
            "artifact": {"title": f"Sales Plan: {topic}", "kind": "plan", "content": plan},
            "followups": [],
        }


class SupportAgent(BaseAgent):
    department = Department.SUPPORT
    role_description = (
        "You are customer support. You resolve customer issues with empathy and "
        "accuracy, write help content, and escalate genuine product gaps to "
        "Product Management."
    )

    def simulate(self, task: Task) -> dict:
        text = f"{task.title} {task.description}".lower()
        is_issue = any(w in text for w in ("bug", "broken", "error", "issue", "complaint"))
        if is_issue:
            reply = (
                f"Reply to customer re: {task.title}\n\n"
                "Thanks for flagging this — I've reproduced it and a fix is in progress. "
                "I'll follow up the moment it ships. Workaround included below."
            )
            return {
                "summary": f"Responded to the customer and escalated '{task.title}' to Product.",
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
            "Step-by-step guide and FAQ entries published to the help center."
        )
        return {
            "summary": f"Published help content / release notes for '{task.title}'.",
            "artifact": {"title": f"Help docs: {task.title}", "kind": "doc", "content": notes},
            "followups": [],
        }


class AnalyticsAgent(BaseAgent):
    department = Department.ANALYTICS
    role_description = (
        "You are analytics. You measure outcomes, surface insights, and recommend "
        "next moves grounded in data."
    )

    def simulate(self, task: Task) -> dict:
        report = (
            f"# Analytics: {task.title}\n\n"
            "- Weekly active users: +8.4%\n- Activation rate: 41% (+3pts)\n"
            "- Top funnel drop-off: onboarding step 2\n\n"
            "Recommendation: simplify onboarding step 2 next sprint."
        )
        return {
            "summary": f"Analyzed '{task.title}' and recommended the next move.",
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
