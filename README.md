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

# generate a random pool
python main.py generate
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

> **Tip:** you may wish to add `data/`, `cache/`, and `output/` to `.gitignore` if you don't want generated data tracked.
- Thumbnail fetching is cached and performed in bulk/parallel for speed.
- Feel free to extend the package with new modules in `ror2tools/`.
