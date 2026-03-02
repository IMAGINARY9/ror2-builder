"""
Flask web application for Risk of Rain 2 item pool optimization.

Provides a modern drag-and-drop interface for building and optimizing pools.
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import os
import json
import threading

from ror2tools.generator import load_items, load_config, clean_wiki_markup
from ror2tools.optimizer import LocalSearchOptimizer, TabuList
from ror2tools.scoring import score_pool, score_breakdown
from ror2tools.history import OptimizationHistory
from ror2tools.utils import load_synergy_graph


app = Flask(__name__)
app.config['SECRET_KEY'] = 'ror2-optimization-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Available DLCs with metadata
AVAILABLE_DLCS = {
    'Base': {'name': 'Base Game', 'icon': '🎮', 'color': '#4a9'},
    'SOTV': {'name': 'Survivors of the Void', 'icon': '🌀', 'color': '#a4f'},
    'SOTS': {'name': 'Seekers of the Storm', 'icon': '⛈️', 'color': '#4af'},
    'AC': {'name': 'Alloyed Collective', 'icon': '⚙️', 'color': '#fa4'},
}

# Global state
# thread-safe pool state
current_pool = []
pool_lock = threading.Lock()

current_config = {}
enabled_dlcs = {'Base', 'SOTV', 'SOTS', 'AC'}  # All DLCs enabled by default
optimizer = None
optimization_thread = None
history = OptimizationHistory()
all_items = []
synergy_graph = {}

# Per-session tabu list for the step-by-step /api/optimize/step endpoint.
# Cleared whenever a new pool is generated so the optimizer starts fresh.
step_tabu = TabuList()


def get_pool_copy():
    with pool_lock:
        return list(current_pool)


def set_pool(new_pool):
    global current_pool
    with pool_lock:
        current_pool = list(new_pool)


def get_scoring_params(config):
    """Extract scoring parameters from config dict."""
    return {
        'style': config.get('style'),
        'synergy_weight': config.get('synergy_weight', 0.5),
        'style_weight': config.get('style_weight', 8.0),
        'diversity_weight': config.get('diversity_weight', 1.0),
        'coverage_weight': config.get('coverage_weight', 1.0),
        'balance_weight': config.get('balance_weight', 5.0),
        'pinned_items': config.get('pinned_items', [])
    }


def initialize_data():
    """Load items and synergy graph on startup."""
    global all_items, synergy_graph, current_config
    try:
        all_items = load_items(enabled_dlcs=enabled_dlcs)
        synergy_graph = load_synergy_graph()
        current_config = load_config()
        print(f"✓ Loaded {len(all_items)} items (DLCs: {', '.join(enabled_dlcs)})")
        print(f"✓ Loaded synergy graph with {len(synergy_graph)} nodes")
    except Exception as e:
        print(f"⚠ Error loading data: {e}")
        all_items = []
        synergy_graph = {}
        current_config = {}


def reload_items_for_dlcs():
    """Reload items when DLC selection changes."""
    global all_items
    try:
        all_items = load_items(enabled_dlcs=enabled_dlcs)
        print(f"✓ Reloaded {len(all_items)} items (DLCs: {', '.join(enabled_dlcs)})")
        return True
    except Exception as e:
        print(f"⚠ Error reloading items: {e}")
        return False


@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')


@app.route('/api/items')
def get_items():
    """Get all available items with metadata."""
    items_data = []
    pool_names = {item.get('Name', '') for item in current_pool if item}
    
    # Rarity mapping from CSV format to UI format
    rarity_map = {
        'Common': 'white',
        'Uncommon': 'green',
        'Legendary': 'red',
        'Boss': 'yellow',
        'Lunar': 'blue',
        'Void': 'purple',
        'Equipment': 'orange',
        'Lunar Equipment': 'blue',
        'Elite Equipment': 'yellow'
    }
    
    for item in all_items:
        # Map rarity to UI format
        csv_rarity = item.get('Rarity', 'Common')
        ui_rarity = rarity_map.get(csv_rarity, 'white')
        
        # Use image URL directly from CSV
        image_url = item.get('Image', '') or ''
        
        items_data.append({
            'name': item.get('Name', 'Unknown'),
            'rarity': ui_rarity,
            'csv_rarity': csv_rarity,  # Keep original for reference
            'image': image_url,
            'tags': item.get('SynergyTags', []) or [],
            'playstyles': item.get('Playstyles', []) or [],
            'category': item.get('Category', ''),
            'stats': item.get('Stats', ''),
            'desc': item.get('Desc', ''),
            # prefer precomputed field when available
            'clean_desc': item.get('clean_desc') or clean_wiki_markup(item.get('Desc', '')),
            'dlc': item.get('DLC', 'Base'),
            'in_pool': item.get('Name', '') in pool_names
        })
    
    return jsonify({'items': items_data})


@app.route('/api/dlc', methods=['GET'])
def get_dlc_status():
    """Get available DLCs and their enabled status."""
    dlc_list = []
    for dlc_id, info in AVAILABLE_DLCS.items():
        dlc_list.append({
            'id': dlc_id,
            'name': info['name'],
            'icon': info['icon'],
            'color': info['color'],
            'enabled': dlc_id in enabled_dlcs
        })
    return jsonify({'dlcs': dlc_list})


@app.route('/api/dlc', methods=['POST'])
def set_dlc_status():
    """Enable or disable a specific DLC."""
    global enabled_dlcs, current_pool
    
    data = request.json or {}
    dlc_id = data.get('dlc')
    enable = data.get('enabled', True)
    
    if dlc_id not in AVAILABLE_DLCS:
        return jsonify({'error': f'Unknown DLC: {dlc_id}'}), 400
    
    # Don't allow disabling Base game
    if dlc_id == 'Base' and not enable:
        return jsonify({'error': 'Cannot disable Base game'}), 400
    
    if enable:
        enabled_dlcs.add(dlc_id)
    else:
        enabled_dlcs.discard(dlc_id)
    
    # Reload items with new DLC settings
    reload_items_for_dlcs()
    
    # Remove any pool items that are no longer available
    available_names = {item['Name'] for item in all_items}
    removed_items = []
    with pool_lock:
        new_pool = []
        for item in current_pool:
            if item.get('Name') in available_names:
                new_pool.append(item)
            else:
                removed_items.append(item.get('Name', 'Unknown'))
        current_pool[:] = new_pool
    
    return jsonify({
        'success': True,
        'enabled_dlcs': list(enabled_dlcs),
        'items_count': len(all_items),
        'removed_from_pool': removed_items
    })


@app.route('/api/pool', methods=['GET'])
def get_pool():
    """Get current pool state."""
    pool = get_pool_copy()
    params = get_scoring_params(current_config)
    return jsonify({
        'pool': pool,
        'score': score_pool(pool, synergy_graph, **params)
    })


@app.route('/api/pool', methods=['POST'])
def update_pool():
    """Replace the entire pool with supplied list of names."""
    data = request.json
    names = data.get('items', [])
    new_pool = []
    for name in names:
        item = next((it for it in all_items if it['Name'] == name), None)
        if item:
            new_pool.append(item)
    set_pool(new_pool)
    params = get_scoring_params(current_config)
    score = score_pool(new_pool, synergy_graph, **params)
    breakdown = score_breakdown(new_pool, synergy_graph, **params)
    return jsonify({
        'success': True,
        'pool': new_pool,
        'score': score,
        'breakdown': breakdown
    })


@app.route('/api/pool/add', methods=['POST'])
def add_item():
    """Add a named item to the pool, return updated pool."""
    data = request.json
    name = data.get('item')
    pool = get_pool_copy()
    item = next((it for it in all_items if it['Name'] == name), None)
    if item and all(it['Name'] != name for it in pool):
        pool.append(item)
        set_pool(pool)
    params = get_scoring_params(current_config)
    score = score_pool(pool, synergy_graph, **params)
    return jsonify({'success': bool(item), 'score': score, 'pool': pool})


@app.route('/api/pool/remove', methods=['POST'])
def remove_item():
    """Remove an item from the pool."""
    global current_pool
    data = request.json
    item_name = data.get('item')
    
    current_pool = [it for it in current_pool if it['Name'] != item_name]
    
    params = get_scoring_params(current_config)
    score = score_pool(current_pool, synergy_graph, **params)
    
    # include the new pool for client-side syncing
    return jsonify({'success': True, 'score': score, 'pool': current_pool})


@app.route('/api/pool/random', methods=['POST'])
def generate_random_pool():
    """Generate a random pool based on config."""
    global step_tabu
    data = request.json
    config = data.get('config', current_config)
    opt = LocalSearchOptimizer(all_items, config, random_seed=None)
    pool = opt._generate_initial_pool()
    set_pool(pool)
    # Clear step tabu list — new pool means a fresh optimisation session
    step_tabu = TabuList()
    params = get_scoring_params(config)
    score = score_pool(pool, synergy_graph, **params)
    return jsonify({
        'success': True,
        'pool': pool,
        'score': score
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    return jsonify(current_config)


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration."""
    global current_config
    data = request.json
    current_config.update(data)
    return jsonify({'success': True, 'config': current_config})


@app.route('/api/pool/pin', methods=['POST'])
def pin_item():
    """Pin an item so it won't be removed during optimization."""
    global current_config
    data = request.json
    item_name = data.get('item')
    
    if 'pinned_items' not in current_config:
        current_config['pinned_items'] = []
    
    if item_name not in current_config['pinned_items']:
        current_config['pinned_items'].append(item_name)
    
    return jsonify({'success': True, 'pinned_items': current_config['pinned_items']})


@app.route('/api/pool/unpin', methods=['POST'])
def unpin_item():
    """Unpin an item so it can be optimized."""
    global current_config
    data = request.json
    item_name = data.get('item')
    
    if 'pinned_items' not in current_config:
        current_config['pinned_items'] = []
    
    if item_name in current_config['pinned_items']:
        current_config['pinned_items'].remove(item_name)
    
    return jsonify({'success': True, 'pinned_items': current_config['pinned_items']})


@app.route('/api/config/style', methods=['POST'])
def update_style():
    """Update the play style preference."""
    global current_config
    data = request.json
    style = data.get('style')
    
    if style:
        current_config['style'] = style
    
    return jsonify({'success': True, 'style': current_config.get('style')})


@app.route('/api/pool/save', methods=['POST'])
def save_pool():
    """Save current pool to CSV and MD files with timestamp."""
    try:
        from datetime import datetime
        from ror2tools.generator import export_pool_files
        import shutil
        
        # Calculate score
        params = get_scoring_params(current_config)
        score = score_pool(current_pool, synergy_graph, **params)
        
        # Use enriched export function with config, synergy graph, and DLCs
        export_pool_files(
            current_pool,
            score=score,
            config=current_config,
            synergy_graph=synergy_graph,
            enabled_dlcs=enabled_dlcs,
        )
        
        # Create timestamped copies
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Copy to timestamped versions
        os.makedirs('output', exist_ok=True)
        shutil.copy('output/generated_pool.csv', f'output/pool_{timestamp}.csv')
        shutil.copy('output/generated_pool.md', f'output/pool_{timestamp}.md')
        
        return jsonify({
            'success': True,
            'csv_path': f'output/pool_{timestamp}.csv',
            'md_path': f'output/pool_{timestamp}.md',
            'filename': f'pool_{timestamp}.csv'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pool/list', methods=['GET'])
def list_saved_pools():
    """List all saved pool files."""
    try:
        import glob
        
        output_dir = 'output'
        if not os.path.exists(output_dir):
            return jsonify({'files': []})
        
        csv_files = glob.glob(os.path.join(output_dir, 'pool_*.csv'))
        files = []
        
        for filepath in sorted(csv_files, reverse=True):
            filename = os.path.basename(filepath)
            files.append({
                'filename': filename,
                'path': filepath,
                'timestamp': filename.replace('pool_', '').replace('.csv', '')
            })
        
        return jsonify({'files': files[:10]})  # Return last 10 saves
    except Exception as e:
        return jsonify({'files': [], 'error': str(e)})


@app.route('/api/pool/load', methods=['POST'])
def load_pool_from_file():
    """Load pool from CSV file."""
    global current_pool
    
    try:
        import csv as csv_mod
        
        data = request.json
        filename = data.get('filename', 'pool_*.csv')
        
        # If no specific file, load the most recent
        if filename == 'latest' or not filename:
            import glob
            csv_files = glob.glob(os.path.join('output', 'pool_*.csv'))
            if not csv_files:
                return jsonify({'success': False, 'error': 'No saved pools found'}), 404
            csv_path = sorted(csv_files, reverse=True)[0]
        else:
            csv_path = os.path.join('output', filename)
        
        if not os.path.exists(csv_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        # Load CSV
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_mod.DictReader(f)
            item_names = [row['Name'] for row in reader]
        
        # Find items by name
        current_pool = []
        for name in item_names:
            item = next((it for it in all_items if it.get('Name') == name), None)
            if item:
                current_pool.append(item)
        
        params = get_scoring_params(current_config)
        score = score_pool(current_pool, synergy_graph, **params)
        
        return jsonify({
            'success': True,
            'pool': current_pool,
            'score': score
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/optimize/reset', methods=['POST'])
def optimize_reset():
    """Reset the step-by-step optimizer state (clears tabu list)."""
    global step_tabu
    step_tabu = TabuList()
    return jsonify({'success': True})


@app.route('/api/optimize/step', methods=['POST'])
def optimize_step():
    """Perform a single optimization iteration."""
    try:
        data = request.json
        pool_names = data.get('pool', [])
        config = data.get('config', current_config)
        
        # Convert names to items
        pool = []
        for name in pool_names:
            item = next((it for it in all_items if it.get('Name') == name), None)
            if item:
                pool.append(item)
        
        if not pool:
            return jsonify({'improved': False, 'error': 'Empty pool'}), 400
        
        # Get k_opt from config - handle both nested and flat structures
        if 'optimization' in config and isinstance(config['optimization'], dict):
            k_opt = config['optimization'].get('k_opt', 1)
            cross_rarity = config['optimization'].get('cross_rarity', False)
        else:
            k_opt = config.get('k_opt', 1)
            cross_rarity = config.get('cross_rarity', False)
            
        synergy_weight = config.get('synergy_weight', 0.5)
        
        # Create optimizer
        optimizer = LocalSearchOptimizer(
            all_items, 
            config,
            k_opt=k_opt,
            max_iterations=1,  # Just one step
            cross_rarity=cross_rarity
        )
        optimizer.graph = synergy_graph
        optimizer.style = config.get('style')
        optimizer.synergy_weight = config.get('synergy_weight', 0.5)
        optimizer.style_weight = config.get('style_weight', 5.0)
        optimizer.diversity_weight = config.get('diversity_weight', 0.5)
        optimizer.coverage_weight = config.get('coverage_weight', 0.3)
        
        # Get current score
        params = get_scoring_params(config)
        current_score = score_pool(pool, synergy_graph, **params)
        
        # Find best swap
        swaps = optimizer._generate_neighborhood(pool, k=k_opt)
        if not swaps:
            return jsonify({'improved': False, 'message': 'No valid swaps available'})
        
        evaluated_swaps = optimizer._evaluate_swaps(pool, swaps)
        
        # ---- Tabu-aware selection for step-by-step mode ----
        # Record the current pool so we never cycle back to it.
        step_tabu.record(pool)
        current_fp = TabuList.pool_fingerprint(pool)
        params = get_scoring_params(config)
        current_score = score_pool(pool, synergy_graph, **params)
        
        best_swap = None
        for swap in evaluated_swaps:
            if swap.delta <= 0:
                break  # no improving swap left
            result_fp = TabuList.swap_result_fingerprint(current_fp, swap)
            if step_tabu.is_tabu(result_fp):
                continue  # skip visited states
            best_swap = swap
            break
        
        if best_swap is None or best_swap.delta <= 0:
            return jsonify({'improved': False, 'message': 'No improvements found (tabu filter active)'})
        
        # Apply best swap
        new_pool = optimizer._apply_swap(pool, best_swap)
        # Record the new state as tabu too
        step_tabu.record(new_pool)
        params = get_scoring_params(config)
        new_score = score_pool(new_pool, synergy_graph, **params)
        
        # Update global current_pool
        global current_pool
        current_pool = new_pool
        
        return jsonify({
            'improved': True,
            'pool': [item['Name'] for item in new_pool],
            'score': float(new_score),
            'delta': float(best_swap.delta),
            'swap': {
                'removed': [item['Name'] for item in best_swap.remove],
                'added': [item['Name'] for item in best_swap.add]
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'improved': False, 'error': str(e)}), 500


@socketio.on('start_optimization')
def handle_start_optimization(data):
    """Start optimization in background thread."""
    global optimizer, optimization_thread, history, current_pool
    
    try:
        config = data.get('config', current_config)
        k_opt = config.get('optimization', {}).get('k_opt', 1)
        max_iterations = config.get('optimization', {}).get('max_iterations', 50)
        convergence = config.get('optimization', {}).get('convergence_threshold', 10)
        tabu_tenure_val = config.get('optimization', {}).get('tabu_tenure', None)
        cross_rarity = config.get('optimization', {}).get('cross_rarity', False)
        
        optimizer = LocalSearchOptimizer(
            all_items, config,
            k_opt=k_opt,
            max_iterations=max_iterations,
            convergence_threshold=convergence,
            tabu_tenure=tabu_tenure_val,
            cross_rarity=cross_rarity,
        )
        
        history = OptimizationHistory()
        
        def optimization_worker():
            global current_pool
            
            try:
                def callback(state):
                    # Send progress update to client
                    socketio.emit('optimization_progress', {
                        'iteration': state.iteration,
                        'score': state.score,
                        'best_score': state.best_score,
                        'stale': state.stale_iterations,
                        'pool': [item['Name'] for item in state.pool],
                        'last_swap': {
                            'removed': [item['Name'] for item in state.last_swap.remove] if state.last_swap else [],
                            'added': [item['Name'] for item in state.last_swap.add] if state.last_swap else [],
                            'delta': state.last_swap.delta if state.last_swap else 0
                        } if state.last_swap else None
                    })
                    history.record(state)
                    return True
                
                # Use current pool as starting point
                initial = get_pool_copy() or None
                best_pool, final_state = optimizer.optimize(
                    initial_pool=initial,
                    callback=callback
                )
                
                # Update global pool under lock
                set_pool(best_pool)
                
                # Send completion
                socketio.emit('optimization_complete', {
                    'pool': [item['Name'] for item in best_pool],
                    'score': final_state.best_score,
                    'iterations': final_state.iteration + 1,
                    'history': [{'iteration': e.iteration, 'score': e.score, 'best_score': e.best_score} 
                            for e in history.entries]
                })
            except Exception as e:
                print(f"Optimization error: {e}")
                import traceback
                traceback.print_exc()
                socketio.emit('optimization_error', {'error': str(e)})
        
        # Launch worker using SocketIO helper (works with eventlet/gevent)
        socketio.start_background_task(optimization_worker)
        
        emit('optimization_started', {'success': True})
    except Exception as e:
        print(f"Start optimization error: {e}")
        import traceback
        traceback.print_exc()
        emit('optimization_error', {'error': str(e)})


@socketio.on('stop_optimization')
def handle_stop_optimization():
    """Stop ongoing optimization."""
    # Note: This is a simplified stop - in production you'd need more robust thread control
    emit('optimization_stopped', {'success': True})


if __name__ == '__main__':
    print("="*70)
    print("Risk of Rain 2 Pool Optimizer - Web Interface")
    print("="*70)
    
    # Initialize data
    initialize_data()
    
    if not all_items:
        print("\n⚠ Warning: No items loaded!")
        print("Run 'python main.py export' first to download item data.")
    
    print("\n🌐 Starting server...")
    print("📱 Open http://localhost:5000 in your browser")
    print("="*70)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
