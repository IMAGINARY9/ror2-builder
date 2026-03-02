# Implementation Summary

> **This document is the authoritative record of completed work and key decisions.**
> For CLI usage and configuration, see [README.md](README.md).
> For algorithm design rationale, see [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md).
> For future roadmap, see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

---

## Completed Features

### Core Optimization Engine (`optimizer.py`)

- Local search algorithm with k-opt swaps (1-opt and 2-opt)
- Rarity constraint preservation (all swaps maintain exact rarity counts)
- **Cross-rarity k-opt swaps** — when `cross_rarity: true` and `k_opt >= 2`, the optimizer also explores swaps that span multiple rarities while preserving the rarity multiset (e.g. remove 1 Common + 1 Legendary, add 1 Common + 1 Legendary). Capped at 2 000 cross-rarity candidates per iteration to prevent combinatorial explosion.
- Convergence detection, simulated annealing, fast delta computation
- Random restart / perturbed pools to escape local optima
- **Tabu list** (`TabuList` class) — tracks visited pool states as frozen name-sets to prevent cycling; configurable tenure (`null` = infinite memory); aspiration criterion overrides tabu when a swap beats the global best

### Scoring System (`scoring.py`)

- Extracted from `generator.py` as a standalone pure-function module
- Multi-component weighted scoring: style match, synergy graph, rarity diversity (Shannon entropy), tag coverage, category balance
- Delta computation: O(k×n) instead of O(n²) for swap evaluation

### Interactive CLI (`interactive.py`)

- Pause-per-iteration mode with rich terminal display
- Command system: continue, run N, swap, view, best, export, quit
- Manual item swaps with rarity validation

### History Tracking (`history.py`)

- Full iteration log with JSON export
- Matplotlib visualization of score progression
- Summary statistics and manual-intervention markers

### Web Interface (`app.py`)

- Flask + Flask-SocketIO real-time drag-and-drop UI
- REST API for pool manipulation and configuration
- WebSocket-powered background optimization with live progress
- Rich saved reports with configuration parameters, score breakdown, pool statistics, and clean item descriptions

### Item Description Cleanup (`generator.py`)

- `clean_wiki_markup()` — strips RoR2 Fandom wiki template syntax (`{{Color|…}}`, `{{Stack|…}}`) from item descriptions
- Applied in both the Markdown export (reports) and the web API (`/api/items` returns `clean_desc`)
- **Bug fix (Mar 2026)**: Description field was unformatted when viewing pool cards because pool endpoints returned raw descriptions. Added `clean_desc` to every item when loading CSV and ensured all `/api/pool` routes propagate it; front‑end now displays the cleaned text consistently.

### CLI Integration (`main.py`)

- Subcommands: `export`, `generate`, `build`, `optimize`, `describe`
- `optimize` supports `--interactive`, `--visualize`, `--seed`, and more (see [README.md](README.md))

---

## Test Coverage

10 original unit tests + 10 new tabu list tests in `tests/test_optimization.py` covering:
- Scoring (basic, with synergy graph, delta, breakdown)
- Optimizer (init, rarity partitioning, pool generation, swap generation)
- TabuList (record, is_tabu, finite/infinite tenure, clear, fingerprinting)
- Tabu integration (no-revisit with SA, aspiration criterion)
- History (tracking, summary)

All tests passing. Run with `pytest` from the project root.

---

## Git History (Key Commits)

1. **feat: add pool optimization system** (e71f970) — core optimizer, scoring, history, interactive modules
2. **feat: add optimization tests and docs** (80e6984) — 10 tests, README update, import fix
3. **docs: add examples and config templates** (bad75b1) — `examples_optimization.py`

---

## Key Design Decisions

These decisions are recorded here for historical context. For the full algorithm rationale, see [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md).

| Decision | Choice | Reasoning |
|---|---|---|
| Search algorithm | Adaptive local search with k-opt | Simple, constraint-friendly, fast convergence, extensible |
| Delta scoring vs full recomputation | Delta (O(k×n)) | ~100× faster for typical pool sizes |
| Default k-opt value | k=1 | Good quality/speed trade-off; k=2 available for thorough search |
| Interactive vs batch | Both modes | Batch for automation, interactive for exploration |
| Scoring extraction | Separate `scoring.py` | Pure functions, testable, reusable across optimizer and generator |
| Web framework | Flask + SocketIO | Lightweight, real-time updates via WebSocket, no frontend build step |
