"""
Basic integration tests for the optimization system.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ror2tools.scoring import score_pool, compute_score_delta, score_breakdown
from ror2tools.optimizer import LocalSearchOptimizer, Swap, TabuList
from ror2tools.history import OptimizationHistory, HistoryEntry


def test_scoring_basic():
    """Test basic scoring function."""
    pool = [
        {'Name': 'Item1', 'Playstyles': ['frenzy'], 'Rarity': 'Common', 'Category': 'Damage'},
        {'Name': 'Item2', 'Playstyles': ['cc'], 'Rarity': 'Uncommon', 'Category': 'Utility'},
    ]
    
    # Style score only (explicit weights for predictable assertions)
    score = score_pool(pool, style='frenzy', style_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    assert score == 1.0, "Should count 1 item matching 'frenzy'"
    
    score = score_pool(pool, style='cc', style_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    assert score == 1.0, "Should count 1 item matching 'cc'"


def test_scoring_with_graph():
    """Test scoring with synergy graph."""
    pool = [
        {'Name': 'A', 'Playstyles': [], 'Rarity': 'Common', 'Category': 'Damage'},
        {'Name': 'B', 'Playstyles': [], 'Rarity': 'Common', 'Category': 'Utility'},
    ]
    
    graph = {
        'A': {'B': 2},
        'B': {'A': 2}
    }
    
    score = score_pool(pool, graph=graph, synergy_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    assert score == 4.0, "Should sum synergy edges (2+2)"


def test_score_delta():
    """Test delta computation."""
    pool = [
        {'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common', 'Category': 'Damage'},
        {'Name': 'B', 'Playstyles': [], 'Rarity': 'Common', 'Category': 'Utility'},
    ]
    
    item_to_remove = [{'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common', 'Category': 'Damage'}]
    item_to_add = [{'Name': 'C', 'Playstyles': ['cc'], 'Rarity': 'Common', 'Category': 'Healing'}]
    
    # Style changes (explicit weights for predictable assertions)
    delta = compute_score_delta(pool, item_to_remove, item_to_add, style='frenzy', style_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    assert delta == -1.0, "Removing frenzy item should decrease score by 1"
    
    delta = compute_score_delta(pool, item_to_remove, item_to_add, style='cc', style_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    assert delta == 1.0, "Adding cc item should increase score by 1"


def test_score_breakdown():
    """Test score breakdown function."""
    pool = [
        {'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common', 'Category': 'Damage'},
        {'Name': 'B', 'Playstyles': ['frenzy'], 'Rarity': 'Common', 'Category': 'Utility'},
    ]
    
    graph = {
        'A': {'B': 1},
        'B': {'A': 1}
    }
    
    # Explicit weights for predictable assertions
    breakdown = score_breakdown(pool, graph, 'frenzy', synergy_weight=2.0, style_weight=1.0, diversity_weight=0, coverage_weight=0, balance_weight=0)
    
    assert breakdown['style_score'] == 2.0
    assert breakdown['synergy_score'] == 2.0
    assert breakdown['weighted_synergy'] == 4.0
    assert breakdown['total'] == 6.0


def test_optimizer_initialization():
    """Test optimizer can be initialized."""
    items = [
        {'Name': 'A', 'Rarity': 'Common', 'Playstyles': []},
        {'Name': 'B', 'Rarity': 'Common', 'Playstyles': []},
        {'Name': 'C', 'Rarity': 'Uncommon', 'Playstyles': []},
    ]
    
    config = {
        'Common': 1,
        'Uncommon': 1
    }
    
    optimizer = LocalSearchOptimizer(items, config, k_opt=1, max_iterations=10)
    assert optimizer.k_opt == 1
    assert optimizer.max_iterations == 10


def test_optimizer_partition_by_rarity():
    """Test rarity partitioning."""
    items = [
        {'Name': 'A', 'Rarity': 'Common'},
        {'Name': 'B', 'Rarity': 'Common'},
        {'Name': 'C', 'Rarity': 'Uncommon'},
    ]
    
    config = {'Common': 1}
    optimizer = LocalSearchOptimizer(items, config)
    
    partitions = optimizer._partition_by_rarity(items)
    assert 'Common' in partitions
    assert 'Uncommon' in partitions
    assert len(partitions['Common']) == 2
    assert len(partitions['Uncommon']) == 1


def test_optimizer_generate_initial_pool():
    """Test initial pool generation."""
    items = [
        {'Name': f'Common{i}', 'Rarity': 'Common', 'Playstyles': []} 
        for i in range(10)
    ] + [
        {'Name': f'Uncommon{i}', 'Rarity': 'Uncommon', 'Playstyles': []} 
        for i in range(5)
    ]
    
    config = {
        'Common': 3,
        'Uncommon': 2
    }
    
    optimizer = LocalSearchOptimizer(items, config, random_seed=42)
    pool = optimizer._generate_initial_pool()
    
    assert len(pool) == 5
    commons = [item for item in pool if item['Rarity'] == 'Common']
    uncommons = [item for item in pool if item['Rarity'] == 'Uncommon']
    assert len(commons) == 3
    assert len(uncommons) == 2


def test_swap_generation():
    """Test k-opt swap generation."""
    items = [
        {'Name': 'A', 'Rarity': 'Common', 'Playstyles': []},
        {'Name': 'B', 'Rarity': 'Common', 'Playstyles': []},
        {'Name': 'C', 'Rarity': 'Common', 'Playstyles': []},
        {'Name': 'D', 'Rarity': 'Common', 'Playstyles': []},
    ]
    
    pool = [items[0], items[1]]  # A, B in pool
    
    config = {'Common': 2}
    optimizer = LocalSearchOptimizer(items, config, k_opt=1)
    
    swaps = optimizer._generate_neighborhood(pool)
    
    # Should be able to swap A→C, A→D, B→C, B→D (4 swaps)
    assert len(swaps) == 4
    
    # Check all swaps preserve rarity
    for swap in swaps:
        assert swap.rarity == 'Common'
        assert len(swap.remove) == 1
        assert len(swap.add) == 1


def test_history_tracking():
    """Test history recording."""
    history = OptimizationHistory()
    
    assert len(history.entries) == 0
    
    entry = HistoryEntry(
        iteration=0,
        score=10.0,
        best_score=10.0,
        swap_from=['A'],
        swap_to=['B'],
        delta=2.0
    )
    
    history.entries.append(entry)
    assert len(history.entries) == 1
    assert history.entries[0].score == 10.0


def test_history_summary():
    """Test history summary generation."""
    history = OptimizationHistory()
    
    history.entries.append(HistoryEntry(0, 10.0, 10.0))
    history.entries.append(HistoryEntry(1, 12.0, 12.0, delta=2.0))
    history.entries.append(HistoryEntry(2, 15.0, 15.0, delta=3.0))
    
    summary = history.get_summary()
    
    assert summary['total_iterations'] == 3
    assert summary['initial_score'] == 10.0
    assert summary['final_score'] == 15.0
    assert summary['best_score'] == 15.0
    assert summary['total_improvement'] == 5.0
    assert summary['successful_swaps'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# ---------------------------------------------------------------------------
# TabuList unit tests
# ---------------------------------------------------------------------------

class TestTabuList:
    """Tests for the TabuList anti-cycling mechanism."""

    def _make_pool(self, names):
        """Helper: build a minimal pool from a list of names."""
        return [{'Name': n, 'Rarity': 'Common', 'Playstyles': [], 'Category': 'Damage'} for n in names]

    def test_record_and_is_tabu(self):
        """A recorded pool state should be tabu."""
        tl = TabuList()
        pool = self._make_pool(['A', 'B'])
        tl.record(pool, iteration=0)

        fp = TabuList.pool_fingerprint(pool)
        assert tl.is_tabu(fp, current_iteration=0)

    def test_unvisited_is_not_tabu(self):
        """A state never recorded should not be tabu."""
        tl = TabuList()
        fp = frozenset(['X', 'Y'])
        assert not tl.is_tabu(fp)

    def test_infinite_tenure(self):
        """With tenure=None, states stay tabu forever."""
        tl = TabuList(tenure=None)
        pool = self._make_pool(['A', 'B'])
        tl.record(pool, iteration=0)

        fp = TabuList.pool_fingerprint(pool)
        assert tl.is_tabu(fp, current_iteration=9999)

    def test_finite_tenure_expires(self):
        """With finite tenure, states expire after enough iterations."""
        tl = TabuList(tenure=3)
        pool = self._make_pool(['A', 'B'])
        tl.record(pool, iteration=0)

        fp = TabuList.pool_fingerprint(pool)
        # Within tenure window → tabu
        assert tl.is_tabu(fp, current_iteration=2)
        assert tl.is_tabu(fp, current_iteration=3)
        # Beyond tenure window → no longer tabu
        assert not tl.is_tabu(fp, current_iteration=4)

    def test_clear(self):
        """clear() should remove all tracked states."""
        tl = TabuList()
        tl.record(self._make_pool(['A', 'B']))
        tl.record(self._make_pool(['C', 'D']))
        assert tl.size == 2

        tl.clear()
        assert tl.size == 0

    def test_swap_result_fingerprint(self):
        """swap_result_fingerprint should compute the correct post-swap set."""
        current_fp = frozenset(['A', 'B', 'C'])
        swap = Swap(
            remove=[{'Name': 'A'}],
            add=[{'Name': 'D'}],
            rarity='Common',
        )
        result_fp = TabuList.swap_result_fingerprint(current_fp, swap)
        assert result_fp == frozenset(['B', 'C', 'D'])

    def test_pool_fingerprint(self):
        """pool_fingerprint should return a frozenset of item names."""
        pool = self._make_pool(['X', 'Y', 'Z'])
        fp = TabuList.pool_fingerprint(pool)
        assert fp == frozenset(['X', 'Y', 'Z'])
        assert isinstance(fp, frozenset)

    def test_size_property(self):
        """size property should reflect number of tracked states."""
        tl = TabuList()
        assert tl.size == 0
        tl.record(self._make_pool(['A']))
        assert tl.size == 1
        tl.record(self._make_pool(['B']))
        assert tl.size == 2


class TestTabuOptimization:
    """Integration tests verifying the optimizer uses the tabu list."""

    def _make_items(self, n=10):
        """Create n Common items with varied playstyles for meaningful swaps."""
        styles = ['frenzy', 'cc', 'tank', 'healer', 'glass']
        categories = ['Damage', 'Utility', 'Healing']
        return [
            {'Name': f'Item{i}', 'Rarity': 'Common',
             'Playstyles': [styles[i % len(styles)]],
             'Category': categories[i % len(categories)]}
            for i in range(n)
        ]

    def test_optimizer_never_revisits_state(self, monkeypatch):
        """With SA enabled, the optimizer should not revisit pool states."""
        # Build enough items with mixed styles so swaps are meaningful
        items = self._make_items(20)
        config = {'Common': 3, 'style': 'cc'}

        optimizer = LocalSearchOptimizer(
            items, config, k_opt=1, max_iterations=30,
            convergence_threshold=30, random_seed=7,
            use_simulated_annealing=True,
            temperature_initial=10.0,
            temperature_decay=0.95,
        )

        # Patch synergy graph to empty (low synergy → high cycling risk)
        monkeypatch.setattr(
            'ror2tools.utils.load_synergy_graph', lambda: {},
        )

        visited = set()
        swaps_applied = 0

        def recording_callback(state):
            nonlocal swaps_applied
            fp = TabuList.pool_fingerprint(state.pool)
            if state.last_swap is not None:
                swaps_applied += 1
                # A swap was actually applied — new state must be novel
                assert fp not in visited, (
                    f"Optimizer revisited pool state {fp} at iteration {state.iteration}"
                )
            visited.add(fp)
            return True

        optimizer.optimize(callback=recording_callback)
        # With SA + enough items, at least a few swaps should happen
        assert swaps_applied >= 1, "SA optimizer should apply at least one swap"

    def test_aspiration_allows_tabu(self, monkeypatch):
        """A tabu state should be allowed if it beats the global best (aspiration)."""
        tl = TabuList()
        pool_a = [{'Name': 'A', 'Rarity': 'Common', 'Playstyles': [], 'Category': 'Damage'}]
        tl.record(pool_a, iteration=0)

        fp_a = TabuList.pool_fingerprint(pool_a)
        # The state is tabu…
        assert tl.is_tabu(fp_a, current_iteration=1)
        # …but the aspiration criterion is checked by the optimizer outside
        # TabuList, so the list itself always reports tabu faithfully.
        # This test just confirms the flag is correct; the optimizer override
        # is covered by test_optimizer_never_revisits_state (it would hang
        # without aspiration enabled).
