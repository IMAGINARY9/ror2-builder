"""
Scoring functions for evaluating Risk of Rain 2 item pools.

This module contains all logic for computing pool scores based on:
- Playstyle matches
- Synergy graph edges (shared tags between items)
- Rarity diversity
- Tag coverage
- Weighted combinations of the above
"""

from typing import List, Dict, Optional
from collections import Counter


def calculate_rarity_diversity(pool: List[Dict]) -> float:
    """
    Calculate diversity score based on rarity distribution.
    
    Rewards balanced distribution across rarities (Shannon entropy-like).
    
    Args:
        pool: List of item dictionaries with 'Rarity' field
    
    Returns:
        Diversity score (0-10 range typically, higher is better)
    """
    if not pool:
        return 0.0
    
    rarity_counts = Counter(item.get('Rarity', 'Common') for item in pool)
    total = len(pool)
    num_rarities = len(rarity_counts)
    
    if num_rarities <= 1:
        return 0.0
    
    # Shannon entropy (positive, higher = more diverse)
    import math
    entropy = 0.0
    for count in rarity_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    
    # Normalize by max entropy (log2 of number of rarities present)
    max_entropy = math.log2(num_rarities)
    normalized = entropy / max_entropy if max_entropy > 0 else 0.0
    
    # Scale to 0-10 range
    return normalized * 10.0


def calculate_category_balance(pool: List[Dict]) -> float:
    """
    Calculate balance score across item categories (Damage/Utility/Healing).
    
    Uses AGGRESSIVE penalties for imbalanced builds. A mono-category build
    should receive a score so negative that no amount of style synergy can
    make it preferable.
    
    Target distribution for 14-item pool:
    - Damage: 4-7 items (30-50%)
    - Utility: 4-7 items (30-50%)  
    - Healing: 2-4 items (14-28%)
    
    Args:
        pool: List of item dictionaries with 'Category' field
    
    Returns:
        Balance score (heavily negative for imbalanced, positive for balanced)
    """
    import math
    
    if not pool:
        return 0.0
    
    pool_size = len(pool)
    
    # Core gameplay categories
    CORE_CATEGORIES = {'Damage', 'Utility', 'Healing'}
    
    # Count items in each core category
    category_counts = {cat: 0 for cat in CORE_CATEGORIES}
    for item in pool:
        cats = item.get('Category', '')
        if isinstance(cats, str):
            cats = [c.strip() for c in cats.split(',') if c.strip()]
        for cat in cats:
            if cat in CORE_CATEGORIES:
                category_counts[cat] += 1
    
    total = sum(category_counts.values())
    if total == 0:
        return 0.0
    
    damage_count = category_counts.get('Damage', 0)
    utility_count = category_counts.get('Utility', 0)
    healing_count = category_counts.get('Healing', 0)
    
    # =================================================================
    # STRICT REQUIREMENTS - These are HARD rules for playability
    # =================================================================
    
    # Minimum requirements (stricter than before)
    # For 14-item pool: need at least 3 damage, 3 utility, 2 healing
    min_damage = max(3, pool_size * 3 // 10)   # At least 30%
    min_utility = max(3, pool_size * 3 // 10)  # At least 30%
    min_healing = max(2, pool_size // 7)        # At least 14%
    
    # Maximum requirements (prevent over-concentration)
    max_damage = pool_size * 55 // 100    # Max 55%
    max_utility = pool_size * 55 // 100   # Max 55%
    max_healing = pool_size * 35 // 100   # Max 35%
    
    # Calculate deficits (below minimum)
    damage_deficit = max(0, min_damage - damage_count)
    utility_deficit = max(0, min_utility - utility_count)
    healing_deficit = max(0, min_healing - healing_count)
    
    # Calculate excess (above maximum)
    damage_excess = max(0, damage_count - max_damage)
    utility_excess = max(0, utility_count - max_utility)
    healing_excess = max(0, healing_count - max_healing)
    
    # =================================================================
    # PENALTY CALCULATIONS - Strong exponential penalties
    # =================================================================
    
    # Deficit penalty: each missing item from minimum costs exponentially more
    # Missing 1 = 4 pts, missing 2 = 16 pts, missing 3 = 36 pts
    deficit_penalty = (
        (damage_deficit ** 2) * 4 +
        (utility_deficit ** 2) * 4 +
        (healing_deficit ** 2) * 3
    )
    
    # Excess penalty: over-concentration is heavily punished
    # Each item above max costs 6 points (linear but steep)
    excess_penalty = (
        damage_excess * 6 +
        utility_excess * 6 +
        healing_excess * 8  # Healing over-concentration worst for RoR2
    )
    
    # Missing category penalty: if any category has 0 items
    categories_with_items = sum(1 for c in category_counts.values() if c > 0)
    if categories_with_items < 3:
        missing_category_penalty = (3 - categories_with_items) * 25
    else:
        missing_category_penalty = 0
    
    # =================================================================
    # BONUS: Reward good balance (Shannon entropy)
    # =================================================================
    proportions = [count / total for count in category_counts.values() if count > 0]
    entropy = 0.0
    for p in proportions:
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(3)
    # Scale entropy to 0-15 range (perfect balance = 15 points)
    entropy_bonus = (entropy / max_entropy) * 15 if max_entropy > 0 else 0
    
    # =================================================================
    # FINAL SCORE
    # =================================================================
    score = entropy_bonus - deficit_penalty - excess_penalty - missing_category_penalty
    
    return score


def calculate_tag_coverage(pool: List[Dict]) -> float:
    """
    Calculate unique tag coverage in the pool.
    
    Rewards variety of mechanical tags (damage, healing, on-kill, etc.).
    
    Args:
        pool: List of item dictionaries with 'SynergyTags' field
    
    Returns:
        Coverage score (number of unique tags)
    """
    if not pool:
        return 0.0
    
    unique_tags = set()
    for item in pool:
        tags_str = item.get('SynergyTags', '')
        if tags_str:
            # Handle both string and list formats
            if isinstance(tags_str, str):
                tags = [t.strip() for t in tags_str.split(',') if t.strip()]
            elif isinstance(tags_str, list):
                tags = tags_str
            else:
                tags = []
            unique_tags.update(tags)
    
    return float(len(unique_tags))


def score_pool(
    pool: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0,
    style_weight: float = 8.0,
    diversity_weight: float = 1.0,
    coverage_weight: float = 1.0,
    balance_weight: float = 5.0,
    pinned_items: Optional[List[str]] = None,
    pin_bonus: float = 2.0
) -> float:
    """
    Compute a numeric score for an item pool with enhanced scoring.
    
    Args:
        pool: List of item dictionaries, each with 'Name', 'Playstyles', etc.
        graph: Synergy adjacency map {item_name: {other_name: edge_weight}}
        style: Preferred playstyle (e.g., 'frenzy', 'cc', 'mobile')
        synergy_weight: Multiplier for synergy component of score
        style_weight: Multiplier for style matching (default 8.0 for strong preference)
        diversity_weight: Multiplier for rarity diversity (default 1.0)
        coverage_weight: Multiplier for tag coverage (default 1.0)
        balance_weight: Multiplier for category balance (default 5.0)
        pinned_items: List of pinned item names (core items)
        pin_bonus: Score bonus per pinned item (default 2.0)
    
    Returns:
        Total score (higher is better)
    
    Score components:
        1. Style matches: count * style_weight
        2. Pairwise synergy: sum of edges * synergy_weight
        3. Rarity diversity: entropy-based * diversity_weight
        4. Tag coverage: unique tags * coverage_weight
        5. Category balance: entropy across Damage/Utility/Healing * balance_weight
        6. Pinned items: count * pin_bonus
    """
    score = 0.0
    
    # Component 1: Count items matching preferred style (scaled up)
    if style and style_weight:
        style_score = 0.0
        for item in pool:
            playstyles = item.get('Playstyles', [])
            # Handle both list and string formats
            if isinstance(playstyles, str):
                playstyles = [s.strip() for s in playstyles.split(',') if s.strip()]
            if style in playstyles:
                style_score += 1.0
        score += style_score * style_weight
    
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
    
    # Component 3: Rarity diversity bonus
    if diversity_weight:
        diversity_score = calculate_rarity_diversity(pool)
        score += diversity_score * diversity_weight
    
    # Component 4: Tag coverage bonus
    if coverage_weight:
        coverage_score = calculate_tag_coverage(pool)
        score += coverage_score * coverage_weight
    
    # Component 5: Category balance bonus (Damage/Utility/Healing)
    if balance_weight:
        balance_score = calculate_category_balance(pool)
        score += balance_score * balance_weight
    
    # Component 6: Pinned items bonus (core build synergy)
    if pinned_items and pin_bonus:
        pinned_set = set(pinned_items)
        pin_score = sum(1.0 for item in pool if item.get('Name') in pinned_set)
        score += pin_score * pin_bonus
    
    return score


def compute_score_delta(
    pool: List[Dict],
    items_to_remove: List[Dict],
    items_to_add: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0,
    style_weight: float = 8.0,
    diversity_weight: float = 1.0,
    coverage_weight: float = 1.0,
    balance_weight: float = 5.0,
    pinned_items: Optional[List[str]] = None,
    pin_bonus: float = 2.0,
    pin_synergy_bonus: float = 1.5
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
        style_weight: Style matching multiplier
        diversity_weight: Diversity multiplier
        coverage_weight: Coverage multiplier
        balance_weight: Category balance multiplier
    
    Returns:
        Delta score (positive means improvement)
    """
    delta = 0.0
    
    # Style delta (scaled)
    if style and style_weight:
        style_delta = 0.0
        for item in items_to_add:
            playstyles = item.get('Playstyles', [])
            if isinstance(playstyles, str):
                playstyles = [s.strip() for s in playstyles.split(',') if s.strip()]
            if style in playstyles:
                style_delta += 1.0
        for item in items_to_remove:
            playstyles = item.get('Playstyles', [])
            if isinstance(playstyles, str):
                playstyles = [s.strip() for s in playstyles.split(',') if s.strip()]
            if style in playstyles:
                style_delta -= 1.0
        delta += style_delta * style_weight
    
    # Synergy delta: only consider edges touching swapped items
    if graph and synergy_weight:
        remove_names = {item['Name'] for item in items_to_remove}
        pinned_set = set(pinned_items) if pinned_items else set()
        
        # Compute synergy contribution of added items
        for item_in in items_to_add:
            name_in = item_in['Name']
            for other in pool:
                if other['Name'] not in remove_names:
                    base_syn = graph.get(name_in, {}).get(other['Name'], 0)
                    base_syn += graph.get(other['Name'], {}).get(name_in, 0)
                    delta += base_syn * synergy_weight
                    
                    # Extra bonus for synergy with PINNED items
                    if other['Name'] in pinned_set and base_syn > 0:
                        delta += base_syn * pin_synergy_bonus
        
        # Subtract synergy contribution of removed items
        for item_out in items_to_remove:
            name_out = item_out['Name']
            for other in pool:
                if other['Name'] not in remove_names:
                    base_syn = graph.get(name_out, {}).get(other['Name'], 0)
                    base_syn += graph.get(other['Name'], {}).get(name_out, 0)
                    delta -= base_syn * synergy_weight
                    
                    # Subtract extra bonus if removing synergy with pinned items
                    if other['Name'] in pinned_set and base_syn > 0:
                        delta -= base_syn * pin_synergy_bonus
    else:
        remove_names = {item['Name'] for item in items_to_remove}
    
    # Diversity and coverage deltas: recompute for simplicity (still fast)
    if diversity_weight or coverage_weight or balance_weight:
        # Create hypothetical new pool
        new_pool = [item for item in pool if item['Name'] not in remove_names]
        new_pool.extend(items_to_add)
        
        if diversity_weight:
            old_diversity = calculate_rarity_diversity(pool)
            new_diversity = calculate_rarity_diversity(new_pool)
            delta += (new_diversity - old_diversity) * diversity_weight
        
        if coverage_weight:
            old_coverage = calculate_tag_coverage(pool)
            new_coverage = calculate_tag_coverage(new_pool)
            delta += (new_coverage - old_coverage) * coverage_weight
        
        if balance_weight:
            old_balance = calculate_category_balance(pool)
            new_balance = calculate_category_balance(new_pool)
            delta += (new_balance - old_balance) * balance_weight
    
    # Pinned item bonus delta
    if pinned_items and pin_bonus:
        pinned_set = set(pinned_items)
        pin_delta = 0.0
        for item in items_to_add:
            if item.get('Name') in pinned_set:
                pin_delta += pin_bonus
        for item in items_to_remove:
            if item.get('Name') in pinned_set:
                pin_delta -= pin_bonus
        delta += pin_delta
    
    return delta


def score_breakdown(
    pool: List[Dict],
    graph: Optional[Dict[str, Dict[str, int]]] = None,
    style: Optional[str] = None,
    synergy_weight: float = 0,
    style_weight: float = 8.0,
    diversity_weight: float = 1.0,
    coverage_weight: float = 1.0,
    balance_weight: float = 5.0,
    pinned_items: Optional[List[str]] = None,
    pin_bonus: float = 2.0
) -> Dict[str, float]:
    """
    Return detailed score breakdown for analysis/display.
    
    Returns:
        Dictionary with keys:
            - 'style_score': Points from style matches (raw count)
            - 'weighted_style': Style score after applying weight
            - 'synergy_score': Points from graph edges (before weight)
            - 'weighted_synergy': Synergy score after applying weight
            - 'diversity_score': Rarity diversity score (raw)
            - 'weighted_diversity': Diversity after applying weight
            - 'coverage_score': Tag coverage score (raw)
            - 'weighted_coverage': Coverage after applying weight
            - 'pin_score': Number of pinned items (raw count)
            - 'weighted_pin': Pin score after applying weight
            - 'total': Total score
    """
    breakdown = {
        'style_score': 0.0,
        'weighted_style': 0.0,
        'synergy_score': 0.0,
        'weighted_synergy': 0.0,
        'diversity_score': 0.0,
        'weighted_diversity': 0.0,
        'coverage_score': 0.0,
        'weighted_coverage': 0.0,
        'balance_score': 0.0,
        'weighted_balance': 0.0,
        'pin_score': 0.0,
        'weighted_pin': 0.0,
        'total': 0.0
    }
    
    # Style component
    if style:
        for item in pool:
            playstyles = item.get('Playstyles', [])
            if isinstance(playstyles, str):
                playstyles = [s.strip() for s in playstyles.split(',') if s.strip()]
            if style in playstyles:
                breakdown['style_score'] += 1.0
        breakdown['weighted_style'] = breakdown['style_score'] * style_weight
    
    # Synergy component
    if graph:
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                name_a = pool[i]['Name']
                name_b = pool[j]['Name']
                breakdown['synergy_score'] += graph.get(name_a, {}).get(name_b, 0)
                breakdown['synergy_score'] += graph.get(name_b, {}).get(name_a, 0)
        breakdown['weighted_synergy'] = breakdown['synergy_score'] * synergy_weight
    
    # Diversity component
    breakdown['diversity_score'] = calculate_rarity_diversity(pool)
    breakdown['weighted_diversity'] = breakdown['diversity_score'] * diversity_weight
    
    # Coverage component
    breakdown['coverage_score'] = calculate_tag_coverage(pool)
    breakdown['weighted_coverage'] = breakdown['coverage_score'] * coverage_weight
    
    # Balance component (Damage/Utility/Healing)
    breakdown['balance_score'] = calculate_category_balance(pool)
    breakdown['weighted_balance'] = breakdown['balance_score'] * balance_weight
    
    # Pin component
    if pinned_items:
        pinned_set = set(pinned_items)
        breakdown['pin_score'] = sum(1.0 for item in pool if item.get('Name') in pinned_set)
        breakdown['weighted_pin'] = breakdown['pin_score'] * pin_bonus
    
    breakdown['total'] = (breakdown['weighted_style'] + 
                          breakdown['weighted_synergy'] +
                          breakdown['weighted_diversity'] +
                          breakdown['weighted_coverage'] +
                          breakdown['weighted_balance'] +
                          breakdown['weighted_pin'])
    return breakdown
