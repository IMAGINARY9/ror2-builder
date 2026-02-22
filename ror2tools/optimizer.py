"""
Local search optimizer for Risk of Rain 2 item pools.

This module implements iterative optimization algorithms that improve
item pools while respecting rarity constraints.
"""

import random
import copy
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from itertools import combinations

from .scoring import score_pool, compute_score_delta


@dataclass
class Swap:
    """Represents a k-opt swap operation."""
    remove: List[Dict]  # Items to remove from pool
    add: List[Dict]     # Items to add to pool
    rarity: str         # Rarity being swapped (for validation)
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
        temperature_initial: float = 1.0,
        temperature_decay: float = 0.95,
        random_seed: Optional[int] = None
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
            temperature_initial: Starting temperature for annealing
            temperature_decay: Temperature multiplier per iteration
            random_seed: Random seed for reproducibility
        """
        self.items = items
        self.config = config
        self.k_opt = k_opt
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.use_simulated_annealing = use_simulated_annealing
        self.temperature = temperature_initial
        self.temperature_decay = temperature_decay
        
        # Extract config parameters
        self.style = config.get('style')
        self.synergy_weight = config.get('synergy_weight', 0)
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
        Generate all k-opt swaps that respect rarity constraints.
        
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
        
        # For each rarity, generate k-combinations
        for rarity in pool_by_rarity.keys():
            pool_items = pool_by_rarity[rarity]
            available_items = available_by_rarity.get(rarity, [])
            
            # Need at least k items in both sets
            if len(pool_items) < k or len(available_items) < k:
                continue
            
            # Generate all k-combinations from pool
            for items_to_remove in combinations(pool_items, k):
                # Generate all k-combinations from available
                for items_to_add in combinations(available_items, k):
                    swap = Swap(
                        remove=list(items_to_remove),
                        add=list(items_to_add),
                        rarity=rarity
                    )
                    swaps.append(swap)
        
        return swaps
    
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
                synergy_weight=self.synergy_weight
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
        probability = math.exp(delta / temperature)
        return random.random() < probability
    
    def _generate_initial_pool(self) -> List[Dict]:
        """
        Generate initial random pool respecting rarity constraints.
        
        Returns:
            Random pool
        """
        pool = []
        items_by_rarity = self._partition_by_rarity(self.items)
        
        # Extract rarity counts from config
        for rarity, count in self.config.items():
            if not isinstance(count, int) or count <= 0:
                continue
            if rarity in ('require_tags', 'require_playstyles', 'style',
                         'size', 'synergy_weight', 'optimization'):
                continue
            
            candidates = items_by_rarity.get(rarity, [])
            if candidates:
                sample_size = min(count, len(candidates))
                pool.extend(random.sample(candidates, sample_size))
        
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
            pool, self.graph, self.style, self.synergy_weight
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
        
        # Optimization loop
        for iteration in range(self.max_iterations):
            state.iteration = iteration
            
            # Generate neighborhood
            neighborhood = self._generate_neighborhood(state.pool)
            
            # If neighborhood is empty, we're stuck
            if not neighborhood:
                break
            
            # Evaluate all swaps
            evaluated_swaps = self._evaluate_swaps(state.pool, neighborhood)
            
            # Select best swap
            best_swap = evaluated_swaps[0] if evaluated_swaps else None
            
            # Decide whether to accept
            if best_swap and self._should_accept(best_swap.delta, self.temperature):
                # Apply swap
                state.pool = self._apply_swap(state.pool, best_swap)
                state.score += best_swap.delta
                state.last_swap = best_swap
                
                # Update best if improved
                if state.score > state.best_score:
                    state.best_score = state.score
                    state.best_pool = copy.deepcopy(state.pool)
                    state.stale_iterations = 0
                else:
                    state.stale_iterations += 1
            else:
                # No improvement
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
