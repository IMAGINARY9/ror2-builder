"""
Example: Optimize an item pool for a specific playstyle.

This script demonstrates how to use the optimization system programmatically.
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ror2tools.generator import load_items, load_config
from ror2tools.optimizer import LocalSearchOptimizer
from ror2tools.history import OptimizationHistory


def example_basic_optimization():
    """Example 1: Basic batch optimization."""
    print("="*70)
    print("Example 1: Basic Batch Optimization")
    print("="*70)
    
    # Load items and config
    items = load_items()
    config = {
        'Common': 3,
        'Uncommon': 2,
        'Legendary': 1,
        'style': 'frenzy',
        'synergy_weight': 2.0
    }
    
    # Create optimizer
    optimizer = LocalSearchOptimizer(
        items=items,
        config=config,
        k_opt=1,
        max_iterations=50,
        convergence_threshold=5,
        random_seed=42  # For reproducibility
    )
    
    # Track history
    history = OptimizationHistory()
    
    # Progress callback
    def progress(state):
        if state.iteration % 10 == 0:
            print(f"Iteration {state.iteration}: score={state.score:.2f}, best={state.best_score:.2f}")
        history.record(state)
        return True
    
    # Run optimization
    print(f"\nOptimizing pool (style={config['style']}, synergy_weight={config['synergy_weight']})...")
    best_pool, final_state = optimizer.optimize(callback=progress)
    
    print(f"\n✓ Optimization complete!")
    print(f"  Initial score: {history.entries[0].score:.2f}")
    print(f"  Final score: {final_state.best_score:.2f}")
    print(f"  Improvement: {final_state.best_score - history.entries[0].score:+.2f}")
    print(f"  Iterations: {final_state.iteration + 1}")
    
    print(f"\nBest pool ({len(best_pool)} items):")
    for item in best_pool:
        print(f"  [{item['Rarity'][0]}] {item['Name']}")
    
    return best_pool, history


def example_simulated_annealing():
    """Example 2: Optimization with simulated annealing."""
    print("\n\n")
    print("="*70)
    print("Example 2: Simulated Annealing")
    print("="*70)
    
    items = load_items()
    config = {
        'Common': 4,
        'Uncommon': 3,
        'Legendary': 2,
        'style': 'cc',
        'synergy_weight': 3.0
    }
    
    # Optimizer with annealing
    optimizer = LocalSearchOptimizer(
        items=items,
        config=config,
        k_opt=1,
        max_iterations=100,
        convergence_threshold=15,
        use_simulated_annealing=True,
        temperature_initial=2.0,
        temperature_decay=0.95,
        random_seed=42
    )
    
    history = OptimizationHistory()
    
    def progress(state):
        if state.iteration % 20 == 0:
            print(f"Iteration {state.iteration}: score={state.score:.2f}, "
                  f"temp={optimizer.temperature:.3f}")
        history.record(state)
        return True
    
    print(f"\nOptimizing with simulated annealing...")
    print(f"  Initial temperature: {optimizer.temperature:.2f}")
    print(f"  Decay rate: {optimizer.temperature_decay:.2f}")
    
    best_pool, final_state = optimizer.optimize(callback=progress)
    
    print(f"\n✓ Annealing complete!")
    print(f"  Best score: {final_state.best_score:.2f}")
    print(f"  Final temperature: {optimizer.temperature:.4f}")
    
    return best_pool, history


def example_comparison():
    """Example 3: Compare random vs optimized pools."""
    print("\n\n")
    print("="*70)
    print("Example 3: Random vs Optimized Comparison")
    print("="*70)
    
    items = load_items()
    config = {
        'Common': 3,
        'Uncommon': 2,
        'Legendary': 1,
        'style': 'mobile',
        'synergy_weight': 2.5
    }
    
    # Create optimizer
    optimizer = LocalSearchOptimizer(items, config, k_opt=1, max_iterations=30, random_seed=42)
    
    # Generate initial random pool
    initial_pool = optimizer._generate_initial_pool()
    initial_score = optimizer._evaluate_swaps(initial_pool, [])  # Just get score
    from ror2tools.scoring import score_pool
    from ror2tools.utils import load_synergy_graph
    
    graph = load_synergy_graph()
    initial_score = score_pool(initial_pool, graph, config['style'], config['synergy_weight'])
    
    print(f"\nRandom pool score: {initial_score:.2f}")
    print("Items:")
    for item in initial_pool:
        plays = ', '.join(item.get('Playstyles', []))
        print(f"  [{item['Rarity'][0]}] {item['Name']:<30} ({plays})")
    
    # Optimize from that initial pool
    print(f"\nOptimizing...")
    best_pool, final_state = optimizer.optimize(initial_pool=initial_pool)
    
    improvement = final_state.best_score - initial_score
    improvement_pct = (improvement / initial_score * 100) if initial_score > 0 else 0
    
    print(f"\n✓ Optimized pool score: {final_state.best_score:.2f}")
    print(f"  Improvement: {improvement:+.2f} ({improvement_pct:+.1f}%)")
    print(f"  Iterations: {final_state.iteration + 1}")
    
    if improvement > 0:
        print("\nOptimized items:")
        for item in best_pool:
            plays = ', '.join(item.get('Playstyles', []))
            print(f"  [{item['Rarity'][0]}] {item['Name']:<30} ({plays})")


def example_export_results():
    """Example 4: Export optimization results."""
    print("\n\n")
    print("="*70)
    print("Example 4: Export Results")
    print("="*70)
    
    items = load_items()
    config = {
        'Common': 3,
        'Uncommon': 2,
        'style': 'frenzy',
        'synergy_weight': 2.0
    }
    
    optimizer = LocalSearchOptimizer(items, config, k_opt=1, max_iterations=25, random_seed=42)
    history = OptimizationHistory()
    
    best_pool, final_state = optimizer.optimize(callback=lambda s: (history.record(s), True)[1])
    
    # Export history
    history.export_json('output/example_optimization_history.json')
    print(f"\n✓ Exported history to output/example_optimization_history.json")
    
    # Export pool
    from ror2tools.generator import export_pool_files
    export_pool_files(best_pool, final_state.best_score)
    print(f"✓ Exported pool to output/generated_pool.csv and .md")
    
    # Try to generate visualization
    try:
        history.plot('output/example_optimization_plot.png', title='Example Optimization')
        print(f"✓ Generated plot at output/example_optimization_plot.png")
    except ImportError:
        print(f"⚠ Skipping plot (matplotlib not installed)")
    
    # Show summary
    summary = history.get_summary()
    print(f"\nSummary:")
    print(f"  Total iterations: {summary['total_iterations']}")
    print(f"  Initial score: {summary['initial_score']:.2f}")
    print(f"  Final score: {summary['final_score']:.2f}")
    print(f"  Best score: {summary['best_score']:.2f}")
    print(f"  Total improvement: {summary['total_improvement']:+.2f}")
    print(f"  Successful swaps: {summary['successful_swaps']}")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("Risk of Rain 2 Pool Optimization Examples")
    print("="*70)
    
    # Check if data exists
    if not os.path.exists('data/items.csv'):
        print("\n⚠ Error: data/items.csv not found!")
        print("Please run 'python main.py export' first to download item data.")
        sys.exit(1)
    
    try:
        # Run examples
        example_basic_optimization()
        example_simulated_annealing()
        example_comparison()
        example_export_results()
        
        print("\n\n" + "="*70)
        print("All examples completed successfully!")
        print("="*70)
        
    except Exception as e:
        print(f"\n⚠ Error running examples: {e}")
        import traceback
        traceback.print_exc()
