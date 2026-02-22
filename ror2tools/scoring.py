"""
Scoring functions for evaluating Risk of Rain 2 item pools.

This module contains all logic for computing pool scores based on:
- Playstyle matches
- Synergy graph edges (shared tags between items)
- Weighted combinations of the above
"""

from typing import List, Dict, Optional


def score_pool(
    pool: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0
) -> float:
    """
    Compute a numeric score for an item pool.
    
    Args:
        pool: List of item dictionaries, each with 'Name', 'Playstyles', etc.
        graph: Synergy adjacency map {item_name: {other_name: edge_weight}}
        style: Preferred playstyle (e.g., 'frenzy', 'cc', 'mobile')
        synergy_weight: Multiplier for synergy component of score
    
    Returns:
        Total score (higher is better)
    
    Score components:
        1. Style matches: +1 for each item matching the preferred style
        2. Pairwise synergy: sum of edge weights between all item pairs,
           multiplied by synergy_weight
    """
    score = 0.0
    
    # Component 1: Count items matching preferred style
    if style:
        for item in pool:
            if style in item.get('Playstyles', []):
                score += 1.0
    
    # Component 2: Sum pairwise synergy from graph
    if graph and synergy_weight:
        synergy_score = 0.0
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                name_a = pool[i]['Name']
                name_b = pool[j]['Name']
                # Synergy is symmetric, so check both directions
                synergy_score += graph.get(name_a, {}).get(name_b, 0)
                synergy_score += graph.get(name_b, {}).get(name_a, 0)
        score += synergy_score * synergy_weight
    
    return score


def compute_score_delta(
    pool: List[Dict],
    items_to_remove: List[Dict],
    items_to_add: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0
) -> float:
    """
    Efficiently compute score change from a swap without recomputing full score.
    
    This is much faster than calling score_pool twice, especially for large pools.
    
    Args:
        pool: Current pool
        items_to_remove: Items being removed from pool
        items_to_add: Items being added to pool
        graph: Synergy graph
        style: Preferred playstyle
        synergy_weight: Synergy multiplier
    
    Returns:
        Delta score (positive means improvement)
    """
    delta = 0.0
    
    # Style delta
    if style:
        for item in items_to_add:
            if style in item.get('Playstyles', []):
                delta += 1.0
        for item in items_to_remove:
            if style in item.get('Playstyles', []):
                delta -= 1.0
    
    # Synergy delta: only consider edges touching swapped items
    if graph and synergy_weight:
        remove_names = {item['Name'] for item in items_to_remove}
        
        # Compute synergy contribution of added items
        for item_in in items_to_add:
            name_in = item_in['Name']
            for other in pool:
                if other['Name'] not in remove_names:
                    delta += graph.get(name_in, {}).get(other['Name'], 0) * synergy_weight
                    delta += graph.get(other['Name'], {}).get(name_in, 0) * synergy_weight
        
        # Subtract synergy contribution of removed items
        for item_out in items_to_remove:
            name_out = item_out['Name']
            for other in pool:
                if other['Name'] not in remove_names:
                    delta -= graph.get(name_out, {}).get(other['Name'], 0) * synergy_weight
                    delta -= graph.get(other['Name'], {}).get(name_out, 0) * synergy_weight
    
    return delta


def score_breakdown(
    pool: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0
) -> Dict[str, float]:
    """
    Return detailed score breakdown for analysis/display.
    
    Returns:
        Dictionary with keys:
            - 'style_score': Points from style matches
            - 'synergy_score': Points from graph edges (before weight)
            - 'weighted_synergy': Synergy score after applying weight
            - 'total': Total score
    """
    breakdown = {
        'style_score': 0.0,
        'synergy_score': 0.0,
        'weighted_synergy': 0.0,
        'total': 0.0
    }
    
    # Style component
    if style:
        for item in pool:
            if style in item.get('Playstyles', []):
                breakdown['style_score'] += 1.0
    
    # Synergy component
    if graph:
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                name_a = pool[i]['Name']
                name_b = pool[j]['Name']
                breakdown['synergy_score'] += graph.get(name_a, {}).get(name_b, 0)
                breakdown['synergy_score'] += graph.get(name_b, {}).get(name_a, 0)
        breakdown['weighted_synergy'] = breakdown['synergy_score'] * synergy_weight
    
    breakdown['total'] = breakdown['style_score'] + breakdown['weighted_synergy']
    return breakdown
