from __future__ import annotations

import argparse
import ast
import difflib
import html
import json
import time
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def parse_module(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path))


def function_map(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def call_name(call: ast.Call) -> str:
    node: ast.AST = call.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def contains_admin_role_check(node: ast.AST) -> bool:
    names = {
        child.id.lower()
        for child in ast.walk(node)
        if isinstance(child, ast.Name)
    }
    attrs = {
        child.attr.lower()
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
    }
    constants = {
        str(child.value).upper()
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
    }
    return "ADMIN" in constants and ("role" in attrs or "role" in names)


def function_enforces_admin(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    visited: set[str] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    visited = set() if visited is None else set(visited)
    if function.name in visited:
        return False, []
    visited.add(function.name)
    evidence: list[dict[str, Any]] = []

    for statement in function.body:
        if isinstance(statement, ast.If) and contains_admin_role_check(statement.test):
            blocks = list(statement.body) + list(statement.orelse)
            if any(isinstance(item, ast.Raise) for item in ast.walk(ast.Module(body=blocks))):
                evidence.append(
                    {
                        "kind": "direct_guard",
                        "function": function.name,
                        "line": statement.lineno,
                        "condition": ast.unparse(statement.test),
                    }
                )
                return True, evidence

        calls = [node for node in ast.walk(statement) if isinstance(node, ast.Call)]
        for call in calls:
            name = call_name(call).split(".")[-1]
            helper = functions.get(name)
            if helper is not None:
                enforced, helper_evidence = function_enforces_admin(helper, functions, visited)
                if enforced:
                    evidence.append(
                        {
                            "kind": "helper_call",
                            "function": function.name,
                            "helper": name,
                            "line": getattr(call, "lineno", None),
                        }
                    )
                    evidence.extend(helper_evidence)
                    return True, evidence

        if any(call_name(call).endswith("mark_approved") for call in calls):
            break

    return False, evidence


def changed_symbols(
    base_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    pr_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[str]:
    changed: list[str] = []
    for name in sorted(set(base_functions) | set(pr_functions)):
        before = base_functions.get(name)
        after = pr_functions.get(name)
        if before is None or after is None or ast.dump(before) != ast.dump(after):
            changed.append(name)
    return changed


def shortest_path(graph: dict[str, list[str]], start: str, goal: str) -> list[str]:
    queue: deque[list[str]] = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == goal:
            return path
        for neighbor in graph.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(path + [neighbor])
    return []


def make_graph() -> dict[str, list[str]]:
    return {
        "REQ-001": ["refund_service"],
        "refund_service": ["approve_refund"],
        "approve_refund": ["RefundRepository.mark_approved", "test_only_admin_can_approve"],
        "RefundRepository.mark_approved": [],
        "test_only_admin_can_approve": [],
    }


def build_check_result(result: dict[str, Any], head_sha: str) -> dict[str, Any]:
    unsafe = result["verdict"] == "VIOLATION"
    output: dict[str, Any] = {
        "name": "IntentFlow Product Intent Verification (local PoC fixture)",
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "failure" if unsafe else "success",
        "output": {
            "title": result["verdict"],
            "summary": result["explanation"],
            "text": "Trace: " + " -> ".join(result["trace_to_protected_call"]),
        },
        "fixture_notice": "Generated locally from a saved GitHub-like event. Not published to GitHub.",
    }
    if unsafe:
        output["output"]["annotations"] = [
            {
                "path": "refund_service.py",
                "start_line": result["protected_call_line"],
                "end_line": result["protected_call_line"],
                "annotation_level": "failure",
                "title": "ACCESS_PERMISSION_DRIFT",
                "message": "REQ-001 requires ADMIN authorization before refund approval, but the guard is absent on the reachable approval path.",
            }
        ]
    return output


def analyze_case(case_name: str, pr_path: Path) -> dict[str, Any]:
    total_start = time.perf_counter_ns()
    parse_start = time.perf_counter_ns()
    base_source, base_tree = parse_module(FIXTURES / "base" / "refund_service.py")
    pr_source, pr_tree = parse_module(pr_path)
    parse_ms = (time.perf_counter_ns() - parse_start) / 1_000_000

    base_functions = function_map(base_tree)
    pr_functions = function_map(pr_tree)
    base_guard, base_evidence = function_enforces_admin(base_functions["approve_refund"], base_functions)
    pr_guard, pr_evidence = function_enforces_admin(pr_functions["approve_refund"], pr_functions)

    protected_calls = [
        node
        for node in ast.walk(pr_functions["approve_refund"])
        if isinstance(node, ast.Call) and call_name(node).endswith("mark_approved")
    ]
    protected_line = protected_calls[0].lineno if protected_calls else None

    graph_start = time.perf_counter_ns()
    graph = make_graph()
    trace_to_call = shortest_path(graph, "REQ-001", "RefundRepository.mark_approved")
    trace_to_test = shortest_path(graph, "REQ-001", "test_only_admin_can_approve")
    graph_ms = (time.perf_counter_ns() - graph_start) / 1_000_000

    verdict = "VIOLATION" if base_guard and not pr_guard else "NO_VIOLATION"
    explanation = (
        "ADMIN authorization guard removed or weakened before the protected refund approval call."
        if verdict == "VIOLATION"
        else "Authorization moved or refactored, but an ADMIN condition remains reachable before approval."
    )
    total_ms = (time.perf_counter_ns() - total_start) / 1_000_000

    return {
        "case": case_name,
        "parser": "Python ast fallback",
        "graph_store": "in-memory adjacency graph fallback",
        "github_mode": "saved event and generated check payload",
        "verdict": verdict,
        "class": "ACCESS_PERMISSION_DRIFT" if verdict == "VIOLATION" else None,
        "requirement": "REQ-001",
        "changed_symbols": changed_symbols(base_functions, pr_functions),
        "changed_symbol": "approve_refund",
        "base_admin_guard": base_guard,
        "pr_admin_guard": pr_guard,
        "base_guard_evidence": base_evidence,
        "pr_guard_evidence": pr_evidence,
        "protected_call": "RefundRepository.mark_approved",
        "protected_call_line": protected_line,
        "trace_to_protected_call": trace_to_call,
        "trace_to_relevant_test": trace_to_test,
        "explanation": explanation,
        "timing_ms": {
            "parse": round(parse_ms, 6),
            "graph_retrieval": round(graph_ms, 6),
            "total_local_decision": round(total_ms, 6),
        },
        "source": pr_source,
        "base_source": base_source,
    }


def write_diff(base_source: str, pr_source: str, label: str, path: Path) -> None:
    diff = difflib.unified_diff(
        base_source.splitlines(keepends=True),
        pr_source.splitlines(keepends=True),
        fromfile="base/refund_service.py",
        tofile=f"{label}/refund_service.py",
    )
    path.write_text("".join(diff), encoding="utf-8")


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"source", "base_source"}}


def summary_html(unsafe: dict[str, Any], safe: dict[str, Any]) -> str:
    unsafe_trace = " &rarr; ".join(map(html.escape, unsafe["trace_to_protected_call"]))
    safe_trace = " &rarr; ".join(map(html.escape, safe["trace_to_relevant_test"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>IntentFlow PoC-Lite evidence</title>
<style>
body{{margin:0;background:#f4f7fb;color:#13233a;font:16px/1.45 Arial,sans-serif}}
main{{max-width:1050px;margin:40px auto;background:white;border:1px solid #dbe4f0;border-radius:16px;padding:34px 42px;box-shadow:0 12px 34px rgba(20,42,75,.08)}}
h1{{margin:0 0 4px;font-size:30px}} .sub{{color:#5b6b82;margin:0 0 26px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.case{{border:1px solid #dbe4f0;border-radius:12px;padding:22px}}
.bad{{border-top:5px solid #c43737}} .good{{border-top:5px solid #2f855a}}
.label{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#64748b}}
.verdict{{font-size:25px;font-weight:700;margin:4px 0 12px}} .bad .verdict{{color:#a61b1b}} .good .verdict{{color:#226b49}}
code{{font-family:Consolas,monospace;background:#f1f5f9;padding:2px 5px;border-radius:4px}}
.trace{{margin-top:20px;padding:16px;background:#eef4fb;border-radius:9px;font-family:Consolas,monospace;font-size:14px}}
.timing{{margin-top:16px;color:#334155}}
footer{{margin-top:22px;color:#64748b;font-size:13px}}
</style></head><body><main>
<h1>IntentFlow PoC-Lite execution evidence</h1><p class="sub">Local controlled fixture. Python AST and in-memory graph fallbacks. No live GitHub or model claim.</p>
<div class="grid">
<section class="case bad"><div class="label">Unsafe PR fixture</div><div class="verdict">{unsafe['verdict']}</div>
<p>{html.escape(unsafe['explanation'])}</p><p><b>Changed symbol:</b> <code>approve_refund</code></p>
<div class="trace">{unsafe_trace}</div><p class="timing"><b>Total local decision:</b> {unsafe['timing_ms']['total_local_decision']:.6f} ms</p></section>
<section class="case good"><div class="label">Safe refactor fixture</div><div class="verdict">{safe['verdict']}</div>
<p>{html.escape(safe['explanation'])}</p><p><b>Evidence:</b> <code>require_admin(actor)</code> reaches the guard before approval.</p>
<div class="trace">{safe_trace}</div><p class="timing"><b>Total local decision:</b> {safe['timing_ms']['total_local_decision']:.6f} ms</p></section>
</div><footer>Generated from the same JSON evidence saved in this folder on 2026-09-08.</footer>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the IntentFlow PoC-Lite controlled cases.")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    event = json.loads((FIXTURES / "github_pull_request_event.json").read_text(encoding="utf-8"))
    unsafe = analyze_case("unsafe_pr", FIXTURES / "unsafe_pr" / "refund_service.py")
    safe = analyze_case("safe_pr", FIXTURES / "safe_pr" / "refund_service.py")

    unsafe_public = public_result(unsafe)
    safe_public = public_result(safe)
    (output / "unsafe_verdict.json").write_text(json.dumps(unsafe_public, indent=2), encoding="utf-8")
    (output / "safe_verdict.json").write_text(json.dumps(safe_public, indent=2), encoding="utf-8")
    (output / "trace_graph.json").write_text(json.dumps(make_graph(), indent=2), encoding="utf-8")
    (output / "timings.json").write_text(
        json.dumps({"unsafe_pr": unsafe_public["timing_ms"], "safe_pr": safe_public["timing_ms"]}, indent=2),
        encoding="utf-8",
    )
    (output / "github_check_unsafe.json").write_text(
        json.dumps(build_check_result(unsafe_public, event["pull_request"]["head"]["sha"]), indent=2),
        encoding="utf-8",
    )
    (output / "github_check_safe.json").write_text(
        json.dumps(build_check_result(safe_public, event["pull_request"]["head"]["sha"]), indent=2),
        encoding="utf-8",
    )
    write_diff(unsafe["base_source"], unsafe["source"], "unsafe_pr", output / "before_after_unsafe.diff")
    write_diff(safe["base_source"], safe["source"], "safe_pr", output / "before_after_safe.diff")

    lines = [
        "IntentFlow PoC-Lite | local controlled fixture",
        "Parser: Python ast fallback | Graph: in-memory adjacency fallback | GitHub: saved event",
        "",
        f"UNSAFE CASE: {unsafe_public['verdict']} | {unsafe_public['class']}",
        f"Changed symbol: {unsafe_public['changed_symbol']}",
        f"Evidence: {unsafe_public['explanation']}",
        "Trace: " + " -> ".join(unsafe_public["trace_to_protected_call"]),
        f"Timing: {unsafe_public['timing_ms']['total_local_decision']:.6f} ms total local decision",
        "",
        f"SAFE CASE: {safe_public['verdict']}",
        f"Evidence: {safe_public['explanation']}",
        "Trace: " + " -> ".join(safe_public["trace_to_relevant_test"]),
        f"Timing: {safe_public['timing_ms']['total_local_decision']:.6f} ms total local decision",
    ]
    console = "\n".join(lines) + "\n"
    (output / "command_output.txt").write_text(console, encoding="utf-8")
    (output / "result_summary.html").write_text(summary_html(unsafe_public, safe_public), encoding="utf-8")
    print(console, end="")
    return 0 if unsafe_public["verdict"] == "VIOLATION" and safe_public["verdict"] == "NO_VIOLATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
