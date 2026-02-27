import argparse

from ror2tools import export_items, generate_pool


def main():
    parser = argparse.ArgumentParser(description='Risk of Rain 2 toolset')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('export', help='Export item data from the wiki')
    sub.add_parser('generate', help='Generate a random item pool (uses data/config.json) - simple mode')
    
    build = sub.add_parser('build', help='Build a scored pool (style/size/synergy options)')
    build.add_argument('--style', help='Preferred playstyle to include')
    build.add_argument('--size', type=int, help='Number of items in pool')
    build.add_argument('--synergy-weight', type=float, default=0, help='Weight of synergy graph when scoring')
    
    optimize = sub.add_parser('optimize', help='Optimize pool using local search')
    optimize.add_argument('--config', help='Path to config file (default: data/config.json)')
    optimize.add_argument('--interactive', action='store_true', help='Enable interactive mode')
    optimize.add_argument('--max-iterations', type=int, help='Maximum optimization iterations')
    optimize.add_argument('--k-opt', type=int, help='Number of items to swap simultaneously (1 or 2)')
    optimize.add_argument('--convergence', type=int, help='Stop after N stale iterations')
    optimize.add_argument('--visualize', action='store_true', help='Generate score plot after completion')
    optimize.add_argument('--seed', type=int, help='Random seed for reproducibility')
    
    desc = sub.add_parser('describe', help='Show description and tips for an item')
    desc.add_argument('item', help='Name of the item to describe')
    args = parser.parse_args()

    if args.command == 'export':
        export_items()
    elif args.command == 'generate':
        generate_pool()
    elif args.command == 'build':
        from ror2tools.generator import load_config
        cfg = load_config()
        if args.style:
            cfg['style'] = args.style
        if args.size is not None:
            cfg['size'] = args.size
        if args.synergy_weight:
            cfg['synergy_weight'] = args.synergy_weight
        generate_pool(cfg)
    elif args.command == 'optimize':
        from ror2tools.generator import load_config, load_items
        from ror2tools.optimizer import LocalSearchOptimizer
        from ror2tools.history import OptimizationHistory
        import os
        
        # Load configuration
        config_path = args.config or os.path.join('data', 'config.json')
        config = load_config(config_path)
        
        # Override with command-line args
        opt_config = config.get('optimization', {})
        if args.max_iterations:
            opt_config['max_iterations'] = args.max_iterations
        if args.k_opt:
            opt_config['k_opt'] = args.k_opt
        if args.convergence:
            opt_config['convergence_threshold'] = args.convergence
        
        # Load items
        items = load_items()
        
        # Create optimizer
        optimizer = LocalSearchOptimizer(
            items=items,
            config=config,
            k_opt=opt_config.get('k_opt', 1),
            max_iterations=opt_config.get('max_iterations', 100),
            convergence_threshold=opt_config.get('convergence_threshold', 10),
            use_simulated_annealing=opt_config.get('use_simulated_annealing', False),
            temperature_initial=opt_config.get('temperature_initial', 1.0),
            temperature_decay=opt_config.get('temperature_decay', 0.95),
            tabu_tenure=opt_config.get('tabu_tenure', None),
            random_seed=args.seed
        )
        
        # Create history tracker
        history = OptimizationHistory()
        
        # Run optimization
        if args.interactive:
            from ror2tools.interactive import InteractiveCLI
            cli = InteractiveCLI(optimizer, history, config)
            best_pool = cli.run()
        else:
            # Batch mode with progress callback
            def progress_callback(state):
                if state.iteration % 10 == 0 or state.last_swap:
                    print(f"Iteration {state.iteration}: score={state.score:.2f}, "
                          f"best={state.best_score:.2f}, stale={state.stale_iterations}")
                    if state.last_swap:
                        print(f"  → {state.last_swap}")
                history.record(state)
                return True
            
            print(f"Running optimization (max {optimizer.max_iterations} iterations, "
                  f"k={optimizer.k_opt}, convergence={optimizer.convergence_threshold})...")
            best_pool, final_state = optimizer.optimize(callback=progress_callback)
            print(f"\nOptimization complete!")
            print(f"Final score: {final_state.best_score:.2f}")
            print(f"Iterations: {final_state.iteration + 1}")
        
        # Export results
        history.export_json('output/optimization_history.json')
        
        if args.visualize:
            history.plot('output/optimization_history.png')
            print("Saved optimization plot to output/optimization_history.png")
        
        # Export pool using existing generator function
        from ror2tools.generator import export_pool_files
        export_pool_files(best_pool, final_state.best_score)
        print("Saved optimized pool to output/generated_pool.csv and .md")
        
    elif args.command == 'describe':
        from ror2tools.utils import fetch_item_description, fetch_wiki_tips
        desc_text = fetch_item_description(args.item)
        tips_text = fetch_wiki_tips(args.item)
        print(f"{args.item}\n\nDescription:\n{desc_text}\n\nTips:\n{tips_text}")


if __name__ == '__main__':
    main()
