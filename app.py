"""
Flask web application for Risk of Rain 2 item pool optimization.

Provides a modern drag-and-drop interface for building and optimizing pools.
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import os
import json
import threading

from ror2tools.generator import load_items, load_config
from ror2tools.optimizer import LocalSearchOptimizer
from ror2tools.scoring import score_pool, score_breakdown
from ror2tools.history import OptimizationHistory
from ror2tools.utils import load_synergy_graph


app = Flask(__name__)
app.config['SECRET_KEY'] = 'ror2-optimization-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
current_pool = []
current_config = {}
optimizer = None
optimization_thread = None
history = OptimizationHistory()
all_items = []
synergy_graph = {}


def initialize_data():
    """Load items and synergy graph on startup."""
    global all_items, synergy_graph, current_config
    try:
        all_items = load_items()
        synergy_graph = load_synergy_graph()
        current_config = load_config()
        print(f"✓ Loaded {len(all_items)} items")
        print(f"✓ Loaded synergy graph with {len(synergy_graph)} nodes")
    except Exception as e:
        print(f"⚠ Error loading data: {e}")
        all_items = []
        synergy_graph = {}
        current_config = {}


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
        
        # Use consistent image format
        image_url = item.get('Image', '')
        if not image_url or image_url == '':
            # Use placeholder
            image_url = f"https://static.wikia.nocookie.net/riskofrain2_gamepedia_en/images/d/de/Squid_Polyp.png/revision/latest?cb=20210329071113"
        
        items_data.append({
            'name': item.get('Name', 'Unknown'),
            'rarity': ui_rarity,
            'csv_rarity': csv_rarity,  # Keep original for reference
            'image': image_url,
            'tags': item.get('SynergyTags', []) or [],
            'playstyles': item.get('Playstyles', []) or [],
            'desc': item.get('Desc', ''),
            'in_pool': item.get('Name', '') in pool_names
        })
    
    return jsonify({'items': items_data})


@app.route('/api/pool', methods=['GET'])
def get_pool():
    """Get current pool state."""
    return jsonify({
        'pool': current_pool,
        'score': score_pool(current_pool, synergy_graph, 
                           current_config.get('style'), 
                           current_config.get('synergy_weight', 0))
    })


@app.route('/api/pool', methods=['POST'])
def update_pool():
    """Update the current pool."""
    global current_pool
    data = request.json
    item_names = data.get('items', [])
    
    # Find items by name
    new_pool = []
    for name in item_names:
        item = next((it for it in all_items if it['Name'] == name), None)
        if item:
            new_pool.append(item)
    
    current_pool = new_pool
    
    score = score_pool(current_pool, synergy_graph,
                      current_config.get('style'),
                      current_config.get('synergy_weight', 0))
    
    breakdown = score_breakdown(current_pool, synergy_graph,
                                current_config.get('style'),
                                current_config.get('synergy_weight', 0))
    
    return jsonify({
        'success': True,
        'pool': current_pool,
        'score': score,
        'breakdown': breakdown
    })


@app.route('/api/pool/add', methods=['POST'])
def add_item():
    """Add an item to the pool."""
    global current_pool
    data = request.json
    item_name = data.get('item')
    
    item = next((it for it in all_items if it['Name'] == item_name), None)
    if item and item not in current_pool:
        current_pool.append(item)
        
        score = score_pool(current_pool, synergy_graph,
                          current_config.get('style'),
                          current_config.get('synergy_weight', 0))
        
        return jsonify({'success': True, 'score': score})
    
    return jsonify({'success': False, 'error': 'Item not found or already in pool'})


@app.route('/api/pool/remove', methods=['POST'])
def remove_item():
    """Remove an item from the pool."""
    global current_pool
    data = request.json
    item_name = data.get('item')
    
    current_pool = [it for it in current_pool if it['Name'] != item_name]
    
    score = score_pool(current_pool, synergy_graph,
                      current_config.get('style'),
                      current_config.get('synergy_weight', 0))
    
    return jsonify({'success': True, 'score': score})


@app.route('/api/pool/random', methods=['POST'])
def generate_random_pool():
    """Generate a random pool based on config."""
    global current_pool, optimizer
    
    data = request.json
    config = data.get('config', current_config)
    
    optimizer = LocalSearchOptimizer(all_items, config, random_seed=None)
    current_pool = optimizer._generate_initial_pool()
    
    score = score_pool(current_pool, synergy_graph,
                      config.get('style'),
                      config.get('synergy_weight', 0))
    
    return jsonify({
        'success': True,
        'pool': current_pool,
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


@app.route('/api/pool/save', methods=['POST'])
def save_pool():
    """Save current pool to CSV and MD files with timestamp."""
    try:
        from datetime import datetime
        from ror2tools.generator import export_pool_files
        import shutil
        
        # Calculate score
        score = score_pool(current_pool, synergy_graph, 
                          current_config.get('style'),
                          current_config.get('synergy_weight', 0))
        
        # Use original export function
        export_pool_files(current_pool, score)
        
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
        import pandas as pd
        
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
        df = pd.read_csv(csv_path)
        item_names = df['Name'].tolist()
        
        # Find items by name
        current_pool = []
        for name in item_names:
            item = next((it for it in all_items if it.get('Name') == name), None)
            if item:
                current_pool.append(item)
        
        score = score_pool(current_pool, synergy_graph,
                          current_config.get('style'),
                          current_config.get('synergy_weight', 0))
        
        return jsonify({
            'success': True,
            'pool': current_pool,
            'score': score
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@socketio.on('start_optimization')
def handle_start_optimization(data):
    """Start optimization in background thread."""
    global optimizer, optimization_thread, history, current_pool
    
    try:
        config = data.get('config', current_config)
        k_opt = config.get('optimization', {}).get('k_opt', 1)
        max_iterations = config.get('optimization', {}).get('max_iterations', 50)
        convergence = config.get('optimization', {}).get('convergence_threshold', 10)
        
        optimizer = LocalSearchOptimizer(
            all_items, config,
            k_opt=k_opt,
            max_iterations=max_iterations,
            convergence_threshold=convergence
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
                best_pool, final_state = optimizer.optimize(
                    initial_pool=current_pool if current_pool else None,
                    callback=callback
                )
                
                # Update global pool
                current_pool = best_pool
                
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
        
        optimization_thread = threading.Thread(target=optimization_worker)
        optimization_thread.daemon = True
        optimization_thread.start()
        
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
