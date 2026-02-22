"""
History tracking and visualization for optimization runs.

Tracks score progression, swaps, and manual interventions across iterations.
"""

import json
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class HistoryEntry:
    """Single iteration record."""
    iteration: int
    score: float
    best_score: float
    swap_from: Optional[List[str]] = None  # Item names removed
    swap_to: Optional[List[str]] = None    # Item names added
    manual: bool = False                    # Was this a manual intervention?
    delta: float = 0.0                     # Score change
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON export."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class OptimizationHistory:
    """
    Tracks the history of an optimization run.
    
    Records score, swaps, and events for each iteration.
    Can export to JSON and generate visualizations.
    """
    
    def __init__(self):
        self.entries: List[HistoryEntry] = []
    
    def record(self, state, manual: bool = False):
        """
        Record an optimization state.
        
        Args:
            state: OptimizationState object from optimizer
            manual: Whether this was a manual intervention
        """
        swap_from = None
        swap_to = None
        delta = 0.0
        
        if state.last_swap:
            swap_from = [item['Name'] for item in state.last_swap.remove]
            swap_to = [item['Name'] for item in state.last_swap.add]
            delta = state.last_swap.delta
        
        entry = HistoryEntry(
            iteration=state.iteration,
            score=state.score,
            best_score=state.best_score,
            swap_from=swap_from,
            swap_to=swap_to,
            manual=manual,
            delta=delta
        )
        
        self.entries.append(entry)
    
    def record_manual(
        self,
        iteration: int,
        score: float,
        best_score: float,
        swap_from: List[str],
        swap_to: List[str],
        delta: float
    ):
        """Record a manual intervention."""
        entry = HistoryEntry(
            iteration=iteration,
            score=score,
            best_score=best_score,
            swap_from=swap_from,
            swap_to=swap_to,
            manual=True,
            delta=delta
        )
        self.entries.append(entry)
    
    def export_json(self, path: str):
        """
        Export history to JSON file.
        
        Args:
            path: Output file path
        """
        data = {
            'entries': [entry.to_dict() for entry in self.entries],
            'summary': {
                'total_iterations': len(self.entries),
                'initial_score': self.entries[0].score if self.entries else 0,
                'final_score': self.entries[-1].score if self.entries else 0,
                'best_score': max((e.best_score for e in self.entries), default=0),
                'manual_interventions': sum(1 for e in self.entries if e.manual),
                'total_improvement': (self.entries[-1].score - self.entries[0].score) if self.entries else 0
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def plot(self, path: str, title: str = "Optimization Progress"):
        """
        Generate a line plot of score over iterations.
        
        Args:
            path: Output image path (e.g., 'output.png')
            title: Plot title
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("Warning: matplotlib not installed, skipping visualization")
            return
        
        if not self.entries:
            print("Warning: No history to plot")
            return
        
        # Extract data
        iterations = [e.iteration for e in self.entries]
        scores = [e.score for e in self.entries]
        best_scores = [e.best_score for e in self.entries]
        manual_iters = [e.iteration for e in self.entries if e.manual]
        manual_scores = [e.score for e in self.entries if e.manual]
        
        # Create plot
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Plot score progression
        ax.plot(iterations, scores, label='Current Score', color='blue', linewidth=2, alpha=0.7)
        ax.plot(iterations, best_scores, label='Best Score', color='green', linewidth=2, linestyle='--')
        
        # Mark manual interventions
        if manual_iters:
            ax.scatter(manual_iters, manual_scores, color='red', s=100, 
                      label='Manual Intervention', zorder=5, marker='*')
        
        # Styling
        ax.set_xlabel('Iteration', fontsize=12)
        ax.set_ylabel('Score', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        # Add summary stats as text
        if self.entries:
            initial = self.entries[0].score
            final = self.entries[-1].score
            best = max(best_scores)
            improvement = final - initial
            
            stats_text = (
                f"Initial: {initial:.2f}\n"
                f"Final: {final:.2f}\n"
                f"Best: {best:.2f}\n"
                f"Improvement: {improvement:+.2f}"
            )
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        if not self.entries:
            return {}
        
        return {
            'total_iterations': len(self.entries),
            'initial_score': self.entries[0].score,
            'final_score': self.entries[-1].score,
            'best_score': max(e.best_score for e in self.entries),
            'total_improvement': self.entries[-1].score - self.entries[0].score,
            'manual_interventions': sum(1 for e in self.entries if e.manual),
            'successful_swaps': sum(1 for e in self.entries if e.delta > 0)
        }
