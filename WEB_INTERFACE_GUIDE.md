# Web Interface Quick Start Guide

## Starting the Application

1. **Install dependencies** (first time only):
   ```powershell
   .venv\Scripts\python.exe -m pip install flask flask-socketio eventlet
   ```

2. **Export item data** (if not done already):
   ```powershell
   python main.py export
   ```

3. **Start the web server**:
   ```powershell
   python app.py
   ```

4. **Open in browser**:
   - Navigate to `http://localhost:5000`

## Using the Interface

### Building Your Pool

**Drag and Drop:**
- Drag items from the "Available Items" grid on the right
- Drop them into the "Current Pool" zone on the left
- Items automatically update the score in real-time

**Filters:**
- Click rarity buttons (All/White/Green/Red/Yellow/Blue) to filter items
- Only matching items will be shown in the grid

**Quick Actions:**
- **Clear**: Remove all items from pool
- **Random**: Generate a random pool based on config

### Optimizing Your Pool

1. **Configure optimization parameters:**
   - **K-opt**: Number of simultaneous swaps (1-5)
   - **Max Iterations**: Maximum optimization steps (10-1000)
   - **Convergence**: Stop after N stale iterations (5-50)
   - **Synergy Weight**: How much to weight item synergies (0-1)

2. **Start optimization:**
   - Click "Start Optimization"
   - Watch real-time progress in the status bar
   - See iteration details in the history table
   - Pool updates automatically with better combinations

3. **Monitor progress:**
   - **Current Score**: Score of current pool
   - **Best Score**: Highest score achieved
   - **Iteration**: Current optimization step
   - **History Chart**: Visual graph of score progression

### Understanding Scores

**Score Breakdown:**
- **Coverage**: How well the pool covers different playstyles
- **Synergy**: Bonus from items that work well together

Higher scores mean better item combinations for your selected playstyle.

## Configuration

Edit `data/config.json` to customize:
- Rarity distribution (how many white/green/red/yellow/blue items)
- Target playstyle (frenzy, purity, survivor, etc.)
- Synergy weight
- Optimization settings (k-opt, iterations, convergence)

## Troubleshooting

**"No items loaded" warning:**
- Run `python main.py export` to download item data first

**Server won't start:**
- Make sure virtual environment is activated
- Check that port 5000 is not already in use
- Install dependencies: `pip install -r requirements.txt`

**Items not dragging:**
- Use a modern browser (Chrome, Firefox, Edge)
- Enable JavaScript in browser settings

**Optimization not starting:**
- Add at least one item to the pool first
- Check that config.json has valid optimization settings

## Tips & Tricks

1. **Start with a random pool** before optimizing for better results
2. **Use lower k-opt (1-2)** for faster, more stable optimization
3. **Higher k-opt (3-5)** explores more aggressively but may be slower
4. **Adjust synergy weight** to balance coverage vs. item combos
5. **Monitor the history chart** to see if optimization is improving
6. **Stop early** if the score plateaus (no improvement for many iterations)

## Keyboard Shortcuts

- Click an item in the pool to remove it
- Click an item card to see full details (modal)
- Close modal with the X button or by clicking outside

## API Endpoints

For advanced users building integrations:

- `GET /api/items` - Get all items (each object includes `clean_desc`, a pre‑formatted description with wiki markup removed)
- `GET /api/pool` - Get current pool and score (pool entries also include `clean_desc` so cards display nicely)
- `POST /api/pool` - Update entire pool
- `POST /api/pool/add` - Add item to pool
- `POST /api/pool/remove` - Remove item from pool
- `POST /api/pool/random` - Generate random pool
- `GET /api/config` - Get configuration
- `POST /api/config` - Update configuration

## WebSocket Events

Real-time optimization uses Socket.IO:

- `start_optimization` - Begin optimization
- `stop_optimization` - Stop optimization
- `optimization_progress` - Receive iteration updates
- `optimization_complete` - Final results
