# Optimization Algorithm Design Document

> **This document is the authoritative source for algorithm design rationale and architecture decisions.**
> For CLI usage and configuration, see [README.md](README.md).
> For completed work log, see [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).
> For remaining roadmap, see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Executive Summary

The pool generator uses an **adaptive local search with k-opt moves** to find optimal item builds while respecting rarity constraints. An interactive CLI and a real-time web interface allow observation and manual adjustment between iterations.

---

## 1. Algorithm Design

### 1.1 Why Local Search + K-Opt?

- Iteratively improves a solution by making small, constraint-preserving changes
- K-opt allows swapping k items at once (1-opt = single swap, 2-opt = pair swap)
- Well-suited for constrained optimization (rarity counts must be preserved)
- Easy to extend (simulated annealing, tabu list, etc.)
- Fast convergence for typical pool sizes (10–20 items)

### 1.2 Algorithm Stages

```
STAGE 1: INITIALIZATION
├─ Generate initial random pool (respecting rarity constraints)
└─ Compute initial score

STAGE 2: LOCAL SEARCH ITERATION
For each iteration (until convergence or max_iterations):
  ├─ Generate neighborhood (candidate k-opt swaps, same-rarity only)
  ├─ Evaluate score delta for each swap (fast O(k×n) computation)
  ├─ Select best improvement (greedy) or accept with probability (annealing)
  ├─ Apply swap, update best-ever if improved
  └─ Check convergence (stale counter ≥ threshold → stop)

STAGE 3: OPTIONAL PERTURBATION
├─ Random restart to escape local optima
└─ Keep best-ever solution

STAGE 4: RETURN OPTIMAL
└─ Return best pool found across all iterations
```

### 1.3 Rarity Constraint Preservation

**Critical invariant:** every swap must maintain exact rarity counts.

- Partition items by rarity: `{Common: [...], Uncommon: [...], ...}`
- Generate swaps only within the same rarity class
- Atomic swap ensures counts are never violated

### 1.4 Score Delta Computation

Instead of recomputing the full O(n²) score, delta scoring evaluates only the edges touching swapped items:

1. Style match delta: +1 if new item matches style, −1 if removed item did
2. Synergy delta: add/remove pairwise edges between swapped items and remaining pool
3. Diversity/coverage/balance deltas computed similarly

Complexity: **O(k × n)** per candidate swap vs O(n²) full recomputation.

---

## 2. Architecture

### 2.1 Module Responsibilities

```
ror2tools/
├── scoring.py      # Pure scoring functions (no I/O, no side effects)
├── optimizer.py     # LocalSearchOptimizer — k-opt search, SA, convergence
├── generator.py     # Pool generation, item/config loading, file export
├── interactive.py   # CLI presentation layer (commands, display)
├── history.py       # Iteration log, JSON export, matplotlib plots
├── utils.py         # Wiki API, synergy graph construction, caching
└── exporter.py      # Wiki → CSV export pipeline
```

### 2.2 Key Data Structures

```python
@dataclass
class Swap:
    remove: Tuple[Dict, ...]    # Items to remove from pool
    add: Tuple[Dict, ...]       # Items to add (same rarity)

@dataclass
class OptimizationState:
    pool: List[Dict]            # Current pool
    score: float                # Current score
    best_pool: List[Dict]       # Best pool found so far
    best_score: float           # Best score found so far
    iteration: int              # Current iteration
    stale_count: int            # Iterations without improvement

@dataclass
class HistoryEntry:
    iteration: int
    score: float
    swap: Optional[Tuple[str, str]]  # (removed_item_name, added_item_name)
    manual: bool                     # User intervention?
```

---

## 3. Performance Characteristics

### Neighborhood Size
- **1-opt:** O(n × m) where n = pool size, m = available items per rarity
- **2-opt:** O(n² × m²) — used for thorough search only

### Typical Results (10-item pool)
- Initial random score: ~5–10
- Optimized score: ~15–25 (2–3× improvement)
- Convergence: 20–50 iterations
- Time: < 5 s (1-opt), < 30 s (2-opt)

### Possible Future Optimizations
- Parallel neighborhood evaluation (multiprocessing)
- Swap memoization / caching
- Adaptive k-opt (start k=1, increase when stuck)

---

## 5. Tabu List (Implemented)

The optimizer tracks every visited pool state (as a `frozenset` of item names).
Before accepting a swap the resulting fingerprint is checked against the tabu
list.  If the state was visited within the last `tabu_tenure` iterations (or
ever, when `tabu_tenure` is `null` / infinite) the swap is **rejected** — unless
the **aspiration criterion** is met (the swap would produce a new global-best
score).

### Why pool-fingerprint tracking?

- Directly prevents **all** forms of cycling (2-step ping-pong, longer loops)
- O(n) per fingerprint computation; O(1) lookup in a hash set
- Memory is bounded by the number of iterations (tiny for typical runs)

### Configuration

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `tabu_tenure` | `int \| null` | `null` | Iterations a state stays tabu. `null` = infinite memory (strongest). |

---

## 6. Future Algorithm Enhancements

These enhancements are out of scope for the current implementation but are viable extensions:

- **Adaptive k-opt**: Start with k=1, increase when stuck
- **Parallel evaluation**: Multiprocessing for large neighborhoods
- **Genetic algorithms**: Population-based search with crossover and mutation
- **Multi-objective optimization**: Balance synergy vs diversity as separate objectives
- **Machine learning**: Learn synergy weights from user preferences
