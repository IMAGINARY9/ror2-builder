// Risk of Rain 2 Pool Optimizer - Frontend Application
// Drag-and-drop interface for building and optimizing item pools

// Global state
let allItems = [];
let currentPool = [];
let currentScore = 0;
let bestScore = 0;
let activeFilter = 'all';
let socket = null;
let dragFromPool = false; // true while dragging a card originating from pool
let optimizationRunning = false;
let historyData = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    setupEventListeners();
    setupSocketIO();
});

// Initialize application
async function initializeApp() {
    showStatus('Loading items...', 'info');
    
    try {
        await loadItems();
        await loadPoolState();
        await loadConfig();
        
        renderItems();
        updateUI();
        
        showStatus('Ready to build!', 'success');
    } catch (error) {
        showStatus('Error loading data: ' + error.message, 'error');
        console.error(error);
    }
}

// Load all available items
async function loadItems() {
    const response = await fetch('/api/items');
    const data = await response.json();
    allItems = data.items;
}

// Load current pool state from API
async function loadPoolState() {
    const response = await fetch('/api/pool');
    const data = await response.json();
    currentPool = data.pool;
    currentScore = data.score;
    bestScore = Math.max(bestScore, currentScore);
}

// Load configuration
async function loadConfig() {
    const response = await fetch('/api/config');
    const config = await response.json();
    
    // Update UI with config values
    document.getElementById('kOpt').value = config.optimization?.k_opt || 1;
    document.getElementById('maxIterations').value = config.optimization?.max_iterations || 100;
    document.getElementById('convergence').value = config.optimization?.convergence_threshold || 10;
    document.getElementById('synergyWeight').value = config.synergy_weight || 0;
}

// Setup event listeners
function setupEventListeners() {
    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            activeFilter = e.target.dataset.rarity;
            renderItems();
        });
    });
    
    // Pool controls
    document.getElementById('savePool').addEventListener('click', savePool);
    document.getElementById('loadPool').addEventListener('click', loadPool);
    document.getElementById('clearPool').addEventListener('click', clearPool);
    document.getElementById('randomPool').addEventListener('click', generateRandomPool);
    
    // Optimization controls
    document.getElementById('startOptimization').addEventListener('click', startOptimization);
    document.getElementById('stopOptimization').addEventListener('click', stopOptimization);
    
    // Pool drop zone
    const dropZone = document.getElementById('poolDropZone');
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('drop', handleDrop);
    dropZone.addEventListener('dragleave', handleDragLeave);
    

    
    // allow removing by dropping back onto available items (only when dragging from pool)
    const itemsGrid = document.getElementById('itemsGrid');
    itemsGrid.addEventListener('dragover', (e) => {
        if (!dragFromPool) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        itemsGrid.classList.add('drag-over');
    });
    itemsGrid.addEventListener('dragleave', () => {
        itemsGrid.classList.remove('drag-over');
    });
    itemsGrid.addEventListener('drop', async (e) => {
        itemsGrid.classList.remove('drag-over');
        if (!dragFromPool) return;
        e.preventDefault();
        const itemName = e.dataTransfer.getData('text/plain');
        if (itemName) {
            await removeItemFromPool(itemName);
        }
    });
    
    // Modal close
    document.querySelector('.close').addEventListener('click', () => {
        document.getElementById('itemModal').classList.remove('show');
    });
}

// Setup Socket.IO for real-time updates
function setupSocketIO() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to server');
        showStatus('Connected to server', 'success');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        showStatus('Disconnected from server', 'warning');
    });
    
    socket.on('optimization_started', () => {
        optimizationRunning = true;
        updateOptimizationButtons();
        showStatus('Optimization started...', 'info');
    });
    
    socket.on('optimization_progress', (data) => {
        updateOptimizationProgress(data);
    });
    
    socket.on('optimization_complete', (data) => {
        optimizationRunning = false;
        updateOptimizationButtons();
        handleOptimizationComplete(data);
    });
    
    socket.on('optimization_error', (data) => {
        optimizationRunning = false;
        updateOptimizationButtons();
        showStatus('Optimization error: ' + (data.error || 'Unknown error'), 'error');
        console.error('Optimization error:', data);
    });
    
    socket.on('optimization_stopped', () => {
        optimizationRunning = false;
        updateOptimizationButtons();
        showStatus('Optimization stopped', 'warning');
    });
}

// Render items grid
function renderItems() {
    const grid = document.getElementById('itemsGrid');
    grid.innerHTML = '';
    
    const filteredItems = allItems.filter(item => {
        // Ensure rarity exists and is a string
        const itemRarity = (item.rarity || 'white').toString().toLowerCase();
        return activeFilter === 'all' || itemRarity === activeFilter.toLowerCase();
    });
    
    filteredItems.forEach(item => {
        const card = createItemCard(item);
        grid.appendChild(card);
    });
}

// Create item card element
function createItemCard(item) {
    const card = document.createElement('div');
    card.className = 'item-card';
    card.draggable = true;
    card.dataset.itemName = item.name;
    
    // Ensure rarity is valid
    const rarity = (item.rarity || 'white').toString().toLowerCase();
    card.dataset.rarity = rarity;
    
    if (item.in_pool) {
        card.classList.add('in-pool');
    }
    
    // Item icon/name
    if (item.image) {
        const img = document.createElement('img');
        img.src = item.image;
        img.alt = item.name;
        img.className = 'item-icon';
        card.appendChild(img);
    } else {
        const name = document.createElement('div');
        name.className = 'item-name';
        name.textContent = item.name;
        card.appendChild(name);
    }
    
    // Drag events
    card.addEventListener('dragstart', handleDragStart);
    card.addEventListener('dragend', handleDragEnd);
    card.addEventListener('click', () => showItemDetails(item));
    
    return card;
}

// Drag and drop handlers
function handleDragStart(e) {
    // basic dragging behaviour used by all cards; pool-specific flag
    // is added separately in renderPool when creating pool cards.
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', e.target.dataset.itemName);
}

function handleDragEnd(e) {
    e.target.classList.remove('dragging');
    dragFromPool = false;
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    
    const dropZone = e.currentTarget;
    if (!dropZone.classList.contains('drag-over')) {
        dropZone.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    if (e.target.id === 'poolDropZone') {
        e.currentTarget.classList.remove('drag-over');
    }
}

async function handleDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    
    const itemName = e.dataTransfer.getData('text/plain');
    await addItemToPool(itemName);
}

// Pool operations
async function addItemToPool(itemName) {
    try {
        const response = await fetch('/api/pool/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item: itemName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.pool) {
                currentPool = data.pool;
            }
            updateUI();
            showStatus(`Added ${itemName} to pool`, 'success');
        } else {
            showStatus(data.error || 'Failed to add item', 'error');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function removeItemFromPool(itemName) {
    try {
        const response = await fetch('/api/pool/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item: itemName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // optimistic update using returned pool if available
            if (data.pool) {
                currentPool = data.pool;
            } else {
                currentPool = currentPool.filter(it => it.Name !== itemName && it.name !== itemName);
            }
            updateUI();
            showStatus(`Removed ${itemName} from pool`, 'success');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function clearPool() {
    // No confirmation dialog - just clear
    try {
        const response = await fetch('/api/pool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: [] })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentPool = [];
            currentScore = 0;
            renderItems();
            updateUI();
            showStatus('Pool cleared', 'success');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function savePool() {
    if (currentPool.length === 0) {
        showStatus('Pool is empty, nothing to save', 'warning');
        return;
    }
    
    showStatus('Saving pool...', 'info');
    
    try {
        const response = await fetch('/api/pool/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showStatus(`Pool saved to ${data.csv_path}`, 'success');
        } else {
            showStatus('Error: ' + (data.error || 'Failed to save'), 'error');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function loadPool() {
    showStatus('Loading saved pool...', 'info');
    
    try {
        // Ask user which file to load
        const listResponse = await fetch('/api/pool/list');
        const listData = await listResponse.json();
        
        if (!listData.files || listData.files.length === 0) {
            showStatus('No saved pools found', 'warning');
            return;
        }
        
        let filename = prompt(
            'Enter filename to load (leave empty for latest):\n' +
            listData.files.map(f => f.filename).join('\n')
        );
        if (!filename) {
            filename = 'latest';
        }
        
        const response = await fetch('/api/pool/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
        
        if (!response.ok) {
            const data = await response.json();
            showStatus('Error: ' + (data.error || 'Failed to load'), 'error');
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            if (data.pool) currentPool = data.pool;
            renderItems();
            updateUI();
            showStatus('Pool loaded successfully!', 'success');
        } else {
            showStatus('Error: ' + (data.error || 'Failed to load'), 'error');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function generateRandomPool() {
    showStatus('Generating random pool...', 'info');
    
    try {
        const response = await fetch('/api/pool/random', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: await getCurrentConfig() })
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch');
        }
        
        const data = await response.json();
        
        if (data.success) {
            if (data.pool) {
                currentPool = data.pool;
            }
            renderItems();
            updateUI();
            showStatus('Random pool generated!', 'success');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

// Optimization
async function startOptimization() {
    if (currentPool.length === 0) {
        showStatus('Add items to pool first!', 'warning');
        return;
    }
    
    const config = await getCurrentConfig();
    
    socket.emit('start_optimization', { config });
    
    // Clear previous history
    historyData = [];
    document.getElementById('historyTable').innerHTML = '';
}

function stopOptimization() {
    socket.emit('stop_optimization');
}

function updateOptimizationProgress(data) {
    // Update scores
    currentScore = data.score;
    bestScore = data.best_score;
    document.getElementById('currentScore').textContent = currentScore.toFixed(2);
    document.getElementById('bestScore').textContent = bestScore.toFixed(2);
    
    // Update progress bar
    const progress = (data.iteration / parseInt(document.getElementById('maxIterations').value)) * 100;
    document.getElementById('progressBar').style.width = progress + '%';
    
    // Update status
    showStatus(
        `Iteration ${data.iteration}: Score ${data.score.toFixed(2)} (Best: ${data.best_score.toFixed(2)}, Stale: ${data.stale})`,
        'info'
    );
    
    // Add to history
    historyData.push({
        iteration: data.iteration,
        score: data.score,
        bestScore: data.best_score
    });
    
    // Update history display
    addHistoryEntry(data);
}

function handleOptimizationComplete(data) {
    currentPool = data.pool.map(name => allItems.find(item => item.name === name));
    currentScore = data.score;
    bestScore = data.score;
    
    renderItems();
    updateUI();
    
    document.getElementById('progressBar').style.width = '100%';
    
    showStatus(
        `Optimization complete! Final score: ${data.score.toFixed(2)} (${data.iterations} iterations)`,
        'success'
    );
    
    // Draw history chart
    drawHistoryChart();
}

function addHistoryEntry(data) {
    const table = document.getElementById('historyTable');
    
    const entry = document.createElement('div');
    entry.className = 'history-entry';
    
    const swap = data.last_swap;
    const swapText = swap 
        ? `Removed: ${swap.removed.join(', ')}<br>Added: ${swap.added.join(', ')}<br>Δ: ${swap.delta.toFixed(2)}`
        : 'No swap';
    
    entry.innerHTML = `
        <div><strong>Iter ${data.iteration}</strong></div>
        <div>Score: ${data.score.toFixed(2)}</div>
        <div>Best: ${data.best_score.toFixed(2)}</div>
        <div>${swapText}</div>
    `;
    
    table.insertBefore(entry, table.firstChild);
    
    // Keep only last 20 entries
    while (table.children.length > 20) {
        table.removeChild(table.lastChild);
    }
}

function drawHistoryChart() {
    const canvas = document.getElementById('historyChart');
    const ctx = canvas.getContext('2d');
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 300;
    
    if (historyData.length === 0) return;
    
    const padding = 40;
    const width = canvas.width - 2 * padding;
    const height = canvas.height - 2 * padding;
    
    // Clear canvas
    ctx.fillStyle = '#3d3d3d';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Find min/max
    const scores = historyData.map(d => d.score);
    const minScore = Math.min(...scores);
    const maxScore = Math.max(...scores);
    const range = maxScore - minScore || 1;
    
    // Draw axes
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, height + padding);
    ctx.lineTo(width + padding, height + padding);
    ctx.stroke();
    
    // Draw line
    ctx.strokeStyle = '#4a9eff';
    ctx.lineWidth = 3;
    ctx.beginPath();
    
    historyData.forEach((data, i) => {
        const x = padding + (i / (historyData.length - 1)) * width;
        const y = padding + height - ((data.score - minScore) / range) * height;
        
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.stroke();
    
    // Draw best score line
    ctx.strokeStyle = '#4caf50';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    
    historyData.forEach((data, i) => {
        const x = padding + (i / (historyData.length - 1)) * width;
        const y = padding + height - ((data.bestScore - minScore) / range) * height;
        
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Draw labels
    ctx.fillStyle = '#e0e0e0';
    ctx.font = '12px Arial';
    ctx.fillText('Iteration', width / 2 + padding, height + padding + 30);
    ctx.save();
    ctx.translate(10, height / 2 + padding);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Score', 0, 0);
    ctx.restore();
}

// UI updates
function updateUI() {
    // Update scores
    document.getElementById('currentScore').textContent = currentScore.toFixed(2);
    document.getElementById('bestScore').textContent = bestScore.toFixed(2);
    
    // Render pool (also updates allItems.in_pool)
    renderPool();
    
    // Re-render available grid so its classes reflect the new pool state immediately
    renderItems();
}

function renderPool() {
    const poolZone = document.getElementById('poolDropZone');
    const emptyState = poolZone.querySelector('.empty-state');
    
    // Clear existing items
    poolZone.querySelectorAll('.item-card').forEach(card => card.remove());
    
    if (currentPool.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        return;
    }
    
    if (emptyState) emptyState.style.display = 'none';
    
    currentPool.forEach(item => {
        // Create card from item data
        const itemData = {
            name: item.Name || item.name,
            rarity: item.Rarity || item.rarity,
            image: item.Image || item.image,
            tags: item.SynergyTags || item.tags || [],
            playstyles: item.Playstyles || item.playstyles || [],
            desc: item.Desc || item.desc || '',
            in_pool: true
        };
        
        const card = createItemCard(itemData);
        card.classList.remove('in-pool');
        
        // Enable dragging FROM pool to remove
        card.draggable = true;
        card.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', itemData.name);
            e.dataTransfer.setData('remove', 'true');  // Flag for removal
            card.classList.add('dragging');
            dragFromPool = true; // indicate removal drag
        });
        card.addEventListener('dragend', () => {
            card.classList.remove('dragging');
            dragFromPool = false;
        });
        
        // Click to remove
        card.addEventListener('click', () => removeItemFromPool(itemData.name));
        
        poolZone.appendChild(card);
    });
    
    // Update available items to show in_pool status
    refreshAvailableItemsStatus();
}

function refreshAvailableItemsStatus() {
    const poolNames = new Set(currentPool.map(it => it.Name || it.name));
    
    // Update allItems in_pool status
    allItems.forEach(item => {
        item.in_pool = poolNames.has(item.name);
    });
    
    // Re-render items grid with updated status
    const grid = document.getElementById('itemsGrid');
    const cards = grid.querySelectorAll('.item-card');
    cards.forEach(card => {
        const itemName = card.dataset.itemName;
        if (poolNames.has(itemName)) {
            card.classList.add('in-pool');
        } else {
            card.classList.remove('in-pool');
        }
    });
}

function updateOptimizationButtons() {
    document.getElementById('startOptimization').disabled = optimizationRunning;
    document.getElementById('stopOptimization').disabled = !optimizationRunning;
}

function showStatus(message, type = 'info') {
    const statusText = document.querySelector('.status-text');
    statusText.textContent = message;
    
    statusText.style.color = {
        'info': '#4a9eff',
        'success': '#4caf50',
        'warning': '#ff9800',
        'error': '#f44336'
    }[type] || '#e0e0e0';
}

// Item details modal
function showItemDetails(item) {
    const modal = document.getElementById('itemModal');
    const body = document.getElementById('modalBody');
    
    body.innerHTML = `
        <h2>${item.name}</h2>
        <p><strong>Rarity:</strong> ${item.rarity}</p>
        <p><strong>Description:</strong> ${item.desc || 'No description available'}</p>
        <p><strong>Tags:</strong> ${item.tags.join(', ') || 'None'}</p>
        <p><strong>Playstyles:</strong> ${item.playstyles.join(', ') || 'None'}</p>
    `;
    
    modal.classList.add('show');
}

// Get current configuration from UI
async function getCurrentConfig() {
    const baseConfig = await fetch('/api/config').then(r => r.json());
    
    return {
        ...baseConfig,
        optimization: {
            k_opt: parseInt(document.getElementById('kOpt').value),
            max_iterations: parseInt(document.getElementById('maxIterations').value),
            convergence_threshold: parseInt(document.getElementById('convergence').value)
        },
        synergy_weight: parseFloat(document.getElementById('synergyWeight').value)
    };
}
