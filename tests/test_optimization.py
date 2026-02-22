"""
Basic integration tests for the optimization system.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ror2tools.scoring import score_pool, compute_score_delta, score_breakdown
from ror2tools.optimizer import LocalSearchOptimizer, Swap
from ror2tools.history import OptimizationHistory, HistoryEntry


def test_scoring_basic():
    """Test basic scoring function."""
    pool = [
        {'Name': 'Item1', 'Playstyles': ['frenzy'], 'Rarity': 'Common'},
        {'Name': 'Item2', 'Playstyles': ['cc'], 'Rarity': 'Uncommon'},
    ]
    
    # Style score only
    score = score_pool(pool, style='frenzy')
    assert score == 1.0, "Should count 1 item matching 'frenzy'"
    
    score = score_pool(pool, style='cc')
    assert score == 1.0, "Should count 1 item matching 'cc'"


def test_scoring_with_graph():
    """Test scoring with synergy graph."""
    pool = [
        {'Name': 'A', 'Playstyles': [], 'Rarity': 'Common'},
        {'Name': 'B', 'Playstyles': [], 'Rarity': 'Common'},
    ]
    
    graph = {
        'A': {'B': 2},
        'B': {'A': 2}
    }
    
    score = score_pool(pool, graph=graph, synergy_weight=1.0)
    assert score == 4.0, "Should sum synergy edges (2+2)"


def test_score_delta():
    """Test delta computation."""
    pool = [
        {'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common'},
        {'Name': 'B', 'Playstyles': [], 'Rarity': 'Common'},
    ]
    
    item_to_remove = [{'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common'}]
    item_to_add = [{'Name': 'C', 'Playstyles': ['cc'], 'Rarity': 'Common'}]
    
    # Style changes
    delta = compute_score_delta(pool, item_to_remove, item_to_add, style='frenzy')
    assert delta == -1.0, "Removing frenzy item should decrease score by 1"
    
    delta = compute_score_delta(pool, item_to_remove, item_to_add, style='cc')
    assert delta == 1.0, "Adding cc item should increase score by 1"


def test_score_breakdown():
    """Test score breakdown function."""
    pool = [
        {'Name': 'A', 'Playstyles': ['frenzy'], 'Rarity': 'Common'},
        {'Name': 'B', 'Playstyles': ['frenzy'], 'Rarity': 'Common'},
    ]
    
    graph = {
        'A': {'B': 1},
        'B': {'A': 1}
    }
    
    breakdown = score_breakdown(pool, graph, 'frenzy', synergy_weight=2.0)
    
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
