# Risk of Rain 2 Item Tools

This repository contains utilities for exporting item data from the Risk of Rain 2 wiki and generating random item pools.

## Structure

- `ror2tools/` – package containing core logic
  - `utils.py` – MediaWiki API helpers, thumbnail handling, and path constants
  - `exporter.py` – item export functionality
  - `generator.py` – random pool generation
- `export_items.py` – simple CLI wrapper that calls `ror2tools.export_items`
- `random_items.py` – simple CLI wrapper that calls `ror2tools.generate_pool`
- `data/` – persistent data store
  - `config.json` – configuration for pool generation
  - `items.csv` – exported item dataset
- `cache/` – thumbnail cache (`thumbnail_cache.json`)
- `output/` – generated outputs (`generated_pool.csv`, `generated_pool.md`)

## Available Commands

Run within the project root (ensure the virtual environment is activated). There are two options:

**Unified CLI (preferred)**
```powershell
# export the item database
python main.py export

# generate a random pool (legacy/simple mode, reads only rarity config)
python main.py generate

# build a pool with advanced scoring options (prints a pool score)
python main.py build --size 5 --style frenzy --synergy-weight 2.0

# show description and wiki tips for a given item
python main.py describe "Crowbar"
```

### Python API

You may also import the package directly in your own scripts:

```python
from ror2tools import export_items, generate_pool

# programmatically export or generate
export_items()
generate_pool()
```

## Configuration Keys

The pool generator reads `data/config.json` and supports the following keys:

- **rarity counts** (`Common`, `Uncommon`, `Legendary`, `Boss`, `Lunar`,
  `Void`, `Equipment`).  Numeric values indicate how many items of each
  rarity to include.  Omit a rarity or set to `0` to exclude it.
- **require_tags** – list of synergy tags; at least one item in the generated
  pool must contain one of these tags.  Tags are derived from item
  descriptions/categories/stats (e.g. `crowd-control`, `healing`).
- **require_playstyles** – list of playstyle keywords (`frenzy`, `cc`,
  `mobile`) computed from synergy tags.  Works like `require_tags` but at the
  playstyle level.
- **style** – when using the advanced `build` command, a preferred playstyle
  to bias selection (items matching the style add to the score).
- **size** – explicit number of items to draw.  If omitted, the sum of
  rarity counts is used.
- **synergy_weight** – floating multiplier applied to the graph-based
  synergy score when using `build`; higher values favor items with more
  shared tags.
- **graph_max_ratio** – (optional) upper threshold for tag frequency when
  building the internal synergy graph.  Tags present in more than this
  fraction of the item pool are ignored.  Default 0.25.  For very small
  item sets (where the computed threshold would be less than one item) the
  ratio filtering is skipped to avoid eliminating every tag.
- **graph_ignore_tags** – (optional) list of specific tag strings to omit
  from the graph regardless of frequency.  Defaults to
  `["utility","damage","healing"]`.

The generator automatically falls back to a **simple rarity-based pool** if
only the rarity counts are provided (or when using `main.py generate`). No
special flag is required; the legacy logic (`select_pool`) handles this.

## Output Columns

Generated CSV/Markdown pools include the following columns:

- **Name, Rarity** – item name and rarity.
- **Tags** – raw synergy tags assigned to each item.  Playstyles (such as
  `frenzy`, `cc` or `mobile`) are appended inside parentheses; e.g.
  ``crowd-control,damage (`cc`)``.  Each tag is wrapped in backticks in the
  Markdown output for readability.
- **Image** – thumbnail URL pulled from the wiki.

> **Note:** the previous "Aspects" column overlapped heavily with Tags and
> has been removed – everything useful that used to appear there is still
> encoded in the tags themselves.
(See the notes section below for more on thumbnail caching and performance.)

## Notes

- `data/items.csv` now includes an `Available` column; the pool generator ignores rows marked `false`.
- In addition to the original fields the exporter writes `SynergyTags`, `Playstyles`, and `WikiTips` columns for each item.  These are used by the generator to classify builds and allow tag-based filtering.
- The pool generator now understands two optional configuration keys in `data/config.json`:
  - `require_tags`: a list of synergy tags to include (at least one must appear in the pool)
  - `require_playstyles`: a list of playstyles to include
  You can mix these with the existing rarity counts.  For example:

```json
{
    "Common": 3,
    "Uncommon": 2,
    "Legendary": 1,
    "require_tags": ["on-kill","crit"]
}
```

Advanced pool-building parameters can also be placed in the same file and are used by the `build` command. For example:

```json
{
    "size": 5,
    "style": "frenzy",
    "synergy_weight": 2.0
}
```

When these keys are absent, the generator defaults back to the simple rarity-based behaviour.

- A basic test suite using `pytest` is available under `tests/`.  To run the tests, install pytest in your environment (`pip install pytest`) and execute `pytest` from the project root.

> **Tip:** you may wish to add `data/`, `cache/`, and `output/` to `.gitignore` if you don't want generated data tracked.
- Thumbnail fetching is cached and performed in bulk/parallel for speed.
- The exporter now processes items in a thread pool (8 workers) and caches
  wiki tips in `cache/tips_cache.json` to avoid repeated network requests.
- Feel free to extend the package with new modules in `ror2tools/`.
