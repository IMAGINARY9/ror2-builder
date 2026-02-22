# Risk of Rain 2 Item Pool Optimization System - Implementation Plan

## Executive Summary

Transform the current random pool generator into an **iterative optimization system** that finds optimal item builds using local search algorithms while respecting rarity constraints. Add an **interactive CLI interface** for observing and manually adjusting builds between iterations.

---

## 1. Analysis of Current State

### Strengths
- ✅ Robust item loading system with synergy tags and playstyles
- ✅ Synergy graph computed from shared tags between items
- ✅ Scoring function that evaluates pools based on style + synergy
- ✅ Rarity-based constraints already enforced
- ✅ Clean separation: `utils.py` (data), `generator.py` (logic), `exporter.py` (wiki)
- ✅ Configuration system via JSON

### Current Limitations
- ❌ **Random sampling only** - uses `random.sample()` with multiple attempts but no systematic improvement
- ❌ **No iterative refinement** - generates pool once and stops
- ❌ **No user interaction** - batch mode only, no ability to observe/modify mid-process
- ❌ **Limited optimization** - `max_attempts` tries different random pools but doesn't improve a single pool
- ❌ **No local search** - doesn't explore neighbor solutions by swapping items
- ❌ **No tracking of optimization history** - can't visualize improvement over iterations

---

## 2. Optimization Algorithm Design

### 2.1 Core Algorithm: **Adaptive Local Search with K-Opt Moves**

**Why Local Search + K-Opt?**
- Local search iteratively improves a solution by making small changes
- K-opt allows swapping k items at once (1-opt = swap 1 item, 2-opt = swap 2 items, etc.)
- Well-suited for constrained optimization (rarity counts must be preserved)
- Easy to implement, understand, and control
- Can escape local optima with random restarts or simulated annealing

### 2.2 Algorithm Stages

```
STAGE 1: INITIALIZATION
├─ Generate initial random pool (respecting rarity constraints)
└─ Compute initial score

STAGE 2: LOCAL SEARCH ITERATION
For each iteration (until convergence or max_iterations):
  ├─ Generate neighborhood (candidate swaps)
  │   ├─ K-opt moves: try swapping k items with k unused items of same rarities
  │   ├─ Filter candidates by rarity constraints
  │   └─ Sort by score improvement (delta)
  ├─ Select best improvement (greedy) or accept with probability (annealing)
  ├─ Apply swap if improvement found
  ├─ Track iteration history (score, swaps made)
  └─ Check convergence (no improvement for N iterations)

STAGE 3: OPTIONAL PERTURBATION
├─ If stuck in local optimum, apply random restart
├─ Keep best-ever solution
└─ Continue search from perturbed state

STAGE 4: RETURN OPTIMAL
└─ Return best pool found across all iterations
```

### 2.3 Rarity Constraint Preservation

**Critical Requirement:** Swaps must maintain exact rarity counts.

**Solution:**
- Partition items by rarity: `{Common: [...], Uncommon: [...], ...}`
- Track which items are IN pool vs. AVAILABLE (not in pool)
- When swapping k items:
  - Select k items FROM pool
  - Select k items FROM available with **matching rarities**
  - Perform atomic swap

**Example:** If pool has `[Common1, Uncommon1]` and we swap `Common1`:
- Only consider Common items NOT in pool
- Swap preserves counts: still 1 Common, 1 Uncommon

---

## 3. Interactive Interface Design

### 3.1 CLI Modes

```
python main.py optimize [--config CONFIG] [--interactive] [--max-iterations N]
                        [--k-opt K] [--temperature T] [--visualize]
```

**Modes:**
1. **Batch mode** (`--interactive=false`, default): Run optimization to completion, show final result
2. **Interactive mode** (`--interactive=true`): Pause after each iteration, show state, allow user input
3. **Visualize mode** (`--visualize`): Generate score plot after completion

### 3.2 Interactive Commands (per iteration)

```
┌──────────────────────────────────────────────────────────┐
│ Iteration 15/100 │ Score: 42.5 → 48.3 (+5.8)            │
│ Convergence: 3 stale iterations                          │
└──────────────────────────────────────────────────────────┘

Current Pool:
  [C] Crowbar          (on-kill, damage)
  [U] Berzerker's P.   (on-kill, cooldown)
  [L] 57 Leaf Clover   (crit, luck)
  ...

Last Swap: Replaced [C] "Lens-Maker's" → "Crowbar" (+3.2)

Commands:
  [c]ontinue      - Run next iteration
  [r]un N         - Run N iterations without pausing
  [s]wap X → Y    - Manually swap item X with item Y
  [a]dd X         - Add item X (if rarity budget allows)
  [d]elete X      - Remove item X from pool
  [v]iew stats    - Show detailed scoring breakdown
  [e]xport        - Save current pool
  [q]uit          - Stop optimization, keep current best
  [reset]         - Restart from scratch

> _
```

### 3.3 Visualization Output

Generate `output/optimization_history.png`:
- X-axis: Iteration number
- Y-axis: Pool score
- Annotations: Mark manual interventions, restarts, best-ever point

---

## 4. Implementation Architecture

### 4.1 New Modules

```
ror2tools/
├── optimizer.py         # Local search engine, swap generation, convergence detection
├── interactive.py       # CLI interface, user command handling, display formatting
├── scoring.py           # Extract scoring logic from generator.py (refactor)
└── history.py           # Track optimization history, export stats/plots
```

### 4.2 Refactoring Needs

**generator.py:**
- Extract `score_pool()` → `scoring.py`
- Keep `build_pool()` for legacy random generation
- Add `optimize_pool()` function that delegates to `optimizer.py`

**main.py:**
- Add `optimize` subcommand
- Parse new flags: `--interactive`, `--k-opt`, `--max-iterations`, etc.

**config.json:**
- Add optimization parameters:
  ```json
  {
    "optimization": {
      "max_iterations": 100,
      "k_opt": 2,
      "convergence_threshold": 10,
      "temperature_initial": 1.0,
      "temperature_decay": 0.95,
      "use_simulated_annealing": false
    }
  }
  ```

### 4.3 Data Structures

**Pool State:**
```python
@dataclass
class PoolState:
    items: List[Dict]           # Current pool items
    score: float                # Current score
    rarity_counts: Dict[str, int]  # {rarity: count}
    iteration: int              # Current iteration number
    history: List[HistoryEntry] # Past states
```

**History Entry:**
```python
@dataclass
class HistoryEntry:
    iteration: int
    score: float
    swap: Optional[Tuple[str, str]]  # (removed_item, added_item)
    manual: bool                # Was this a user intervention?
```

**Neighborhood:**
```python
class Neighborhood:
    def generate_swaps(self, pool, available_items, k=1):
        """Generate all k-opt swaps respecting rarity constraints."""
        
    def score_swap(self, pool, swap_candidate):
        """Evaluate score delta for a candidate swap."""
```

---

## 5. Implementation Phases

### **PHASE 1: Core Optimizer (No Interaction)**
**Goal:** Implement local search algorithm in batch mode
- [ ] Create `optimizer.py` with `LocalSearchOptimizer` class
- [ ] Implement k-opt swap generation with rarity constraints
- [ ] Implement greedy best-first improvement selection
- [ ] Add convergence detection (N iterations without improvement)
- [ ] Refactor `score_pool()` into `scoring.py`
- [ ] Add `optimize` subcommand to `main.py`
- [ ] Write tests for swap generation and scoring
- [ ] **Commit:** "feat: add local search optimizer (batch mode)"

### **PHASE 2: Optimization History & Stats**
**Goal:** Track and export optimization progress
- [ ] Create `history.py` with `OptimizationHistory` class
- [ ] Track score per iteration, swap details, manual flags
- [ ] Export history to JSON (`output/optimization_history.json`)
- [ ] Add `--export-history` flag
- [ ] **Commit:** "feat: add optimization history tracking"

### **PHASE 3: Interactive CLI Interface**
**Goal:** Enable user observation and intervention
- [ ] Create `interactive.py` with `InteractiveCLI` class
- [ ] Implement pause-per-iteration mode
- [ ] Display current pool, score, recent swaps
- [ ] Add command parser (continue, run N, swap, add, delete, view, export, quit)
- [ ] Integrate with optimizer (yield control after each iteration)
- [ ] Add `--interactive` flag to `optimize` command
- [ ] **Commit:** "feat: add interactive optimization mode"

### **PHASE 4: Manual Pool Editing**
**Goal:** Allow user to manually modify pool
- [ ] Implement `swap` command (validate rarity constraints)
- [ ] Implement `add` command (check rarity budget)
- [ ] Implement `delete` command (update counts)
- [ ] Update pool state and recompute score after edits
- [ ] Mark manual interventions in history
- [ ] **Commit:** "feat: enable manual pool editing in interactive mode"

### **PHASE 5: Visualization**
**Goal:** Generate charts showing optimization progress
- [ ] Add `matplotlib` dependency
- [ ] Create plotting function in `history.py`
- [ ] Generate line plot: iteration vs. score
- [ ] Annotate manual interventions and restarts
- [ ] Save to `output/optimization_history.png`
- [ ] Add `--visualize` flag
- [ ] **Commit:** "feat: add optimization visualization"

### **PHASE 6: Advanced Features**
**Goal:** Enhance algorithm robustness
- [ ] Add simulated annealing option (accept worse solutions probabilistically)
- [ ] Implement random restart when stuck
- [ ] Add tabu list (avoid recently swapped items)
- [ ] Support variable k-opt (start with k=2, increase if stuck)
- [ ] Add parallel neighborhood evaluation (multiprocessing)
- [ ] **Commit:** "feat: add simulated annealing and restarts"

### **PHASE 7: Documentation & Polish**
**Goal:** Finalize and document
- [ ] Update `README.md` with optimization command examples
- [ ] Add docstrings to all new modules
- [ ] Write integration tests for full optimization workflow
- [ ] Add example configurations for different optimization strategies
- [ ] Create `OPTIMIZATION_GUIDE.md` with algorithm explanation
- [ ] **Commit:** "docs: document optimization system"

---

## 6. Algorithm Pseudocode

### 6.1 Main Optimizer Loop

```python
def optimize_pool(items, config, interactive=False):
    # Initialize
    pool = generate_initial_pool(items, config)
    best_pool = pool
    best_score = score_pool(pool, ...)
    history = []
    stale_iterations = 0
    
    for iteration in range(max_iterations):
        # Generate neighborhood (all possible k-opt swaps)
        neighborhood = generate_neighborhood(pool, items, k=k_opt)
        
        # Evaluate all candidates
        scored_swaps = [(swap, compute_delta(pool, swap)) for swap in neighborhood]
        scored_swaps.sort(key=lambda x: x[1], reverse=True)  # best first
        
        # Select best swap
        if scored_swaps and scored_swaps[0][1] > 0:
            best_swap, delta = scored_swaps[0]
            apply_swap(pool, best_swap)
            new_score = score_pool(pool, ...)
            history.append(HistoryEntry(iteration, new_score, best_swap, False))
            stale_iterations = 0
            
            if new_score > best_score:
                best_score = new_score
                best_pool = copy(pool)
        else:
            # No improvement found
            stale_iterations += 1
            history.append(HistoryEntry(iteration, score_pool(pool, ...), None, False))
        
        # Check convergence
        if stale_iterations >= convergence_threshold:
            print("Converged: no improvement in {convergence_threshold} iterations")
            break
        
        # Interactive mode: yield control
        if interactive:
            action = interactive_cli.prompt(pool, history)
            if action == "quit":
                break
            elif action.startswith("swap"):
                handle_manual_swap(pool, action)
            # ... handle other commands
    
    return best_pool, history
```

### 6.2 K-Opt Swap Generation

```python
def generate_neighborhood(pool, all_items, k=1):
    """Generate all k-opt swaps that respect rarity constraints."""
    swaps = []
    
    # Partition items by rarity
    pool_by_rarity = partition_by_rarity(pool)
    available_by_rarity = partition_by_rarity(all_items, exclude=pool)
    
    # For each rarity, generate all k-combinations
    for rarity in pool_by_rarity.keys():
        pool_items = pool_by_rarity[rarity]
        available_items = available_by_rarity.get(rarity, [])
        
        if len(available_items) < k:
            continue  # Not enough items to swap
        
        # Generate all ways to select k items from pool
        for items_to_remove in combinations(pool_items, k):
            # Generate all ways to select k items from available
            for items_to_add in combinations(available_items, k):
                swap = Swap(remove=items_to_remove, add=items_to_add, rarity=rarity)
                swaps.append(swap)
    
    return swaps
```

### 6.3 Score Delta Computation (Fast)

```python
def compute_delta(pool, swap):
    """Compute score change without recomputing entire pool.
    
    Only evaluate:
    1. Style match change (does new item match better?)
    2. Synergy change (new edges added/removed in graph)
    """
    delta = 0
    
    # Style contribution
    for item_in in swap.add:
        if target_style in item_in['Playstyles']:
            delta += 1
    for item_out in swap.remove:
        if target_style in item_out['Playstyles']:
            delta -= 1
    
    # Synergy contribution (only edges touching swapped items)
    for item_in in swap.add:
        for other in pool:
            if other not in swap.remove:
                delta += synergy_graph[item_in['Name']].get(other['Name'], 0)
    
    for item_out in swap.remove:
        for other in pool:
            if other not in swap.remove:
                delta -= synergy_graph[item_out['Name']].get(other['Name'], 0)
    
    return delta * synergy_weight
```

---

## 7. Testing Strategy

### Unit Tests
- `test_optimizer.py`:
  - Swap generation preserves rarity counts
  - Delta computation matches full score recomputation
  - Convergence detection works correctly
  
- `test_interactive.py`:
  - Command parsing works
  - Manual swaps update state correctly
  - Invalid commands are rejected

### Integration Tests
- `test_optimization_flow.py`:
  - End-to-end optimization completes
  - History is tracked correctly
  - Interactive mode can be simulated (mock input)

### Regression Tests
- Ensure existing `generate` command still works
- Ensure existing `build` command still works

---

## 8. Configuration Examples

### Example 1: Fast Optimization (Greedy, Low K)
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

### Example 2: Thorough Search (Higher K, Annealing)
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
    "convergence_threshold": 20,
    "use_simulated_annealing": true,
    "temperature_initial": 2.0,
    "temperature_decay": 0.98
  }
}
```

---

## 9. Performance Considerations

### Neighborhood Size
- **1-opt:** O(n × m) where n = pool size, m = available items per rarity
  - Example: 10 items in pool, 50 available per rarity → ~500 swaps
- **2-opt:** O(n² × m²)
  - Example: 10 items, 50 available → ~250,000 swaps
- **Mitigation:** 
  - Use 1-opt by default
  - Only use 2-opt when stuck
  - Sample neighborhood instead of evaluating all

### Score Computation
- Current implementation recomputes full synergy matrix each time
- **Optimization:** Cache synergy contributions, only update deltas
- Expected speedup: 100x for large pools

### Parallel Evaluation
- Swap evaluation is embarrassingly parallel
- Use `multiprocessing.Pool` to evaluate swaps in parallel
- Expected speedup: 4-8x on modern CPUs

---

## 10. Success Criteria

### Functional Requirements
- ✅ Optimization finds better pools than random sampling
- ✅ Rarity constraints are never violated
- ✅ Interactive mode allows user to observe and intervene
- ✅ Manual swaps work correctly
- ✅ History is tracked and exportable
- ✅ Visualization shows improvement over time

### Performance Requirements
- ✅ 1-opt optimization completes in < 5 seconds for 10-item pool
- ✅ Interactive mode responds to commands in < 100ms

### Code Quality Requirements
- ✅ All new code has docstrings
- ✅ Test coverage > 80% for new modules
- ✅ No regression in existing functionality
- ✅ Code follows existing project style

---

## 11. Future Enhancements (Out of Scope for Initial Implementation)

- **Genetic Algorithms:** Population-based search with crossover and mutation
- **Constraint Programming:** Use SAT/CSP solvers for guaranteed optimal solutions
- **Multi-Objective Optimization:** Optimize for multiple criteria (synergy, diversity, etc.)
- **Web Interface:** Replace CLI with web UI (Flask + React)
- **Recommendation System:** Suggest items based on user's playstyle preferences
- **Machine Learning:** Train model to predict item synergies from descriptions

---

## 12. Timeline Estimate

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1 | Core optimizer (batch) | 2-3 hours |
| Phase 2 | History tracking | 1 hour |
| Phase 3 | Interactive CLI | 2-3 hours |
| Phase 4 | Manual editing | 1-2 hours |
| Phase 5 | Visualization | 1 hour |
| Phase 6 | Advanced features | 2-3 hours |
| Phase 7 | Documentation & polish | 1-2 hours |
| **Total** | | **10-15 hours** |

---

## 13. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Optimization gets stuck in local optimum | High | Medium | Add restarts, annealing, tabu list |
| K-opt becomes too slow for large k | High | Medium | Default to k=1, sample neighborhoods |
| User enters invalid manual swaps | Medium | Low | Validate all commands, clear error messages |
| Visualization fails on systems without GUI | Low | Low | Make visualization optional, fail gracefully |
| History JSON becomes large | Low | Low | Add rotation/compression |

---

## Conclusion

This plan transforms the RoR2 item pool generator into a sophisticated optimization system that:
1. **Finds better builds** through systematic local search
2. **Respects constraints** (rarity counts preserved)
3. **Enables user control** through interactive mode
4. **Tracks progress** with full history and visualization
5. **Maintains code quality** through testing and documentation

The phased approach allows incremental delivery and testing, ensuring stability at each milestone.

---

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 1 implementation
3. Commit after each phase completion
4. Iterate based on testing results
