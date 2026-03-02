# Risk of Rain 2 Item Tools

This repository contains utilities for exporting item data from the Risk of Rain 2 wiki, generating random item pools, and **optimizing builds** using iterative local search algorithms.

## 🌐 Web Interface (Recommended)

The easiest way to use the optimizer is through the **drag-and-drop web interface**:

```powershell
# Start the web server
python app.py

# Open http://localhost:5000 in your browser
```

**Features:**
- 🎯 Drag-and-drop item management
- 📊 Real-time optimization with live score updates
- 📈 Interactive history charts
- 🎨 Visual rarity-based filters
- ⚡ WebSocket-powered progress tracking

## Structure

- `ror2tools/` – package containing core logic
  - `utils.py` – MediaWiki API helpers, thumbnail handling, and path constants
  - `exporter.py` – item export functionality
  - `generator.py` – random pool generation
  - **`optimizer.py`** – local search optimization engine
  - **`scoring.py`** – pool scoring functions
  - **`interactive.py`** – interactive CLI for optimization
  - **`history.py`** – optimization history tracking and visualization
- **`app.py`** – Flask web application with drag-and-drop interface
- `templates/` – HTML templates for web interface
- `static/` – CSS and JavaScript for web interface
- `export_items.py` – simple CLI wrapper that calls `ror2tools.export_items`
- `random_items.py` – simple CLI wrapper that calls `ror2tools.generate_pool`
- `data/` – persistent data store
  - `config.json` – configuration for pool generation and optimization
  - `items.csv` – exported item dataset
- `cache/` – thumbnail cache (`thumbnail_cache.json`)
- `output/` – generated outputs (`generated_pool.csv`, `generated_pool.md`, `optimization_history.json`, `optimization_history.png`)

## CLI Commands

Run within the project root (ensure the virtual environment is activated).

**Unified CLI**
```powershell
# export the item database
python main.py export

# generate a random pool (legacy/simple mode, reads only rarity config)
python main.py generate

# build a pool with advanced scoring options (prints a pool score)
python main.py build --size 5 --style frenzy --synergy-weight 2.0

# optimize a pool using local search (batch mode)
python main.py optimize --max-iterations 100 --k-opt 1

# optimize with interactive mode (pause after each iteration)
python main.py optimize --interactive --max-iterations 100

# optimize and generate visualization
python main.py optimize --visualize --max-iterations 50 --synergy-weight 2.0

# show description and wiki tips for a given item
python main.py describe "Crowbar"
```

### Optimization Features

The `optimize` command implements **iterative local search** to find better item combinations:

- **K-opt swaps**: Systematically explores item swaps while preserving rarity constraints
- **Greedy best-first**: Selects the best improvement at each iteration
- **Convergence detection**: Stops when no improvements found for N iterations
- **Simulated annealing**: Optional probabilistic acceptance of worse solutions to escape local optima
- **Tabu list**: Tracks visited pool states to prevent cycling (especially important with low synergy weights)
- **Interactive mode**: Pause after each iteration to observe progress and manually intervene
- **Manual editing**: In interactive mode, manually swap items between iterations
- **History tracking**: Records all changes and exports detailed JSON logs
- **Visualization**: Generates plots showing score progression over time

**Optimization flags:**
- `--max-iterations N`: Maximum optimization iterations (default: 100)
- `--k-opt K`: Number of items to swap simultaneously (1 or 2, default: 1)
- `--convergence N`: Stop after N iterations without improvement (default: 10)
- `--interactive`: Enable interactive mode with manual control
- `--visualize`: Generate optimization progress plot
- `--seed N`: Random seed for reproducibility

**Interactive mode commands:**
- `c` / `continue`: Run next iteration
- `r N` / `run N`: Run N iterations without pausing
- `s X → Y` / `swap X → Y`: Manually swap item X with item Y
- `v` / `view`: Show detailed scoring breakdown
- `p` / `pool`: Show current pool again
- `b` / `best`: Show best pool found so far
- `e` / `export`: Save current pool
- `q` / `quit`: Stop optimization

### Python API

You may also import the package directly in your own scripts:

```python
from ror2tools import export_items, generate_pool
from ror2tools.optimizer import LocalSearchOptimizer
from ror2tools.generator import load_items, load_config

# Export or generate
export_items()
generate_pool()

# Optimize programmatically
items = load_items()
config = load_config()
optimizer = LocalSearchOptimizer(items, config, k_opt=1, max_iterations=50)
best_pool, state = optimizer.optimize()
print(f"Optimized score: {state.best_score}")
```

## Configuration Keys

The pool generator and optimizer read `data/config.json` and support the following keys:

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
- **pinned_items** – optional list of item names that should remain fixed
  in the pool.  The optimizer will never remove these items, and swaps are
  biased to maximize synergy with them.
- **pin_synergy_bonus** – additional score bonus per synergy edge involving
  a pinned item.  This makes the fixed item the focal point of each
  replacement; set higher values to force the optimizer to treat pinned
  connections as much more important than ordinary pairwise synergy.
- **graph_max_ratio** – (optional) upper threshold for tag frequency when
  building the internal synergy graph.  Tags present in more than this
  fraction of the item pool are ignored.  Default 0.25.  For very small
  item sets (where the computed threshold would be less than one item) the
  ratio filtering is skipped to avoid eliminating every tag.
- **graph_ignore_tags** – (optional) list of specific tag strings to omit
  from the graph regardless of frequency.  Defaults to
  `["utility","damage","healing"]`.
- **optimization** – (optional) nested object with optimization parameters:
  - `max_iterations` – maximum optimization iterations (default: 100)
  - `k_opt` – number of items to swap simultaneously, 1 or 2 (default: 1)
  - `cross_rarity` – allow cross-rarity k-opt swaps, e.g. swap 1 red + 1 green ↔ 1 green + 1 red. Only effective when `k_opt` ≥ 2. Increases search space significantly. (default: false)
  - `convergence_threshold` – stop after N stale iterations (default: 10)
  - `use_simulated_annealing` – accept worse solutions probabilistically (default: false)
  - `temperature_initial` – starting temperature for annealing (default: 1.0)
  - `temperature_decay` – temperature multiplier per iteration (default: 0.95)
  - `tabu_tenure` – iterations a visited pool state stays tabu (`null` = infinite memory, strongest anti-cycling; positive int = sliding window). Prevents the optimizer from cycling back to previously seen pools. (default: null)

The generator automatically falls back to a **simple rarity-based pool** if
only the rarity counts are provided (or when using `main.py generate`). No
special flag is required; the legacy logic (`select_pool`) handles this.

### Example Configuration

**Basic optimization:**
```json
{
  "Common": 3,
  "Uncommon": 2,
  "Legendary": 1,
  "style": "frenzy",
  "synergy_weight": 2.0,
  "optimization": {
    "max_iterations": 50,
    "k_opt": 1,
    "convergence_threshold": 5
  }
}
```

**Advanced optimization with annealing:**
```json
{
  "Common": 5,
  "Uncommon": 3,
  "Legendary": 2,
  "style": "cc",
  "synergy_weight": 3.0,
  "optimization": {
    "max_iterations": 200,
    "k_opt": 2,
    "cross_rarity": true,
    "convergence_threshold": 20,
    "use_simulated_annealing": true,
    "temperature_initial": 2.0,
    "temperature_decay": 0.98
  }
}
```

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
