# Future Implementation Plan

This document outlines a roadmap for extending the Risk of Rain 2 item tools with richer build-generation capabilities and improved data handling.  Use it as a reference for subsequent development.

## 1. Data Model Expansion

- [ ] Add new fields to `data/items.csv`:
  - `SynergyTags` (comma-separated keywords e.g. `on-hit,crit,bleed`)
  - `Playstyles` (e.g. `tank,glass-cannon,crowd-control`)
  - `Character` (optional preferred survivor)
  - `WikiTips` (string scraped from the item page)
  - Numeric breakdown of stats (columns for damage%, cooldown%, etc.)
- [ ] Update exporter to compute and write these columns.
- [ ] Provide a script (`ror2tools/augment.py`) to reprocess existing CSV and fill missing values.

## 2. Wiki Scraping Enhancements

- [ ] Implement `fetch_wiki_tips(title)` in `ror2tools/utils.py`:
  ```python
  def fetch_wiki_tips(title):
      # query parse sections, identify 'Tips'/'Usage', return plain text
  ```
- [ ] Call this during export and store in `WikiTips` column.
- [ ] Optionally download and store drop source tables (categories) for reference.

## 3. Synergy Graph

- [ ] Define rules for generating synergy tags from categories/stats.
- [ ] Construct an adjacency matrix or list mapping item→item synergy weights.
- [ ] Store the graph as JSON under `data/synergy.json`.
- [ ] Write utilities to score a portfolio of items using graph edges.

## 4. Build Generator Improvements

- [ ] Replace `select_pool` with `build_pool` accepting parameters:
  - `style` (tank, damage, mobility, hybrid)
  - `character` (optional)
  - `size` (number of items)
  - `synergy` weight factor
- [ ] Implement scoring function:
  ```python
  score(item) = base_stat_score + synergy_bonus + style_match
  ```
- [ ] Add additional CLI commands to `main.py`:
  - `build --style tank --size 10` → prints enhanced build
  - `describe <item>` → outputs wiki tips and stats

## 5. Output Formatting

- [ ] Create HTML template for builds with icons, stats table, and tips.
- [ ] Extend generator to optionally write `output/build-<timestamp>.html`.
- [ ] Aggregate statistics (sum %) at top of output.
- [ ] Add README section showing sample generated build.

## 6. Testing & Validation

- [ ] Add `tests/` directory with unit tests for:
  - `utils.lua_parse_items_module`
  - `fetch_wiki_tips` (mock API responses)
  - `build_pool` scoring logic
- [ ] Use `pytest` and include in CI pipeline (GitHub Actions).

## 7. Documentation & CLI Help

- [ ] Update README with new commands and examples.
- [ ] Ensure `main.py` argparse help messages are descriptive.
- [ ] Maintain change log for future enhancements.

## 8. Optional Enhancements

- [ ] Web server / Flask app to serve dynamic build generation.
- [ ] Graphical interface (Electron/React) for interactive selection.
- [ ] Integration with game API (if available) to import actual gear.

---

This plan is written in markdown for easy viewing; a machine-readable form could be added later (e.g. YAML checklist for project management).  Each task should be broken into PRs and tracked in the repository.
