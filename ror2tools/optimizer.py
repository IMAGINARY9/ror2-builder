"""
Local search optimizer for Risk of Rain 2 item pools.

This module implements iterative optimization algorithms that improve
item pools while respecting rarity constraints.  Includes a tabu list
to prevent cycling back to recently visited pool states.
"""

import random
import copy
from typing import List, Dict, Tuple, Optional, Set, FrozenSet
from dataclasses import dataclass, field
from collections import Counter
from itertools import combinations

from .scoring import score_pool, compute_score_delta


@dataclass
class Swap:
    """Represents a k-opt swap operation."""
    remove: List[Dict]  # Items to remove from pool
    add: List[Dict]     # Items to add to pool
    rarity: str         # Rarity being swapped (single rarity or 'mixed')
    delta: float = 0.0  # Expected score change
    
    def __repr__(self):
        remove_names = [item['Name'] for item in self.remove]
        add_names = [item['Name'] for item in self.add]
        return f"Swap({remove_names} → {add_names}, Δ={self.delta:.2f})"


@dataclass
class OptimizationState:
    """Represents the state of an optimization run."""
    pool: List[Dict]
    score: float
    iteration: int
    stale_iterations: int  # Iterations without improvement
    best_pool: List[Dict]
    best_score: float
    last_swap: Optional[Swap] = None
    tabu_skipped: int = 0  # Swaps skipped due to tabu this iteration


class TabuList:
    """
    Tracks visited pool states to prevent the optimizer from cycling.

    Each pool state is represented as a *frozenset* of item names.
    A state is considered tabu (forbidden) if it was visited within the
    last ``tenure`` iterations.  When ``tenure`` is ``None`` the memory
    is infinite – every state visited during the run is remembered.

    An **aspiration criterion** can override the tabu status: if
    accepting a tabu move would produce a new global-best score the
    move is allowed regardless.

    Args:
        tenure: Number of iterations a state stays tabu.
                ``None`` (default) means infinite memory.
    """

    def __init__(self, tenure: Optional[int] = None) -> None:
        self.tenure = tenure
        # Maps pool fingerprint → iteration when the state was last visited
        self._visited: Dict[FrozenSet[str], int] = {}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def pool_fingerprint(pool: List[Dict]) -> FrozenSet[str]:
        """Create a hashable fingerprint of a pool (frozenset of names)."""
        return frozenset(item['Name'] for item in pool)

    @staticmethod
    def swap_result_fingerprint(
        current_fp: FrozenSet[str],
        swap: 'Swap',
    ) -> FrozenSet[str]:
        """Compute the fingerprint that would result from applying *swap*."""
        remove_names = frozenset(item['Name'] for item in swap.remove)
        add_names = frozenset(item['Name'] for item in swap.add)
        return (current_fp - remove_names) | add_names

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record(self, pool: List[Dict], iteration: int = 0) -> None:
        """Mark a pool state as visited at *iteration*."""
        fp = self.pool_fingerprint(pool)
        self._visited[fp] = iteration

    def record_fingerprint(self, fp: FrozenSet[str], iteration: int = 0) -> None:
        """Mark an already-computed fingerprint as visited."""
        self._visited[fp] = iteration

    def is_tabu(self, fingerprint: FrozenSet[str], current_iteration: int = 0) -> bool:
        """Return True if *fingerprint* is currently tabu."""
        if fingerprint not in self._visited:
            return False
        if self.tenure is None:
            return True  # infinite memory – always tabu once visited
        visited_at = self._visited[fingerprint]
        return (current_iteration - visited_at) <= self.tenure

    def clear(self) -> None:
        """Remove all recorded states."""
        self._visited.clear()

    @property
    def size(self) -> int:
        """Number of currently tracked states."""
        return len(self._visited)


class LocalSearchOptimizer:
    """
    Iterative local search optimizer using k-opt swaps.
    
    The optimizer maintains rarity constraints by only swapping items
    of the same rarity. It explores the neighborhood of the current
    solution and greedily selects the best improvement.
    """
    
    def __init__(
        self,
        items: List[Dict],
        config: Dict,
        k_opt: int = 1,
        max_iterations: int = 100,
        convergence_threshold: int = 10,
        use_simulated_annealing: bool = False,
        temperature_initial: float = 10.0,
        temperature_decay: float = 0.98,
        temperature_min: float = 0.1,
        tabu_tenure: Optional[int] = None,
        random_seed: Optional[int] = None,
        cross_rarity: bool = False
    ):
        """
        Initialize the optimizer.
        
        Args:
            items: Full list of available items
            config: Configuration dict with rarity counts, style, etc.
            k_opt: Number of items to swap simultaneously (1 = swap one item)
            max_iterations: Maximum optimization iterations
            convergence_threshold: Stop if no improvement for this many iterations
            use_simulated_annealing: Accept worse solutions probabilistically
            temperature_initial: Starting temperature for annealing (increased from 1.0)
            temperature_decay: Temperature multiplier per iteration (slower from 0.95)
            temperature_min: Minimum temperature floor (new parameter)
            tabu_tenure: Iterations a visited pool state stays tabu.
                         ``None`` = infinite memory (default, strongest anti-cycling).
                         Set to a positive int for a sliding window.
            random_seed: Random seed for reproducibility
            cross_rarity: Allow cross-rarity swaps (e.g. 1 red + 1 green ↔
                          1 green + 1 red).  Only effective when k_opt >= 2.
        """
        self.items = items
        self.config = config
        self.k_opt = k_opt
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.use_simulated_annealing = use_simulated_annealing
        self.temperature = temperature_initial
        self.temperature_decay = temperature_decay
        self.temperature_min = temperature_min
        self.cross_rarity = cross_rarity
        
        # Tabu list (prevents cycling back to recently visited pool states)
        self.tabu = TabuList(tenure=tabu_tenure)
        
        # Extract config parameters
        self.style = config.get('style')
        self.synergy_weight = config.get('synergy_weight', 0.5)
        self.style_weight = config.get('style_weight', 8.0)
        self.diversity_weight = config.get('diversity_weight', 1.0)
        self.coverage_weight = config.get('coverage_weight', 1.0)
        self.balance_weight = config.get('balance_weight', 5.0)
        self.pinned_items = set(config.get('pinned_items', []))  # Items user wants to keep
        self.graph = None  # Will be loaded when needed
        
        if random_seed is not None:
            random.seed(random_seed)
    
    def _partition_by_rarity(
        self,
        items: List[Dict],
        exclude: Optional[Set[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Partition items by rarity.
        
        Args:
            items: Items to partition
            exclude: Set of item names to exclude
        
        Returns:
            Dictionary mapping rarity → list of items
        """
        partitions = {}
        exclude_set = exclude or set()
        
        for item in items:
            if item['Name'] in exclude_set:
                continue
            rarity = item['Rarity']
            if rarity not in partitions:
                partitions[rarity] = []
            partitions[rarity].append(item)
        
        return partitions
    
    def _generate_neighborhood(
        self,
        pool: List[Dict],
        k: Optional[int] = None
    ) -> List[Swap]:
        """
        Generate all k-opt swaps that respect rarity constraints and pinned items.
        
        When ``cross_rarity`` is enabled and k >= 2, also generates swaps
        that span multiple rarities while preserving the rarity multiset
        (e.g. remove 1 Common + 1 Legendary, add 1 Common + 1 Legendary).
        
        Args:
            pool: Current pool
            k: Number of items to swap (defaults to self.k_opt)
        
        Returns:
            List of Swap objects
        """
        if k is None:
            k = self.k_opt
        
        swaps = []
        
        # Partition pool and available items by rarity
        pool_names = {item['Name'] for item in pool}
        pool_by_rarity = self._partition_by_rarity(pool)
        available_by_rarity = self._partition_by_rarity(self.items, exclude=pool_names)
        
        # ---- Same-rarity swaps (original logic) ----
        for rarity in pool_by_rarity.keys():
            pool_items = pool_by_rarity[rarity]
            available_items = available_by_rarity.get(rarity, [])
            
            # Filter out pinned items from pool_items (we can't remove them)
            unpinned_pool_items = [item for item in pool_items 
                                   if item['Name'] not in self.pinned_items]
            
            # Need at least k items in both sets
            if len(unpinned_pool_items) < k or len(available_items) < k:
                continue
            
            # Generate all k-combinations from unpinned pool items
            for items_to_remove in combinations(unpinned_pool_items, k):
                # Generate all k-combinations from available
                for items_to_add in combinations(available_items, k):
                    swap = Swap(
                        remove=list(items_to_remove),
                        add=list(items_to_add),
                        rarity=rarity
                    )
                    swaps.append(swap)
        
        # ---- Cross-rarity swaps (new) ----
        if self.cross_rarity and k >= 2:
            swaps.extend(self._generate_cross_rarity_swaps(pool, pool_by_rarity,
                                                           available_by_rarity, k))
        
        return swaps
    
    def _generate_cross_rarity_swaps(
        self,
        pool: List[Dict],
        pool_by_rarity: Dict[str, List[Dict]],
        available_by_rarity: Dict[str, List[Dict]],
        k: int
    ) -> List[Swap]:
        """
        Generate cross-rarity k-opt swaps that preserve the rarity multiset.
        
        For k items to remove, the added items must have the exact same
        rarity distribution (e.g. {Common: 1, Legendary: 1}).
        Only generates swaps that span at least 2 different rarities
        (single-rarity combos are already covered by the main loop).
        
        To control combinatorial explosion, candidate additions are sampled
        randomly when the full neighbourhood would exceed a size limit.
        
        Args:
            pool: Current pool
            pool_by_rarity: Pool items partitioned by rarity
            available_by_rarity: Available (non-pool) items partitioned by rarity
            k: Number of items to swap
        
        Returns:
            List of cross-rarity Swap objects
        """
        MAX_CROSS_SWAPS = 2000  # cap to prevent combinatorial explosion
        
        # Build flat list of unpinned pool items across all rarities
        unpinned_pool: List[Dict] = []
        for rarity_items in pool_by_rarity.values():
            unpinned_pool.extend(
                item for item in rarity_items
                if item['Name'] not in self.pinned_items
            )
        
        if len(unpinned_pool) < k:
            return []
        
        swaps: List[Swap] = []
        
        # Generate k-combinations from unpinned pool items (any rarity mix)
        for items_to_remove in combinations(unpinned_pool, k):
            rarity_counts = Counter(item['Rarity'] for item in items_to_remove)
            
            # Skip single-rarity combos (already handled by same-rarity logic)
            if len(rarity_counts) < 2:
                continue
            
            # Build candidate adds: for each rarity in the multiset,
            # pick that many items from available_by_rarity[rarity].
            # The cross product of per-rarity combos gives valid additions.
            per_rarity_combos: List[List[Tuple]] = []
            feasible = True
            for rarity, count in rarity_counts.items():
                candidates = available_by_rarity.get(rarity, [])
                if len(candidates) < count:
                    feasible = False
                    break
                per_rarity_combos.append(
                    list(combinations(candidates, count))
                )
            
            if not feasible:
                continue
            
            # Cartesian product of per-rarity combos
            add_combos = self._cartesian_product(per_rarity_combos)
            
            for add_tuple_of_tuples in add_combos:
                items_to_add = []
                for combo in add_tuple_of_tuples:
                    items_to_add.extend(combo)
                
                swap = Swap(
                    remove=list(items_to_remove),
                    add=items_to_add,
                    rarity='mixed'
                )
                swaps.append(swap)
                
                if len(swaps) >= MAX_CROSS_SWAPS:
                    return swaps
        
        return swaps
    
    @staticmethod
    def _cartesian_product(
        lists: List[List[Tuple]]
    ) -> List[Tuple[Tuple, ...]]:
        """
        Compute the Cartesian product of a list of lists of tuples.
        
        Args:
            lists: List of lists, each containing tuples of items.
        
        Returns:
            List of tuples, each containing one element from each input list.
        """
        if not lists:
            return []
        result = [()]
        for pool_list in lists:
            result = [existing + (item,) for existing in result for item in pool_list]
        return result
    
    def _evaluate_swaps(
        self,
        pool: List[Dict],
        swaps: List[Swap]
    ) -> List[Swap]:
        """
        Evaluate score delta for each swap.
        
        Args:
            pool: Current pool
            swaps: List of swaps to evaluate
        
        Returns:
            Swaps with delta computed, sorted by delta (best first)
        """
        for swap in swaps:
            swap.delta = compute_score_delta(
                pool=pool,
                items_to_remove=swap.remove,
                items_to_add=swap.add,
                graph=self.graph,
                style=self.style,
                synergy_weight=self.synergy_weight,
                style_weight=self.style_weight,
                diversity_weight=self.diversity_weight,
                coverage_weight=self.coverage_weight,
                balance_weight=self.balance_weight,
                pinned_items=self.pinned_items,
                pin_bonus=2.0,
                pin_synergy_bonus=1.5
            )
        
        # Sort by delta descending (best improvements first)
        swaps.sort(key=lambda s: s.delta, reverse=True)
        return swaps
    
    def _apply_swap(self, pool: List[Dict], swap: Swap) -> List[Dict]:
        """
        Apply a swap to a pool (creates new pool).
        
        Args:
            pool: Current pool
            swap: Swap to apply
        
        Returns:
            New pool with swap applied
        """
        remove_names = {item['Name'] for item in swap.remove}
        new_pool = [item for item in pool if item['Name'] not in remove_names]
        new_pool.extend(swap.add)
        return new_pool
    
    def _should_accept(self, delta: float, temperature: float) -> bool:
        """
        Simulated annealing acceptance criterion.
        
        Args:
            delta: Score change (positive = improvement)
            temperature: Current temperature
        
        Returns:
            True if swap should be accepted
        """
        if delta > 0:
            return True  # Always accept improvements
        
        if not self.use_simulated_annealing:
            return False  # Reject all downgrades in greedy mode
        
        # Accept downgrades probabilistically
        import math
        # Apply temperature floor to maintain some randomness
        effective_temp = max(temperature, self.temperature_min)
        probability = math.exp(delta / effective_temp)
        return random.random() < probability
    
    def _generate_initial_pool(self) -> List[Dict]:
        """
        Generate initial random pool respecting rarity constraints.
        
        IMPORTANT: Ensures category diversity by requiring at least one item
        from each core category (Damage, Utility, Healing) to create playable pools.
        
        Returns:
            Random pool with guaranteed category coverage
        """
        items_by_rarity = self._partition_by_rarity(self.items)
        
        # Core categories that MUST be represented
        CORE_CATEGORIES = {'Damage', 'Utility', 'Healing'}
        
        # Extract rarity counts from config
        rarity_counts = {}
        for rarity, count in self.config.items():
            if not isinstance(count, int) or count <= 0:
                continue
            if rarity in ('require_tags', 'require_playstyles', 'style',
                         'size', 'synergy_weight', 'optimization'):
                continue
            rarity_counts[rarity] = count
        
        # Helper to get item's primary category
        def get_category(item):
            cats = item.get('Category', '')
            if isinstance(cats, str):
                for core in CORE_CATEGORIES:
                    if core in cats:
                        return core
            return None
        
        # Partition items by rarity AND category
        items_by_rarity_cat = {}
        for rarity, items in items_by_rarity.items():
            items_by_rarity_cat[rarity] = {}
            for cat in CORE_CATEGORIES:
                items_by_rarity_cat[rarity][cat] = [
                    it for it in items if get_category(it) == cat
                ]
        
        pool = []
        used_names = set()
        categories_filled = {cat: False for cat in CORE_CATEGORIES}
        
        # First pass: ensure at least one item from each category
        # Pick from most common rarity first
        primary_rarity = 'Common'
        for cat in CORE_CATEGORIES:
            candidates = items_by_rarity_cat.get(primary_rarity, {}).get(cat, [])
            if not candidates:
                # Try any rarity
                for rarity in items_by_rarity_cat:
                    candidates = items_by_rarity_cat[rarity].get(cat, [])
                    if candidates:
                        break
            if candidates:
                item = random.choice(candidates)
                pool.append(item)
                used_names.add(item['Name'])
                categories_filled[cat] = True
        
        # Second pass: fill remaining slots by rarity
        for rarity, count in rarity_counts.items():
            candidates = [it for it in items_by_rarity.get(rarity, []) 
                         if it['Name'] not in used_names]
            
            # Count how many of this rarity already in pool
            already_have = sum(1 for it in pool if it.get('Rarity') == rarity)
            need = max(0, count - already_have)
            
            if candidates and need > 0:
                sample_size = min(need, len(candidates))
                selected = random.sample(candidates, sample_size)
                for item in selected:
                    pool.append(item)
                    used_names.add(item['Name'])
        
        return pool
    
    def optimize(
        self,
        initial_pool: Optional[List[Dict]] = None,
        callback: Optional[callable] = None
    ) -> Tuple[List[Dict], OptimizationState]:
        """
        Run optimization loop.
        
        Args:
            initial_pool: Starting pool (if None, generates random)
            callback: Optional function called after each iteration with state
                      Should return True to continue, False to stop
        
        Returns:
            Tuple of (best_pool, final_state)
        """
        # Load synergy graph
        from .utils import load_synergy_graph
        self.graph = load_synergy_graph()
        
        # Initialize pool
        if initial_pool is None:
            pool = self._generate_initial_pool()
        else:
            pool = copy.deepcopy(initial_pool)
        
        # Compute initial score
        current_score = score_pool(
            pool, self.graph, self.style, self.synergy_weight,
            self.style_weight, self.diversity_weight, self.coverage_weight,
            self.pinned_items
        )
        
        # Initialize state
        state = OptimizationState(
            pool=pool,
            score=current_score,
            iteration=0,
            stale_iterations=0,
            best_pool=copy.deepcopy(pool),
            best_score=current_score
        )
        
        # Record initial pool in tabu list so we never cycle back to it
        self.tabu.record(pool, iteration=0)
        
        # Optimization loop
        for iteration in range(self.max_iterations):
            state.iteration = iteration
            state.tabu_skipped = 0
            
            # Generate neighborhood
            neighborhood = self._generate_neighborhood(state.pool)
            
            # If neighborhood is empty, we're stuck
            if not neighborhood:
                break
            
            # Evaluate all swaps (sorted best-first)
            evaluated_swaps = self._evaluate_swaps(state.pool, neighborhood)
            
            # ----------------------------------------------------------
            # Tabu-aware swap selection
            # ----------------------------------------------------------
            current_fp = TabuList.pool_fingerprint(state.pool)
            selected_swap: Optional[Swap] = None
            
            for swap in evaluated_swaps:
                result_fp = TabuList.swap_result_fingerprint(current_fp, swap)
                
                # Aspiration criterion: override tabu if this swap would
                # produce a new global best score.
                is_aspiration = (state.score + swap.delta) > state.best_score
                
                if self.tabu.is_tabu(result_fp, iteration) and not is_aspiration:
                    state.tabu_skipped += 1
                    continue  # skip tabu move
                
                # First non-tabu (or aspiration-eligible) swap —
                # check acceptance criterion (greedy / SA).
                if self._should_accept(swap.delta, self.temperature):
                    selected_swap = swap
                break  # only test acceptance for the best non-tabu swap
            
            # ----------------------------------------------------------
            # Apply or reject
            # ----------------------------------------------------------
            if selected_swap is not None:
                state.pool = self._apply_swap(state.pool, selected_swap)
                state.score += selected_swap.delta
                state.last_swap = selected_swap
                
                # Record new pool state in tabu list
                self.tabu.record(state.pool, iteration)
                
                # Update best if improved
                if state.score > state.best_score:
                    state.best_score = state.score
                    state.best_pool = copy.deepcopy(state.pool)
                    state.stale_iterations = 0
                else:
                    state.stale_iterations += 1
            else:
                # Nothing accepted this iteration
                state.stale_iterations += 1
                state.last_swap = None
            
            # Decay temperature for annealing
            if self.use_simulated_annealing:
                self.temperature *= self.temperature_decay
            
            # Call callback (for interactive mode)
            if callback:
                should_continue = callback(state)
                if not should_continue:
                    break
            
            # Check convergence
            if state.stale_iterations >= self.convergence_threshold:
                break
        
        return state.best_pool, state
    
    def random_restart(
        self,
        current_best: List[Dict],
        perturbation_ratio: float = 0.3
    ) -> List[Dict]:
        """
        Generate a perturbed version of the current best pool.
        
        Args:
            current_best: Current best pool
            perturbation_ratio: Fraction of items to randomly swap
        
        Returns:
            Perturbed pool
        """
        pool = copy.deepcopy(current_best)
        pool_names = {item['Name'] for item in pool}
        
        # Determine how many items to perturb
        num_perturb = max(1, int(len(pool) * perturbation_ratio))
        
        # Select random items to replace
        items_to_remove = random.sample(pool, num_perturb)
        
        # Replace with random alternatives of same rarity
        available_by_rarity = self._partition_by_rarity(self.items, exclude=pool_names)
        
        for item in items_to_remove:
            pool.remove(item)
            candidates = available_by_rarity.get(item['Rarity'], [])
            if candidates:
                replacement = random.choice(candidates)
                pool.append(replacement)
                # Update exclusion set
                pool_names.add(replacement['Name'])
        
        return pool
