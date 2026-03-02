# Copilot Instructions — Risk of Rain 2 Item Tools

## Project Overview

A Python toolkit for Risk of Rain 2 item management: wiki data export, random pool generation, build optimization via local search, and a real-time web interface. See [README.md](../README.md) for full user-facing documentation.

---

## Environment Setup

- The workspace uses a Python virtual environment under `.venv`.
- **Always activate the venv before running any Python command or tests.**
  - On Windows PowerShell: `& .venv\Scripts\Activate.ps1`
  - On Unix/macOS: `source .venv/bin/activate`
- Once activated, install dependencies with `pip install -r requirements.txt`.
- All guidance and tests assume the correct interpreter is selected and the venv is active.


---

## Documentation Hygiene Rules

### Single Source of Truth Principle

Every piece of information **must live in exactly one authoritative document**. All other documents that reference the same topic must **link to the authoritative source** rather than duplicating content. When updating any fact, update it **only in the authoritative document** — never copy-paste the same information into multiple files.

### Authoritative Sources Table

| Topic | Authoritative Document | What It Covers |
|---|---|---|
| Project overview, getting started, CLI commands, configuration reference, output format, Python API | [README.md](../README.md) | Single entry point for users and developers |
| Future roadmap & pending tasks | [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) | What remains to be built; checked/unchecked task lists |
| Optimization algorithm design rationale & architecture decisions | [OPTIMIZATION_PLAN.md](../OPTIMIZATION_PLAN.md) | Why specific algorithms/data structures were chosen |
| Completed work changelog & implementation notes | [IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md) | Historical record of what was built and key decisions |
| Web interface usage | [WEB_INTERFACE_GUIDE.md](../WEB_INTERFACE_GUIDE.md) | Browser-based UI: setup, features, API endpoints, WebSocket events |
| Copilot/agent development rules | [.github/copilot-instructions.md](copilot-instructions.md) (this file) | How to develop, document, and maintain this project |
| Runtime configuration | [data/config.json](../data/config.json) | Rarity counts, scoring weights, optimization parameters |
| Synergy data | [data/synergy.json](../data/synergy.json) | Item-to-item synergy graph (auto-generated) |

### Documentation Update Protocol

1. **Before adding content** — check the table above to find the authoritative document for that topic.
2. **Never duplicate** configuration examples, CLI commands, algorithm explanations, or architecture details across multiple documents. Instead, write the content once and link to it.
3. **When modifying behaviour** — update the authoritative document and remove any stale references elsewhere.
4. **After every feature/refactor** — update [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) (mark tasks done) and [IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md) (record what changed).

---

## Code Quality Requirements

### Proactive Improvement

- If potential problems in the code or architectural limitations requiring updates/changes are discovered during the course of work, **improve them proactively** to ensure stability and reliability. Do not leave known issues for later unless explicitly scoped out.
- When touching a module, opportunistically fix nearby code smells (dead code, inconsistent signatures, missing validation) — leave the code better than you found it.

### Code Standards

- **Patterns**: Use `@dataclass` for value objects and state containers. Use `typing` annotations (`List`, `Dict`, `Optional`, `Tuple`, `Set`) on all function signatures. Prefer composition over inheritance.
- **Abstraction**: The code should use optimal data structures and programming patterns. Maintain a high level of abstraction to keep the codebase clean and reusable. Extract repeated logic into well-named helper functions; avoid inline duplication.
- **Type safety**: All public functions must have complete type hints (arguments + return type). Use `Optional[T]` explicitly instead of `None` defaults without annotation.
- **Naming**: Descriptive snake_case for functions/variables, PascalCase for classes. Module-level constants in UPPER_SNAKE_CASE.
- **Docstrings**: All public classes and functions require a docstring (Google style). Include parameter descriptions for non-trivial functions.
- **Error handling**: Validate inputs at public API boundaries. Use specific exception types, not bare `except`. Web endpoints must validate request body shape before processing.

### Architecture Principles

- **Loose coupling**: Modules communicate through well-defined interfaces. The optimizer receives items, config, and synergy graph as parameters — never imports and calls global loaders internally. Scoring functions are pure (no side effects).
- **Testability**: Avoid module-level side effects (directory creation, file I/O at import time). Use dependency injection — pass data as arguments rather than reading globals. All core logic must be unit-testable without network, filesystem, or UI.
- **Separation of concerns**: Maintain clear boundaries between layers:
  - `scoring.py` — pure scoring math (no I/O)
  - `optimizer.py` — search algorithm logic (receives data, returns results)
  - `generator.py` — pool generation and data loading
  - `interactive.py` — CLI presentation layer
  - `history.py` — tracking / persistence
  - `app.py` — web layer (Flask routes, SocketIO events)
  - `utils.py` — wiki API, caching, synergy graph construction
- **Thread safety**: Any mutable shared state in `app.py` (pool, config, DLC flags) must be protected by locks. Background optimization threads must check a cancellation flag.

---

## Development Requirements

### General Workflow

1. **Understand before changing** — read the relevant module(s) and their tests before modifying code.
2. **Incremental changes** — make small, verifiable changes. Run tests after each logical change.
3. **Test coverage** — every new public function needs at least one unit test. Bug fixes must include a regression test.
4. **No dead code** — remove unused imports, duplicate returns, and commented-out blocks.
5. **Consistent call signatures** — when a function signature changes, update all callers. Use grep/search to verify.

### Known Issues to Address Opportunistically

These are existing technical debt items. Fix them when working in the relevant area:

- Duplicated export/Markdown-writing logic inside `generator.py` (`generate_pool()` vs `export_pool_files()` and duplicate `color_text` helper).
- Module-level side effects in `utils.py` (directory creation and cache loading at import time) — should be lazy or explicit.
- Global mutable state in `app.py` (`current_config`) mutated without locking.
- `optimizer.py` has a dead duplicate `return pool` statement.
- Scoring call sites in `generator.py` use the old 4-arg signature, missing newer weight parameters.
- Hardcoded item name lists in `utils.py` playstyle boost logic — fragile if items change.
- No input validation on web API POST endpoints.
- `stop_optimization` SocketIO handler doesn't actually cancel the background worker.

### Testing

- Framework: **pytest**. Run with `pytest` from the project root.
- Use inline helper factories (e.g., `make_item()`) for test data.
- Use `monkeypatch` for patching I/O and external calls.
- Isolate score components by zeroing other weights (`*_weight=0`).
- Tests live in `tests/`. Add `conftest.py` fixtures when shared across multiple test files.

### Tech Stack Reference

| Layer | Technology |
|---|---|
| Language | Python 3.7+ |
| Web framework | Flask + Flask-SocketIO + Eventlet |
| Data scraping | Requests + BeautifulSoup4 |
| Data loading | `csv.DictReader` (prefer over pandas) |
| Visualization | Matplotlib (optional) |
| Frontend | Vanilla JS + custom CSS (no framework, no build step) |
| Testing | pytest |
| Config format | JSON (`data/config.json`) |

### Project Structure

```
ror2tools/             # Core Python package
  scoring.py           # Pure scoring functions
  optimizer.py         # Local search optimization engine
  generator.py         # Pool generation, item/config loading, file export
  interactive.py       # Interactive CLI for optimization
  history.py           # Optimization history tracking & visualization
  utils.py             # Wiki API helpers, synergy graph, caching, constants
  exporter.py          # Full item export pipeline (wiki → CSV)
app.py                 # Flask web application (REST + WebSocket)
main.py                # CLI entry point (argparse subcommands)
data/                  # Configuration and item data
  config.json          # Runtime configuration (rarity, weights, optimization)
  items.csv            # Exported item dataset
  synergy.json         # Auto-generated synergy graph
cache/                 # Thumbnail and tips caches
output/                # Generated pools, history, plots
static/                # Web frontend assets (CSS, JS)
templates/             # Jinja2 HTML templates
tests/                 # pytest test suite
```

### Key Data Flow

1. **Export**: `main.py export` → `exporter.export_items()` → Fandom wiki API → Lua parsing → `items.csv` + `synergy.json`
2. **Load**: `generator.load_items()` reads CSV, filters by DLC/availability, parses tag lists
3. **Score**: `scoring.score_pool()` = style_match × weight + synergy × weight + diversity + coverage + balance
4. **Optimize**: `LocalSearchOptimizer.optimize()` → k-opt neighborhood (same-rarity swaps) → delta scoring → greedy/SA acceptance → converge
5. **Web**: Browser ↔ REST/SocketIO ↔ `app.py` ↔ in-memory pool state → JSON responses
