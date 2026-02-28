// Risk of Rain 2 Pool Optimizer - Frontend Application
// Drag-and-drop interface for building and optimizing item pools

// Global state
let allItems = [];
let currentPool = [];
let currentScore = 0;
let bestScore = 0;
let iterationCount = 0; // Tracks all user interactions
let activeFilter = 'all';
let socket = null;
let dragFromPool = false; // true while dragging a card originating from pool
let optimizationRunning = false;
let currentOptimizer = null; // reference to current optimization session
let pinnedItems = new Set(); // Set of pinned item names
let dlcStatus = []; // Array of DLC status objects

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
        await loadDLCStatus();
        await loadItems();
        await loadPoolState();
        await loadConfig();
        
        renderDLCToggles();
        renderItems();
        updateUI();
        
        showStatus('Ready to build!', 'success');
    } catch (error) {
        showStatus('Error loading data: ' + error.message, 'error');
        console.error(error);
    }
}

// Load DLC status
async function loadDLCStatus() {
    const response = await fetch('/api/dlc');
    const data = await response.json();
    dlcStatus = data.dlcs;
}

// Render DLC toggle buttons
function renderDLCToggles() {
    const container = document.getElementById('dlcToggles');
    container.innerHTML = '';
    
    dlcStatus.forEach(dlc => {
        const btn = document.createElement('button');
        btn.className = `dlc-btn ${dlc.enabled ? 'enabled' : ''} ${dlc.id === 'Base' ? 'disabled-permanent' : ''}`;
        btn.dataset.dlc = dlc.id;
        btn.style.setProperty('--dlc-color', dlc.color);
        // Convert hex color to RGB for rgba() usage
        const hex = dlc.color.replace('#', '');
        const r = parseInt(hex.substr(0, 2), 16) || 74;
        const g = parseInt(hex.substr(2, 2), 16) || 158;
        const b = parseInt(hex.substr(4, 2), 16) || 255;
        btn.style.setProperty('--dlc-rgb', `${r}, ${g}, ${b}`);
        
        btn.innerHTML = `
            <span class="dlc-icon">${dlc.icon}</span>
            <span class="dlc-name">${dlc.id}</span>
        `;
        btn.title = `${dlc.name} - Click to ${dlc.enabled ? 'disable' : 'enable'}`;
        
        if (dlc.id !== 'Base') {
            btn.addEventListener('click', () => toggleDLC(dlc.id, !dlc.enabled));
        }
        
        container.appendChild(btn);
    });
}

// Toggle DLC enabled/disabled
async function toggleDLC(dlcId, enable) {
    showStatus(`${enable ? 'Enabling' : 'Disabling'} ${dlcId}...`, 'info');
    
    try {
        const response = await fetch('/api/dlc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dlc: dlcId, enabled: enable })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showStatus('Error: ' + data.error, 'error');
            return;
        }
        
        // Update local DLC status
        dlcStatus = dlcStatus.map(dlc => ({
            ...dlc,
            enabled: data.enabled_dlcs.includes(dlc.id)
        }));
        
        // Reload items with new DLC filter
        await loadItems();
        await loadPoolState();
        
        // Re-render everything
        renderDLCToggles();
        renderItems();
        renderPool();
        updateUI();
        
        // Notify about removed items
        if (data.removed_from_pool && data.removed_from_pool.length > 0) {
            showStatus(`${dlcId} ${enable ? 'enabled' : 'disabled'}. Removed from pool: ${data.removed_from_pool.join(', ')}`, 'warning');
        } else {
            showStatus(`${dlcId} ${enable ? 'enabled' : 'disabled'}. ${data.items_count} items available.`, 'success');
        }
    } catch (error) {
        showStatus('Error toggling DLC: ' + error.message, 'error');
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
    document.getElementById('synergyWeight').value = config.synergy_weight || 0.5;
    document.getElementById('styleWeight').value = config.style_weight || 8.0;
    document.getElementById('diversityWeight').value = config.diversity_weight || 1.0;
    document.getElementById('coverageWeight').value = config.coverage_weight || 1.0;
    document.getElementById('balanceWeight').value = config.balance_weight || 5.0;
    document.getElementById('playStyle').value = config.style || '';
    
    // Update slider value displays
    document.getElementById('kOptValue').textContent = config.optimization?.k_opt || 1;
    document.getElementById('crossRarity').checked = config.optimization?.cross_rarity || false;
    document.getElementById('synergyWeightValue').textContent = (config.synergy_weight || 0.5).toFixed(1);
    document.getElementById('styleWeightValue').textContent = (config.style_weight || 8.0).toFixed(1);
    document.getElementById('diversityWeightValue').textContent = (config.diversity_weight || 1.0).toFixed(1);
    document.getElementById('coverageWeightValue').textContent = (config.coverage_weight || 1.0).toFixed(1);
    document.getElementById('balanceWeightValue').textContent = (config.balance_weight || 5.0).toFixed(1);
    
    // Load pinned items
    pinnedItems = new Set(config.pinned_items || []);
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
    document.getElementById('clearPool').addEventListener('click', clearPool);
    document.getElementById('randomPool').addEventListener('click', generateRandomPool);
    
    // Optimization controls  
    document.getElementById('nextIteration').addEventListener('click', nextIteration);
    
    // Configuration controls
    document.getElementById('playStyle').addEventListener('change', async (e) => {
        await updatePlayStyle(e.target.value);
    });
    
    // Range slider value updates
    const sliderConfigs = [
        { id: 'kOpt', valueId: 'kOptValue', format: (v) => v },
        { id: 'synergyWeight', valueId: 'synergyWeightValue', format: (v) => parseFloat(v).toFixed(1) },
        { id: 'styleWeight', valueId: 'styleWeightValue', format: (v) => parseFloat(v).toFixed(1) },
        { id: 'diversityWeight', valueId: 'diversityWeightValue', format: (v) => parseFloat(v).toFixed(1) },
        { id: 'coverageWeight', valueId: 'coverageWeightValue', format: (v) => parseFloat(v).toFixed(1) },
        { id: 'balanceWeight', valueId: 'balanceWeightValue', format: (v) => parseFloat(v).toFixed(1) }
    ];
    
    sliderConfigs.forEach(config => {
        const slider = document.getElementById(config.id);
        const valueDisplay = document.getElementById(config.valueId);
        
        slider.addEventListener('input', (e) => {
            valueDisplay.textContent = config.format(e.target.value);
        });
        
        // Initialize display with current value
        valueDisplay.textContent = config.format(slider.value);
    });
    
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

    // Parameter change handlers: reset optimizer state and re-enable optimize button
    const kOptInput = document.getElementById('kOpt');
    const synergyInput = document.getElementById('synergyWeight');
    const paramHandler = () => {
        // Clear any running optimizer so nextIteration will reinitialize with new params
        if (currentOptimizer) currentOptimizer = null;
        const nextBtn = document.getElementById('nextIteration');
        if (nextBtn) nextBtn.disabled = false;
        showStatus('Parameters changed — optimizer reset', 'info');
    };
    if (kOptInput) {
        kOptInput.addEventListener('change', paramHandler);
        kOptInput.addEventListener('input', paramHandler);
    }
    if (synergyInput) {
        synergyInput.addEventListener('change', paramHandler);
        synergyInput.addEventListener('input', paramHandler);
    }
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
function createItemCard(item, isInPool = false) {
    const card = document.createElement('div');
    card.className = 'item-card';
    card.draggable = true;
    card.dataset.itemName = item.name;
    
    // Ensure rarity is valid
    const rarity = (item.rarity || 'white').toString().toLowerCase();
    card.dataset.rarity = rarity;
    
    if (item.in_pool || isInPool) {
        card.classList.add('in-pool');
    }
    
    // Check if item is pinned
    if (pinnedItems.has(item.name)) {
        card.classList.add('pinned');
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
    
    // Add pin indicator if pinned
    if (pinnedItems.has(item.name)) {
        const pinIndicator = document.createElement('div');
        pinIndicator.className = 'pin-indicator';
        pinIndicator.textContent = '📌';
        pinIndicator.title = 'Pinned (won\'t be removed during optimization)';
        card.appendChild(pinIndicator);
    }
    
    // Drag events
    card.addEventListener('dragstart', handleDragStart);
    card.addEventListener('dragend', handleDragEnd);
    card.addEventListener('click', () => showItemDetails(item));
    
    // Right-click to pin/unpin (only for items in pool)
    if (isInPool) {
        card.addEventListener('contextmenu', async (e) => {
            e.preventDefault();
            await togglePinItem(item.name);
        });
    }
    
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
            
            // Reset optimizer state when user manually edits pool
            if (currentOptimizer) {
                currentOptimizer = null;
            }
            // Re-enable manual optimize button after user change
            const nextBtn = document.getElementById('nextIteration');
            if (nextBtn) nextBtn.disabled = false;
            
            // Update scores
            const oldScore = currentScore;
            currentScore = data.score || 0;
            bestScore = Math.max(bestScore, currentScore);
            const delta = currentScore - oldScore;
            
            iterationCount++;
            document.getElementById('iterationCount').textContent = iterationCount;
            
            // Add to history
            addHistoryEntry({
                iteration: iterationCount,
                score: currentScore,
                best_score: bestScore,
                last_swap: {
                    removed: [],
                    added: [itemName]
                },
                delta: delta
            });
            
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
            
            // Unpin item if it was pinned
            if (pinnedItems.has(itemName)) {
                pinnedItems.delete(itemName);
                await fetch('/api/pool/unpin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ item: itemName })
                });
            }
            
            // Reset optimizer state when user manually edits pool
            if (currentOptimizer) {
                currentOptimizer = null;
            }
            // Re-enable manual optimize button after user change
            const nextBtn = document.getElementById('nextIteration');
            if (nextBtn) nextBtn.disabled = false;
            
            // Update scores
            const oldScore = currentScore;
            currentScore = data.score || 0;
            bestScore = Math.max(bestScore, currentScore);
            const delta = currentScore - oldScore;
            
            iterationCount++;
            document.getElementById('iterationCount').textContent = iterationCount;
            
            // Add to history
            addHistoryEntry({
                iteration: iterationCount,
                score: currentScore,
                best_score: bestScore,
                last_swap: {
                    removed: [itemName],
                    added: []
                },
                delta: delta
            });
            
            updateUI();
            showStatus(`Removed ${itemName} from pool`, 'success');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function clearPool() {
    // No confirmation dialog - just clear
    resetOptimization();
    
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


async function togglePinItem(itemName) {
    try {
        const isPinned = pinnedItems.has(itemName);
        const endpoint = isPinned ? '/api/pool/unpin' : '/api/pool/pin';
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item: itemName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Update local state
            if (isPinned) {
                pinnedItems.delete(itemName);
                showStatus(`Unpinned ${itemName}`, 'success');
            } else {
                pinnedItems.add(itemName);
                showStatus(`Pinned ${itemName} (won't be removed during optimization)`, 'success');
            }
            
            // Re-render pool to show pin indicator
            renderPool();
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}


async function updatePlayStyle(style) {
    try {
        const response = await fetch('/api/config/style', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ style: style })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showStatus(`Play style updated to: ${style || 'None'}`, 'success');
            
            // Reset optimizer state when style changes
            if (currentOptimizer) {
                currentOptimizer = null;
            }
            
            // Re-enable manual optimize button
            const nextBtn = document.getElementById('nextIteration');
            if (nextBtn) nextBtn.disabled = false;
            
            // Recalculate score with new style
            await loadPoolState();
            updateUI();
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}



async function generateRandomPool() {
    showStatus('Generating random pool...', 'info');
    
    // Reset optimization state
    resetOptimization();
    
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
async function nextIteration() {
    if (currentPool.length === 0) {
        showStatus('Add items to pool first!', 'warning');
        return;
    }
    
    if (!currentOptimizer) {
        // Initialize optimizer on first iteration
        currentOptimizer = { iteration: 0, config: await getCurrentConfig() };
    }
    
    showStatus('Running iteration...', 'info');
    
    try {
        const response = await fetch('/api/optimize/step', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                pool: currentPool.map(item => item.Name || item.name),
                config: currentOptimizer.config,
                iteration: currentOptimizer.iteration
            })
        });
        
        const data = await response.json();
        
        if (data.improved) {
            // Update pool with improved version
            currentPool = data.pool.map(name => allItems.find(item => item.name === name || item.Name === name)).filter(item => item);
            currentScore = data.score || 0;
            bestScore = Math.max(bestScore, currentScore);
            
            const delta = data.delta || 0;
            
            // Increment iteration counter
            iterationCount++;
            document.getElementById('iterationCount').textContent = iterationCount;
            
            currentOptimizer.iteration = iterationCount;
            
            // Update UI
            renderItems();
            updateUI();
            
            // Add to history
            addHistoryEntry({
                iteration: iterationCount,
                score: currentScore,
                best_score: bestScore,
                last_swap: data.swap,
                delta: delta
            });
            
            showStatus(
                `Iteration ${currentOptimizer.iteration}: Improved to ${currentScore.toFixed(2)} (Δ: +${delta.toFixed(2)})`,
                'success'
            );
        } else {
            showStatus('No improvement found. Pool is optimized!', 'info');
            document.getElementById('nextIteration').disabled = true;
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

function resetOptimization() {
    currentOptimizer = null;
    iterationCount = 0;
    document.getElementById('iterationCount').textContent = '0';
    document.getElementById('historyTable').innerHTML = '';
    // Ensure the manual optimize button is available after a reset
    const nextBtn = document.getElementById('nextIteration');
    if (nextBtn) nextBtn.disabled = false;
    showStatus('Optimization reset', 'info');
}

function updateOptimizationProgress(data) {
    // Update scores
    currentScore = data.score;
    bestScore = data.best_score;
    document.getElementById('currentScore').textContent = currentScore.toFixed(2);
    document.getElementById('bestScore').textContent = bestScore.toFixed(2);
    
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
    const delta = data.delta || (swap && swap.delta) || 0;
    
    let swapHtml = '';
    if (swap) {
        // Create images for removed items
        const removedHtml = swap.removed.map(itemName => {
            const item = allItems.find(it => (it.Name || it.name) === itemName);
            if (item && (item.image || item.Image)) {
                return `<img src="${item.image || item.Image}" alt="${itemName}" title="${itemName}" class="history-item-icon">`;
            }
            return `<span class="history-item-name">${itemName}</span>`;
        }).join(' ');
        
        // Create images for added items
        const addedHtml = swap.added.map(itemName => {
            const item = allItems.find(it => (it.Name || it.name) === itemName);
            if (item && (item.image || item.Image)) {
                return `<img src="${item.image || item.Image}" alt="${itemName}" title="${itemName}" class="history-item-icon">`;
            }
            return `<span class="history-item-name">${itemName}</span>`;
        }).join(' ');
        
        swapHtml = `
            <div class="history-swap">
                <div class="history-removed">${removedHtml}</div>
                <div class="history-arrow">→</div>
                <div class="history-added">${addedHtml}</div>
            </div>
            <div class="history-delta">Δ: ${delta.toFixed(2)}</div>
        `;
    } else {
        swapHtml = '<div>No swap</div>';
    }
    
    entry.innerHTML = `
        <div class="history-header">
            <strong>Iter ${data.iteration}</strong>
            <span>Score: ${(data.score || 0).toFixed(2)}</span>
            <span>Best: ${(data.best_score || 0).toFixed(2)}</span>
        </div>
        ${swapHtml}
    `;
    
    table.insertBefore(entry, table.firstChild);
    
    // Keep only last 20 entries
    while (table.children.length > 20) {
        table.removeChild(table.lastChild);
    }
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
        // Still need to update available items status when pool is empty
        refreshAvailableItemsStatus();
        return;
    }
    
    if (emptyState) emptyState.style.display = 'none';
    
    // Sort pool items by category (damage, utility, healing)
    const sortedPool = sortPoolByCategory([...currentPool]);
    
    sortedPool.forEach(item => {
        // Create card from item data
        const itemData = {
            name: item.Name || item.name,
            rarity: item.Rarity || item.rarity,
            image: item.Image || item.image,
            tags: item.SynergyTags || item.tags || [],
            playstyles: item.Playstyles || item.playstyles || [],
            category: item.Category || item.category || '',
            desc: item.Desc || item.desc || '',
            in_pool: true
        };
        
        const card = createItemCard(itemData, true); // Pass true for isInPool
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
        
        
        poolZone.appendChild(card);
    });
    
    // Update available items to show in_pool status
    refreshAvailableItemsStatus();
}

// Sort pool items by category priority
function sortPoolByCategory(items) {
    const getCategoryScore = (item) => {
        const tags = (item.SynergyTags || item.tags || []).join(',').toLowerCase();
        const categories = (item.Category || item.category || '').toLowerCase();
        const combined = tags + ',' + categories;
        
        // Damage items first
        if (combined.includes('damage') || combined.includes('on-kill') || combined.includes('onkilleffect')) return 0;
        // Movement/utility items second  
        if (combined.includes('utility') || combined.includes('movement') || combined.includes('speed')) return 1;
        // Healing/defense third
        if (combined.includes('healing') || combined.includes('health') || combined.includes('barrier')) return 2;
        // Everything else
        return 3;
    };
    
    return items.sort((a, b) => {
        const scoreA = getCategoryScore(a);
        const scoreB = getCategoryScore(b);
        
        if (scoreA !== scoreB) {
            return scoreA - scoreB;
        }
        // Secondary sort by name
        const nameA = a.Name || a.name || '';
        const nameB = b.Name || b.name || '';
        return nameA.localeCompare(nameB);
    });
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
    const isRunning = currentOptimizer !== null;
    document.getElementById('nextIteration').disabled = currentPool.length === 0;
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

    // Use pre-cleaned description from server, fall back to raw desc
    const desc = item.clean_desc || item.desc || 'No description available';
    const stats = item.stats || '';
    const category = item.category || 'Unknown';
    const dlc = item.dlc || 'Base';

    // Rarity colour mapping
    const rarityColors = {
        white: '#FFFFFF', green: '#50C878', red: '#FF4500',
        yellow: '#FFD700', blue: '#6699FF', purple: '#800080',
        orange: '#FFA500'
    };
    const rarityColor = rarityColors[(item.rarity || 'white').toLowerCase()] || '#e0e0e0';
    const rarityLabel = item.csv_rarity || item.rarity || 'Unknown';

    const imgHtml = item.image
        ? `<img src="${item.image}" alt="${item.name}" style="width:64px;height:64px;margin-right:12px;vertical-align:middle;">`
        : '';

    body.innerHTML = `
        <div style="display:flex;align-items:center;margin-bottom:12px">
            ${imgHtml}
            <div>
                <h2 style="margin:0;color:${rarityColor}">${item.name}</h2>
                <span style="color:${rarityColor};font-size:0.9em">${rarityLabel}</span>
                ${dlc !== 'Base' ? `<span style="margin-left:8px;font-size:0.8em;color:#888">[${dlc}]</span>` : ''}
            </div>
        </div>
        <p style="color:#ccc;line-height:1.5">${desc}</p>
        ${stats ? `<p><strong>Stats:</strong> ${stats}</p>` : ''}
        <p><strong>Category:</strong> ${category}</p>
        <p><strong>Tags:</strong> ${(item.tags || []).join(', ') || 'None'}</p>
        <p><strong>Playstyles:</strong> ${(item.playstyles || []).join(', ') || 'None'}</p>
    `;

    modal.classList.add('show');
}

// Get current configuration from UI
async function getCurrentConfig() {
    const baseConfig = await fetch('/api/config').then(r => r.json());
    
    return {
        ...baseConfig,
        style: document.getElementById('playStyle').value || baseConfig.style || '',
        synergy_weight: parseFloat(document.getElementById('synergyWeight').value) || 0.5,
        style_weight: parseFloat(document.getElementById('styleWeight').value) || 8.0,
        diversity_weight: parseFloat(document.getElementById('diversityWeight').value) || 1.0,
        coverage_weight: parseFloat(document.getElementById('coverageWeight').value) || 1.0,
        balance_weight: parseFloat(document.getElementById('balanceWeight').value) || 5.0,
        pinned_items: Array.from(pinnedItems),
        optimization: {
            ...(baseConfig.optimization || {}),
            k_opt: parseInt(document.getElementById('kOpt').value) || 1,
            cross_rarity: document.getElementById('crossRarity').checked
        }
    };
}
