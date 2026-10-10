from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzer import FIXTURES, analyze_case  # noqa: E402


class PocLiteTests(unittest.TestCase):
    def test_unsafe_guard_removal_is_a_violation(self) -> None:
        result = analyze_case("unsafe_pr", FIXTURES / "unsafe_pr" / "refund_service.py")
        self.assertEqual("VIOLATION", result["verdict"])
        self.assertEqual("ACCESS_PERMISSION_DRIFT", result["class"])
        self.assertTrue(result["base_admin_guard"])
        self.assertFalse(result["pr_admin_guard"])
        self.assertIn("approve_refund", result["changed_symbols"])

    def test_safe_helper_refactor_preserves_admin_guard(self) -> None:
        result = analyze_case("safe_pr", FIXTURES / "safe_pr" / "refund_service.py")
        self.assertEqual("NO_VIOLATION", result["verdict"])
        self.assertTrue(result["pr_admin_guard"])
        self.assertTrue(any(item["kind"] == "helper_call" for item in result["pr_guard_evidence"]))

    def test_trace_reaches_protected_call_and_test(self) -> None:
        result = analyze_case("unsafe_pr", FIXTURES / "unsafe_pr" / "refund_service.py")
        self.assertEqual("REQ-001", result["trace_to_protected_call"][0])
        self.assertEqual("RefundRepository.mark_approved", result["trace_to_protected_call"][-1])
        self.assertEqual("test_only_admin_can_approve", result["trace_to_relevant_test"][-1])


if __name__ == "__main__":
    unittest.main()
