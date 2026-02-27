# Future Implementation Plan

This document outlines a roadmap for extending the Risk of Rain 2 item tools with richer build-generation capabilities and improved data handling.  Use it as a reference for subsequent development.

## 1. Data Model Expansion

- [x] Add new fields to `data/items.csv`:
  - `SynergyTags` (comma-separated keywords e.g. `on-hit,crit,bleed`)
  - `Playstyles` (e.g. `tank,glass-cannon,crowd-control`)
  - `Character` (optional preferred survivor)  <!-- still pending -->
  - `WikiTips` (string scraped from the item page)
  - Numeric breakdown of stats (columns for damage%, cooldown%, etc.)  <!-- partially done via StatsJson -->
- [x] Update exporter to compute and write these columns.
- [ ] Provide a script (`ror2tools/augment.py`) to reprocess existing CSV and fill missing values.  <!-- future work -->

## 2. Wiki Scraping Enhancements

- [x] Implement `fetch_wiki_tips(title)` in `ror2tools/utils.py` (returns first Tips/Usage text).
- [x] Call this during export and store in `WikiTips` column.
- [ ] Optionally download and store drop source tables (categories) for reference.

## 3. Synergy Graph

- [x] Define rules for generating synergy tags from categories/stats.  (heuristics already in utils)
- [x] Construct an adjacency matrix or list mapping item→item synergy weights.
- [x] Store the graph as JSON under `data/synergy.json`.
- [x] Write utilities to score a portfolio of items using graph edges.

## 4. Build Generator Improvements

- [x] Replace `select_pool` with `build_pool` accepting parameters:
  - `style` (tank, damage, mobility, hybrid)
  - `character` (optional)
  - `size` (number of items)
  - `synergy` weight factor
- [x] Implement scoring function:
  ```python
  score(item) = base_stat_score + synergy_bonus + style_match
  ```
- [x] Add additional CLI commands to `main.py`:
  - `build --style tank --size 10` → prints enhanced build
  - `describe <item>` → outputs wiki tips and stats

> **Note:** simple generation is still available via `generate` and by omitting the advanced fields in `config.json`.

## 5. Output Formatting

There are several ways to present builds beyond plain text/CSV.  Each has
different trade‑offs:

* **Enhanced Markdown** (current approach)
  * Pros: already supported, no extra dependencies, works offline, easily
    previewable in VS Code or GitHub.
  * Cons: layout options limited (tables, images), styling is rudimentary.

* **Static HTML** (templating to `.html` files)
  * Pros: rich styling, responsive design, can embed icons/tips nicely.
  * Cons: requires a templating library (e.g. Jinja2), CSS assets, and
    users open files locally.  No server needed if files are purely static.
  * This is a lightweight alternative to a full server and avoids runtime
    dependencies besides the template engine.

* **Web server / Flask app**
  * Pros: interactive UI, query parameters, re‑generate on the fly.
  * Cons: additional dependency (Flask or similar), need to run a server,
    more code to maintain, not strictly necessary for simple file
    generation.

* **Other stacks** (e.g. React/Electron) are possible but likely overkill for
a CLI tool.

Given the existing scope and desire to keep dependencies minimal, the
next step could simply be to extend the Markdown output with better
styling and perhaps a few helper scripts to convert Markdown → HTML (via
pandoc or similar) if a richer presentation is needed.  If interactive
functionality becomes important later, a lightweight Flask server could be
added as an optional extra.

### Updated tasks

- [x] Continue using Markdown for build output; explore CSS-based styling
  or pandoc conversion for improved appearance (done, generator writes styled
  Markdown with score).  HTML conversion may be handled externally if needed.
- [ ] (Optional, low priority) add a built-in static HTML exporter using a
  templating library; not required for current scope, may be a plugin later.
- [x] Flask-based web UI with real-time optimization (see [WEB_INTERFACE_GUIDE.md](WEB_INTERFACE_GUIDE.md)).

## 6. Testing & Validation

- [x] `tests/` directory with unit tests for scoring, optimizer, generator, and utilities.
- [x] `pytest` framework in place. CI pipeline (GitHub Actions) still pending.

## 7. Documentation & CLI Help

- [x] README updated with commands and examples.
- [x] `main.py` argparse help messages are descriptive.
- [x] Changelog maintained in [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).

## 8. Optional Enhancements

- [x] Web server / Flask app to serve dynamic build generation.
- [ ] Graphical interface (Electron/React) for interactive selection.
- [ ] Integration with game API (if available) to import actual gear.

---

For completed work details, see [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).
For algorithm design rationale, see [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md).
