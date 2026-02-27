#!/usr/bin/env python3
"""Test balanced builds with new scoring system."""

from ror2tools.generator import load_items, load_config
from ror2tools.optimizer import LocalSearchOptimizer
from ror2tools.utils import load_synergy_graph
from ror2tools.scoring import score_breakdown

config = load_config()
all_items = load_items()
synergy_graph = load_synergy_graph()

results = {}

# Test all playstyles with balance penalty
for style in ['cc', 'frenzy', 'mobile', 'proc', 'regen', 'tank']:
    print(f"=== {style.upper()} ===")
    
    cfg = config.copy()
    cfg['style'] = style
    cfg['synergy_weight'] = 0.5
    cfg['style_weight'] = 8.0
    cfg['balance_weight'] = 5.0
    
    opt = LocalSearchOptimizer(
        items=all_items,
        config=cfg,
        max_iterations=50,
        use_simulated_annealing=True,
        random_seed=42,
    )
    
    pool = opt._generate_initial_pool()
    optimized, state = opt.optimize(pool)
    
    # Analyze category balance
    cat_counts = {'Damage': 0, 'Utility': 0, 'Healing': 0}
    for item in optimized:
        cats = item.get('Category', '')
        if isinstance(cats, str):
            cats = [c.strip() for c in cats.split(',') if c.strip()]
        for cat in cats:
            if cat in cat_counts:
                cat_counts[cat] += 1
    
    # Count style-matching items
    style_items = [i for i in optimized if style in i.get('Playstyles', [])]
    results[style] = set(i['Name'] for i in optimized)
    
    breakdown = score_breakdown(optimized, synergy_graph, style,
                                synergy_weight=0.5, style_weight=8.0, balance_weight=5.0)
    
    print(f"Style match: {len(style_items)}/{len(optimized)}")
    print(f"Categories: Damage={cat_counts['Damage']}, Utility={cat_counts['Utility']}, Healing={cat_counts['Healing']}")
    print(f"Balance score: {breakdown.get('balance_score', 0):.1f}")
    print()

print("=== BALANCE COMPARISON ===")
for style in results:
    print(f"{style}: {len(results[style])} items")
