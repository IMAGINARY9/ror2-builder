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
- Feel free to extend the package with new modules in `ror2tools/`.
