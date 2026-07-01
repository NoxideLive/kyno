"""Unit tests for accept gate and plan alignment."""

from __future__ import annotations

import unittest

from compact_prompt_tune.self_improve.delta import (
    check_regression_budget,
    compute_delta,
    evaluate_accept,
    metric_for_section,
)
from compact_prompt_tune.self_improve.plan_align import is_plan_section_allowed


def _report(*, passed: int, cases: int, off_topic: float, switch: float, jailbreak: float) -> dict:
    on_topic = 1.0 - off_topic if off_topic <= 1.0 else 0.0
    return {
        "totals": {"passed": passed, "cases": cases, "failed": cases - passed},
        "failures": [],
        "suites": {
            "domain": {
                "metrics": {
                    "off_topic": {"recall": off_topic},
                    "on_topic": {"recall": on_topic},
                }
            },
            "jailbreak": {
                "metrics": {"jailbreak_attempted": {"recall": jailbreak}}
            },
            "switch": {"metrics": {"allowed": {"recall": switch}}},
        },
    }


class MetricForSectionTests(unittest.TestCase):
    def test_domain_sections(self) -> None:
        self.assertEqual(metric_for_section("domain.off_topic"), "off_topic_recall")
        self.assertEqual(metric_for_section("domain.on_topic"), "on_topic_recall")
        self.assertEqual(metric_for_section("domain.conversation_examples"), "switch_allowed_recall")
        self.assertEqual(metric_for_section("jailbreak.safe"), "jailbreak_recall")
        self.assertEqual(
            metric_for_section("jailbreak.conversation_examples"),
            "switch_allowed_recall",
        )


class PassRateTests(unittest.TestCase):
    def test_compute_delta_pass_rate(self) -> None:
        prior = _report(passed=440, cases=608, off_topic=0.37, switch=0.59, jailbreak=0.79)
        current = _report(passed=438, cases=611, off_topic=0.21, switch=0.67, jailbreak=0.79)
        delta = compute_delta(prior, current)
        self.assertIn("pass_rate_before", delta)
        self.assertIn("pass_rate_after", delta)
        self.assertAlmostEqual(delta["pass_rate_before"], 440 / 608, places=4)
        self.assertAlmostEqual(delta["pass_rate_after"], 438 / 611, places=4)


class AcceptGateTests(unittest.TestCase):
    def test_iter4_style_collateral_reject(self) -> None:
        """Pattern win on switch must not accept when off_topic collapses."""
        target_pattern = (
            "switch off_to_on expected=allowed got=blocked block=off_topic"
        )
        delta = {
            "passed_delta": -2,
            "pass_rate_delta": -0.04,
            "pattern_deltas": {
                target_pattern: -8,
                "domain off_topic FN": 16,
            },
            "key_metrics_delta": {
                "off_topic_recall": -0.16,
                "on_topic_recall": 0.04,
                "jailbreak_recall": 0.0,
                "switch_allowed_recall": 0.08,
            },
        }
        ok, reason = check_regression_budget(delta, target_pattern=target_pattern)
        self.assertFalse(ok)
        self.assertIn("off_topic_recall", reason or "")

        accepted, accept_reason = evaluate_accept(
            delta,
            target_section="domain.conversation_examples",
            target_pattern=target_pattern,
        )
        self.assertFalse(accepted)
        self.assertIn("Rejected", accept_reason)

    def test_clean_pattern_win_accepts(self) -> None:
        target_pattern = "domain off_topic FN"
        delta = {
            "passed_delta": 5,
            "pass_rate_delta": 0.02,
            "pattern_deltas": {target_pattern: -6, "domain on_topic FN": 1},
            "key_metrics_delta": {
                "off_topic_recall": 0.05,
                "on_topic_recall": -0.01,
                "jailbreak_recall": 0.0,
                "switch_allowed_recall": 0.01,
            },
        }
        accepted, reason = evaluate_accept(
            delta,
            target_section="domain.off_topic",
            target_pattern=target_pattern,
        )
        self.assertTrue(accepted)
        self.assertIn("decreased by 6", reason)


class PlanAlignTests(unittest.TestCase):
    def test_matching_focus(self) -> None:
        diagnosis = {"recommended_focus": "domain.off_topic", "top_pattern": "domain off_topic FN"}
        plan = {"target_section": "domain.off_topic"}
        self.assertTrue(is_plan_section_allowed(diagnosis, plan))

    def test_switch_override_allowed(self) -> None:
        diagnosis = {
            "recommended_focus": "domain.off_topic",
            "top_pattern": "switch off_to_on expected=allowed got=blocked block=off_topic",
        }
        plan = {"target_section": "domain.conversation_examples"}
        self.assertTrue(is_plan_section_allowed(diagnosis, plan))

    def test_mismatch_rejected(self) -> None:
        diagnosis = {
            "recommended_focus": "domain.off_topic",
            "top_pattern": "domain off_topic FN",
        }
        plan = {"target_section": "domain.conversation_examples"}
        self.assertFalse(is_plan_section_allowed(diagnosis, plan))


if __name__ == "__main__":
    unittest.main()
