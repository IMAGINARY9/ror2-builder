"""
Interactive command-line interface for pool optimization.

Allows users to observe each iteration and manually intervene.
"""

import copy
from typing import List, Dict, Optional

from .scoring import score_pool, score_breakdown


class InteractiveCLI:
    """
    Interactive interface for optimization runs.
    
    Pauses after each iteration, displays state, and accepts user commands.
    """
    
    def __init__(self, optimizer, history, config):
        """
        Initialize interactive CLI.
        
        Args:
            optimizer: LocalSearchOptimizer instance
            history: OptimizationHistory instance
            config: Configuration dictionary
        """
        self.optimizer = optimizer
        self.history = history
        self.config = config
        self.state = None
        self.should_stop = False
        self.auto_run = 0  # Number of iterations to run automatically
    
    def _display_state(self):
        """Display current optimization state."""
        if not self.state:
            return
        
        print("\n" + "="*70)
        print(f"Iteration {self.state.iteration}/{self.optimizer.max_iterations} │ "
              f"Score: {self.state.score:.2f} │ Best: {self.state.best_score:.2f}")
        print(f"Convergence: {self.state.stale_iterations}/{self.optimizer.convergence_threshold} "
              f"stale iterations")
        print("="*70)
        
        # Show last swap
        if self.state.last_swap:
            removed = [item['Name'] for item in self.state.last_swap.remove]
            added = [item['Name'] for item in self.state.last_swap.add]
            print(f"\n→ Last Swap (Δ={self.state.last_swap.delta:+.2f}):")
            print(f"  Removed: {', '.join(removed)}")
            print(f"  Added:   {', '.join(added)}")
        else:
            print("\n→ No improvement found in last iteration")
        
        # Show current pool
        print(f"\nCurrent Pool ({len(self.state.pool)} items):")
        by_rarity = {}
        for item in self.state.pool:
            rarity = item['Rarity']
            if rarity not in by_rarity:
                by_rarity[rarity] = []
            by_rarity[rarity].append(item)
        
        for rarity, items in sorted(by_rarity.items()):
            print(f"\n  [{rarity}] ({len(items)} items):")
            for item in sorted(items, key=lambda x: x['Name']):
                tags = item.get('SynergyTags', [])[:3]  # Show first 3 tags
                plays = item.get('Playstyles', [])
                tag_str = ', '.join(tags)
                play_str = f" ({', '.join(plays)})" if plays else ""
                print(f"    • {item['Name']:<30} {tag_str}{play_str}")
    
    def _display_help(self):
        """Display available commands."""
        print("\n" + "-"*70)
        print("Commands:")
        print("  [c]ontinue        - Run next iteration")
        print("  [r]un N           - Run N iterations without pausing")
        print("  [s]wap X → Y      - Manually swap item X with item Y")
        print("  [v]iew stats      - Show detailed scoring breakdown")
        print("  [p]ool            - Show current pool again")
        print("  [b]est            - Show best pool found so far")
        print("  [e]xport          - Save current pool")
        print("  [h]elp            - Show this help")
        print("  [q]uit            - Stop optimization")
        print("-"*70)
    
    def _display_breakdown(self):
        """Display detailed score breakdown."""
        breakdown = score_breakdown(
            self.state.pool,
            self.optimizer.graph,
            self.optimizer.style,
            self.optimizer.synergy_weight
        )
        
        print("\n" + "-"*70)
        print("Score Breakdown:")
        print(f"  Style matches:     {breakdown['style_score']:.2f}")
        print(f"  Synergy (raw):     {breakdown['synergy_score']:.2f}")
        print(f"  Synergy (weighted): {breakdown['weighted_synergy']:.2f}")
        print(f"  TOTAL:             {breakdown['total']:.2f}")
        print("-"*70)
    
    def _show_best_pool(self):
        """Display best pool found so far."""
        print("\n" + "="*70)
        print(f"Best Pool (Score: {self.state.best_score:.2f}):")
        print("="*70)
        
        by_rarity = {}
        for item in self.state.best_pool:
            rarity = item['Rarity']
            if rarity not in by_rarity:
                by_rarity[rarity] = []
            by_rarity[rarity].append(item)
        
        for rarity, items in sorted(by_rarity.items()):
            print(f"\n  [{rarity}] ({len(items)} items):")
            for item in sorted(items, key=lambda x: x['Name']):
                print(f"    • {item['Name']}")
    
    def _handle_swap_command(self, args: str) -> bool:
        """
        Handle manual swap command.
        
        Args:
            args: Command arguments (e.g., "Crowbar → Syringe")
        
        Returns:
            True if swap was successful
        """
        # Parse swap command
        parts = args.split('→')
        if len(parts) != 2:
            parts = args.split('->')
        if len(parts) != 2:
            print("Error: Invalid swap format. Use: swap X → Y")
            return False
        
        item_remove_name = parts[0].strip()
        item_add_name = parts[1].strip()
        
        # Find items in pool and available
        pool_names = {item['Name'] for item in self.state.pool}
        
        # Find item to remove
        item_to_remove = None
        for item in self.state.pool:
            if item['Name'].lower() == item_remove_name.lower():
                item_to_remove = item
                break
        
        if not item_to_remove:
            print(f"Error: Item '{item_remove_name}' not found in current pool")
            return False
        
        # Find item to add
        item_to_add = None
        for item in self.optimizer.items:
            if item['Name'] not in pool_names and item['Name'].lower() == item_add_name.lower():
                item_to_add = item
                break
        
        if not item_to_add:
            print(f"Error: Item '{item_add_name}' not available (not in database or already in pool)")
            return False
        
        # Check rarity match
        if item_to_remove['Rarity'] != item_to_add['Rarity']:
            print(f"Error: Rarity mismatch. {item_remove_name} is {item_to_remove['Rarity']}, "
                  f"but {item_add_name} is {item_to_add['Rarity']}")
            print("Manual swaps must preserve rarity counts.")
            return False
        
        # Compute score delta
        from .scoring import compute_score_delta
        delta = compute_score_delta(
            self.state.pool,
            [item_to_remove],
            [item_to_add],
            self.optimizer.graph,
            self.optimizer.style,
            self.optimizer.synergy_weight,
            # propagate pinned configuration for correctness
            pinned_items=list(self.optimizer.pinned_items),
            pin_synergy_bonus=self.optimizer.pin_synergy_bonus
        )
        
        # Apply swap
        self.state.pool = [item for item in self.state.pool if item['Name'] != item_remove_name]
        self.state.pool.append(item_to_add)
        self.state.score += delta
        
        # Update best if needed
        if self.state.score > self.state.best_score:
            self.state.best_score = self.state.score
            self.state.best_pool = copy.deepcopy(self.state.pool)
            print(f"✓ New best score: {self.state.best_score:.2f}")
        
        # Record in history
        self.history.record_manual(
            self.state.iteration,
            self.state.score,
            self.state.best_score,
            [item_remove_name],
            [item_add_name],
            delta
        )
        
        print(f"✓ Swapped {item_remove_name} → {item_add_name} (Δ={delta:+.2f})")
        print(f"  New score: {self.state.score:.2f}")
        
        return True
    
    def _export_current(self):
        """Export current pool."""
        from .generator import export_pool_files
        export_pool_files(self.state.pool, self.state.score)
        print("✓ Exported current pool to output/generated_pool.csv and .md")
    
    def _get_command(self) -> str:
        """Get command from user."""
        self._display_help()
        try:
            cmd = input("\n> ").strip().lower()
            return cmd
        except (EOFError, KeyboardInterrupt):
            return 'q'
    
    def _callback(self, state) -> bool:
        """
        Callback for optimizer (called after each iteration).
        
        Returns:
            True to continue, False to stop
        """
        self.state = state
        self.history.record(state)
        
        # If auto-running, decrement counter and continue
        if self.auto_run > 0:
            self.auto_run -= 1
            if state.iteration % 5 == 0:
                print(f"  Iteration {state.iteration}: score={state.score:.2f}, best={state.best_score:.2f}")
            return True
        
        # Display state and prompt for command
        self._display_state()
        
        while True:
            cmd = self._get_command()
            
            if cmd in ('c', 'continue', ''):
                return True
            
            elif cmd.startswith('r'):
                # Run N iterations
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    self.auto_run = int(parts[1]) - 1  # -1 because we'll continue once now
                    print(f"Running {int(parts[1])} iterations...")
                    return True
                else:
                    print("Error: Use 'run N' where N is a number")
            
            elif cmd.startswith('s'):
                # Manual swap
                args = cmd[1:].strip()
                if not args:
                    item_from = input("Item to remove: ").strip()
                    item_to = input("Item to add: ").strip()
                    args = f"{item_from} → {item_to}"
                self._handle_swap_command(args)
                self._display_state()
            
            elif cmd in ('v', 'view'):
                self._display_breakdown()
            
            elif cmd in ('p', 'pool'):
                self._display_state()
            
            elif cmd in ('b', 'best'):
                self._show_best_pool()
            
            elif cmd in ('e', 'export'):
                self._export_current()
            
            elif cmd in ('h', 'help'):
                continue  # Help is shown by default
            
            elif cmd in ('q', 'quit', 'exit'):
                print("Stopping optimization...")
                return False
            
            else:
                print(f"Unknown command: {cmd}")
    
    def run(self) -> List[Dict]:
        """
        Run interactive optimization session.
        
        Returns:
            Best pool found
        """
        print("\n" + "="*70)
        print("Interactive Pool Optimization")
        print("="*70)
        print(f"Configuration: {self.config}")
        print(f"K-opt: {self.optimizer.k_opt}, Max iterations: {self.optimizer.max_iterations}")
        print(f"Convergence threshold: {self.optimizer.convergence_threshold}")
        print("\nStarting optimization... (press Ctrl+C to stop)")
        
        # Run optimization with interactive callback
        best_pool, final_state = self.optimizer.optimize(callback=self._callback)
        
        print("\n" + "="*70)
        print("Optimization Complete!")
        print("="*70)
        print(f"Best score: {final_state.best_score:.2f}")
        print(f"Total iterations: {final_state.iteration + 1}")
        print(f"Manual interventions: {sum(1 for e in self.history.entries if e.manual)}")
        
        self.state = final_state
        self._show_best_pool()
        
        return best_pool
