# IntentFlow PoC-Lite

**IntentFlow** is an AI-assisted software integrity and delivery system. This
repository contains the runnable PoC-Lite used for the proposal defense.

The PoC tests one technical question: can a code change be connected to an
approved requirement and structural evidence before producing a Pull Request
verdict?

This is a small feasibility demonstration, not the complete IntentFlow system.

## Demonstrated pipeline

`REQ-001 -> refund_service -> approve_refund -> structural guard evidence -> deterministic verdict -> GitHub-like check payload`

Two controlled cases run:

- `unsafe_pr`: removes the ADMIN authorization guard and must return `VIOLATION` with class `ACCESS_PERMISSION_DRIFT`.
- `safe_pr`: moves authorization into `require_admin(actor)` and must return `NO_VIOLATION`.

## Run

From PowerShell:

```powershell
./run_demo.ps1
```

Portable direct command:

```text
python src/analyzer.py --output evidence
python -m unittest discover -s tests -p test_*.py -v
```

The implementation uses only the Python standard library.

## Honest fallback disclosure

- Python `ast` replaces Tree-sitter for this PoC because Tree-sitter was unavailable in the bundled runtime. The production design remains Tree-sitter for Python and TypeScript.
- A transparent in-memory adjacency graph replaces Neo4j. The PoC validates trace traversal, not Neo4j performance.
- A saved GitHub-like webhook fixture and generated check payload replace a live GitHub App because credentials were not supplied.
- No external LLM runs. The decision uses deterministic structural evidence.
- Prototype pages for merge collisions and predictive test selection are clearly labelled interface demonstrations; no unexecuted result from those pages is treated as evidence.

## Evidence

Running the command writes actual diffs, JSON verdicts, check payloads, trace data, timings, console output and an HTML summary to `evidence/`. The measured milliseconds are local feasibility timings only and must not be presented as production latency or benchmark accuracy.

## Repository layout

- `src/`: analyzer implementation
- `fixtures/`: requirement, webhook and safe/unsafe code fixtures
- `tests/`: automated tests for verdicts and trace traversal
- `evidence/`: generated diffs, verdicts, timings and GitHub-like check payloads
- `report/`: feasibility report

## Scope boundary

The planned production system will use Tree-sitter, Neo4j and a live GitHub App.
This repository proves only the smaller structural-analysis and evidence path
described above.
