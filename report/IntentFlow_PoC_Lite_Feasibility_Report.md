# IntentFlow PoC-Lite Feasibility Report

**Execution date:** 2026-09-08  
**Scope:** Local controlled Python fixture  
**Status:** Executed successfully

## 1. Objective

The PoC tests the highest-risk proposal assumption: whether IntentFlow can take a code change, recover relevant structural context and approved intent, and produce an evidence-backed PR-time verdict rather than a generic review comment.

## 2. Defense PoC-Lite package

The proposal-defense PoC-Lite follows the supplied "what to show" guidance and combines:

- a clickable high-fidelity prototype of the proposed reviewer workflow;
- a saved GitHub-like event and structured intent data check;
- a runnable local structural-analysis baseline; and
- a safe/unsafe risk experiment over a controlled authorization rule.

The prototype is in `outputs/08_clickable_prototype`. It demonstrates navigation and interaction, but does not claim that every interface page has a production service behind it. The executed results in this report come only from the analyzer and saved evidence files.

## 3. PoC boundary

This is a feasibility slice, not the production architecture. It uses Python `ast` instead of Tree-sitter, a transparent in-memory adjacency graph instead of Neo4j, and a saved GitHub-like webhook payload instead of a live GitHub App. No external LLM was used. The production design still targets Tree-sitter for Python and TypeScript, Neo4j for graph topology, and GitHub Checks for delivery.

## 4. Approved intent and trace

`REQ-001` states: **Only an ADMIN can approve a pending refund.**

The controlled trace graph contains the following evidence paths:

```text
REQ-001 -> refund_service -> approve_refund -> RefundRepository.mark_approved
REQ-001 -> refund_service -> approve_refund -> test_only_admin_can_approve
```

## 5. Cases

### Unsafe PR

The base implementation checks `actor.role != "ADMIN"` and raises `PermissionError`. The unsafe PR removes this authorization guard while leaving the protected `mark_approved` call reachable.

Expected decision: `VIOLATION`, class `ACCESS_PERMISSION_DRIFT`.

### Safe control

The safe PR moves the same authorization check into `require_admin(actor)` and calls the helper before the protected operation.

Expected decision: `NO_VIOLATION`.

## 6. Structural evidence method

The analyzer parses the base and PR sources into Python abstract syntax trees. It compares function nodes to identify changed symbols. For `approve_refund`, it searches statements before the protected approval call for either:

- a direct ADMIN role condition that raises on unauthorized access; or
- a call to a local helper whose syntax tree contains that guard.

This bounded recursive check recognizes the safe helper refactor without treating the removed guard as a simple text deletion.

## 7. Deterministic verdict rule

If the base function enforced the ADMIN guard and the PR function no longer has an effective direct or helper guard before the protected call, the PoC returns `VIOLATION`. If the guard remains reachable, it returns `NO_VIOLATION`.

## 8. Actual execution results

The analyzer and three unit tests ran successfully on 2026-09-08.

| Case | Changed symbol | Base guard | PR guard | Verdict | Total local decision time |
|---|---|---:|---:|---|---:|
| Unsafe guard removal | `approve_refund` | Present | Absent | `VIOLATION` | 1.128200 ms |
| Safe helper refactor | `approve_refund` | Present | Present through `require_admin` | `NO_VIOLATION` | 0.641300 ms |

All three tests passed:

1. unsafe guard removal produces the expected violation and drift class;
2. safe helper refactor preserves the authorization evidence;
3. graph traversal reaches both the protected call and linked test.

These timings are observed local feasibility measurements for tiny fixtures. They do not represent production p95 latency, final accuracy or Neo4j performance.

## 9. GitHub-like evidence output

The PoC generates a Check Runs style JSON payload. The unsafe payload has `conclusion: failure` and a line annotation that cites `REQ-001`, the changed file, the protected call line and the access-permission drift explanation. The safe payload has `conclusion: success`. Both payloads contain an explicit notice that they were generated locally and were not published to GitHub.

## 10. Evidence files

- `evidence/before_after_unsafe.diff`
- `evidence/before_after_safe.diff`
- `evidence/unsafe_verdict.json`
- `evidence/safe_verdict.json`
- `evidence/github_check_unsafe.json`
- `evidence/github_check_safe.json`
- `evidence/trace_graph.json`
- `evidence/timings.json`
- `evidence/command_output.txt`
- `evidence/poc_result_summary.png`

## 11. What the PoC supports

The execution demonstrates that a small structural analyzer can identify a changed function, distinguish a removed guard from a helper-based refactor, retrieve a requirement-to-code-to-test trace, and generate evidence suitable for a PR check payload.

The result supports the architecture decision to keep deterministic program evidence as the ground truth supplied to later semantic reasoning.

## 12. What the PoC does not support

The run does not establish production accuracy, TypeScript coverage, Tree-sitter behavior, Neo4j performance, large-repository scalability, live GitHub installation, LLM semantic performance, merge-collision accuracy or predictive test-ranking performance.

## 13. Reproduction

From `outputs/07_poc_lite` run:

```powershell
./run_demo.ps1
```

Or run the portable commands documented in `README.md`. The implementation uses only the Python standard library.

To run the complementary clickable interface:

```powershell
../08_clickable_prototype/run_prototype.ps1
```
