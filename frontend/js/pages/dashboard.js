/**
 * Dashboard Builder Page
 * Loads pending charts from localStorage, displays them in a grid,
 * and allows users to save the complete dashboard configuration.
 */

// Global variables
let pendingCharts = [];
let currentLayout = 'grid';

/**
 * Called by DashboardLayout when a chart is removed via the X button.
 * Syncs pendingCharts array, localStorage, and the count badge.
 */
function onChartRemoved(chartId) {
    pendingCharts = pendingCharts.filter(c => c.id !== chartId);
    Storage.set(Storage.userKey('pendingDashboardCharts'), pendingCharts);
    updateUIState();
    if (pendingCharts.length === 0) {
        showEmptyState();
    }
}

/**
 * Initialize dashboard page
 */
let _dashPageInitialized = false;

function initDashboardPage() {
    // Guard against double initialization (two DOMContentLoaded registrations
    // used to render every staged chart twice).
    if (_dashPageInitialized) return;
    _dashPageInitialized = true;
    console.log('Initializing Dashboard Builder page...');

    // Initialize dashboard layout
    window.dashboardLayout = new window.DashboardLayout('dashboardGrid', {
        minChartHeight: 350,
        chartSpacing: 16,
        enableResize: true,
        enableRemove: true,
        enableFullscreen: false,
        layout: 'grid'
    });
    
    // Load pending charts from localStorage
    loadPendingCharts();
    
    // Setup event listeners
    setupEventListeners();
    
    // Update UI state
    updateUIState();
    
    console.log('Dashboard Builder initialized successfully');
}

/**
 * Load pending charts from localStorage
 */
function loadPendingCharts() {
    console.log('Loading pending charts from localStorage...');
    
    try {
        // Retrieve pending charts from localStorage
        pendingCharts = Storage.get(Storage.userKey('pendingDashboardCharts')) || [];

        // Drop exact duplicates that accumulated from repeated "Add to
        // Dashboard" clicks in earlier sessions (same chart staged twice).
        const seen = new Set();
        const unique = pendingCharts.filter(c => {
            const key = `${c.title}|${JSON.stringify(c.plotlySpec?.data ?? '')}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
        if (unique.length !== pendingCharts.length) {
            console.log(`Removed ${pendingCharts.length - unique.length} duplicate staged chart(s)`);
            pendingCharts = unique;
            Storage.set(Storage.userKey('pendingDashboardCharts'), pendingCharts);
        }

        console.log(`Found ${pendingCharts.length} pending charts`);
        
        if (pendingCharts.length === 0) {
            showEmptyState();
            return;
        }
        
        // Hide empty state
        hideEmptyState();
        
        // Add each chart to the dashboard
        pendingCharts.forEach((chartConfig, index) => {
            try {
                console.log(`Adding chart ${index + 1}: ${chartConfig.title}`);
                
                // Add chart to dashboard layout
                const chartId = window.dashboardLayout.addChart({
                    id: chartConfig.id,
                    title: chartConfig.title,
                    plotlySpec: chartConfig.plotlySpec,
                    size: chartConfig.size || 'medium'
                });
                
                console.log(`Chart added with ID: ${chartId}`);
            } catch (error) {
                console.error(`Error adding chart ${index + 1}:`, error);
                Notifications.error(`Failed to add chart: ${chartConfig.title}`);
            }
        });
        
        // Update UI state
        updateUIState();
        
        console.log('All pending charts loaded successfully');
        
    } catch (error) {
        console.error('Error loading pending charts:', error);
        Notifications.error('Failed to load pending charts');
        showEmptyState();
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Save Dashboard button
    const saveDashboardBtn = document.getElementById('saveDashboardBtn');
    if (saveDashboardBtn) {
        saveDashboardBtn.addEventListener('click', openSaveDashboardModal);
    }
    
    // Clear Dashboard button
    const clearDashboardBtn = document.getElementById('clearDashboardBtn');
    if (clearDashboardBtn) {
        clearDashboardBtn.addEventListener('click', clearDashboard);
    }
    
    // Change Layout button
    const changeLayoutBtn = document.getElementById('changeLayoutBtn');
    if (changeLayoutBtn) {
        changeLayoutBtn.addEventListener('click', openLayoutModal);
    }
    
    // Save Dashboard Modal
    const saveDashboardForm = document.getElementById('saveDashboardForm');
    if (saveDashboardForm) {
        saveDashboardForm.addEventListener('submit', handleSaveDashboard);
    }
    
    const closeModalBtn = document.getElementById('closeModalBtn');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeSaveDashboardModal);
    }
    
    const cancelModalBtn = document.getElementById('cancelModalBtn');
    if (cancelModalBtn) {
        cancelModalBtn.addEventListener('click', closeSaveDashboardModal);
    }
    
    // Layout Modal
    const closeLayoutModalBtn = document.getElementById('closeLayoutModalBtn');
    if (closeLayoutModalBtn) {
        closeLayoutModalBtn.addEventListener('click', closeLayoutModal);
    }
    
    // Layout options
    const layoutOptions = document.querySelectorAll('.layout-option');
    layoutOptions.forEach(option => {
        option.addEventListener('click', handleLayoutChange);
    });
    
    // Description character counter
    const descriptionInput = document.getElementById('dashboardDescription');
    const charCountSpan = document.getElementById('descCharCount');
    if (descriptionInput && charCountSpan) {
        descriptionInput.addEventListener('input', (e) => {
            charCountSpan.textContent = e.target.value.length;
        });
    }
}

/**
 * Update UI state (button enabled/disabled, chart count)
 */
function updateUIState() {
    const chartCount = pendingCharts.length;
    
    // Update chart count badge
    const chartCountSpan = document.getElementById('chartCount');
    if (chartCountSpan) {
        chartCountSpan.textContent = chartCount;
    }
    
    // Enable/disable Save Dashboard button
    const saveDashboardBtn = document.getElementById('saveDashboardBtn');
    if (saveDashboardBtn) {
        if (chartCount > 0) {
            saveDashboardBtn.disabled = false;
            saveDashboardBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            saveDashboardBtn.disabled = true;
            saveDashboardBtn.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
    
    // Enable/disable Clear Dashboard button
    const clearDashboardBtn = document.getElementById('clearDashboardBtn');
    if (clearDashboardBtn) {
        if (chartCount > 0) {
            clearDashboardBtn.disabled = false;
            clearDashboardBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            clearDashboardBtn.disabled = true;
            clearDashboardBtn.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
    
    // Enable/disable Change Layout button
    const changeLayoutBtn = document.getElementById('changeLayoutBtn');
    if (changeLayoutBtn) {
        if (chartCount > 0) {
            changeLayoutBtn.disabled = false;
            changeLayoutBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            changeLayoutBtn.disabled = true;
            changeLayoutBtn.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
}

/**
 * Show empty state
 */
function showEmptyState() {
    const emptyState = document.getElementById('emptyState');
    const dashboardGrid = document.getElementById('dashboardGrid');

    if (emptyState) {
        emptyState.classList.remove('hidden');
    }

    if (dashboardGrid) {
        dashboardGrid.classList.add('hidden');
    }
}

/**
 * Hide empty state
 */
function hideEmptyState() {
    const emptyState = document.getElementById('emptyState');
    const dashboardGrid = document.getElementById('dashboardGrid');

    if (emptyState) {
        emptyState.classList.add('hidden');
    }

    if (dashboardGrid) {
        dashboardGrid.classList.remove('hidden');
    }
}

/**
 * Open Save Dashboard Modal
 */
function openSaveDashboardModal() {
    const modal = document.getElementById('saveDashboardModal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        
        // Focus on name input
        const nameInput = document.getElementById('dashboardName');
        if (nameInput) {
            setTimeout(() => nameInput.focus(), 100);
        }
    }
}

/**
 * Close Save Dashboard Modal
 */
function closeSaveDashboardModal() {
    const modal = document.getElementById('saveDashboardModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        
        // Reset form
        const form = document.getElementById('saveDashboardForm');
        if (form) {
            form.reset();
            document.getElementById('descCharCount').textContent = '0';
        }
    }
}

/**
 * Handle Save Dashboard form submission
 */
async function handleSaveDashboard(e) {
    e.preventDefault();
    
    const nameInput = document.getElementById('dashboardName');
    const descInput = document.getElementById('dashboardDescription');
    
    const dashboardName = nameInput.value.trim();
    const dashboardDescription = descInput.value.trim();
    
    if (!dashboardName) {
        Notifications.error('Please enter a dashboard name');
        return;
    }
    
    console.log('Saving dashboard:', dashboardName);
    
    try {
        // Show loading state
        Loading.show('Saving dashboard...');
        
        // Get dashboard configuration
        const dashboardConfig = window.dashboardLayout.getDashboardConfig();
        
        // Use live layout charts (not pendingCharts) so removed charts are excluded
        const currentCharts = window.dashboardLayout.charts.map(c => c.config);
        
        // Prepare dashboard data for API
        const dashboardData = {
            name: dashboardName,
            description: dashboardDescription,
            config_json: {
                layout: dashboardConfig.layout,
                charts: currentCharts,
                created_at: new Date().toISOString(),
                chart_count: currentCharts.length
            }
        };
        
        console.log('Dashboard data:', dashboardData);
        
        // Save to backend API
        const response = await API.post('/dashboards', dashboardData, true);
        
        console.log('Dashboard saved successfully:', response);
        
        // Clear pending charts from localStorage
        Storage.remove(Storage.userKey('pendingDashboardCharts'));
        
        // Close modal
        closeSaveDashboardModal();
        
        // Show success notification
        Notifications.success(`Dashboard "${dashboardName}" saved successfully!`);
        
        // Wait a moment then redirect to saved dashboards page
        setTimeout(() => {
            window.location.href = 'saved-dashboards.html';
        }, 2000);
        
    } catch (error) {
        console.error('Error saving dashboard:', error);
        
        // Check if error is due to missing API endpoint (Day 6 feature)
        if (error.message && error.message.includes('404')) {
            Notifications.warning('Dashboard save API not yet implemented (Coming in Day 6). Your dashboard is stored locally for now.');
            
            // Store locally for now
            const savedDashboards = Storage.get(Storage.userKey('savedDashboards')) || [];
            const currentCharts = window.dashboardLayout.charts.map(c => c.config);
            savedDashboards.push({
                id: Date.now(),
                name: dashboardName,
                description: dashboardDescription,
                config_json: {
                    layout: window.dashboardLayout.getDashboardConfig().layout,
                    charts: currentCharts
                },
                created_at: new Date().toISOString()
            });
            Storage.set(Storage.userKey('savedDashboards'), savedDashboards);
            
            // Clear pending charts
            Storage.remove(Storage.userKey('pendingDashboardCharts'));
            
            // Close modal
            closeSaveDashboardModal();
            
            // Redirect after delay
            setTimeout(() => {
                window.location.href = 'saved-dashboards.html';
            }, 2000);
        } else {
            Notifications.error('Failed to save dashboard: ' + (error.message || 'Unknown error'));
        }
    } finally {
        Loading.hide();
    }
}

/**
 * Clear all charts from dashboard
 */
function clearDashboard() {
    if (pendingCharts.length === 0) {
        return;
    }
    
    // Confirm with user
    const confirmed = confirm('Are you sure you want to clear all charts? This action cannot be undone.');
    
    if (!confirmed) {
        return;
    }
    
    console.log('Clearing dashboard...');
    
    try {
        // Clear dashboard layout
        window.dashboardLayout.clearDashboard();
        
        // Clear pending charts from localStorage
        Storage.remove(Storage.userKey('pendingDashboardCharts'));
        
        // Reset pending charts array
        pendingCharts = [];
        
        // Show empty state
        showEmptyState();
        
        // Update UI state
        updateUIState();
        
        Notifications.success('Dashboard cleared successfully');
        
        console.log('Dashboard cleared');
        
    } catch (error) {
        console.error('Error clearing dashboard:', error);
        Notifications.error('Failed to clear dashboard');
    }
}

/**
 * Open Layout Modal
 */
function openLayoutModal() {
    const modal = document.getElementById('layoutModal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
}

/**
 * Close Layout Modal
 */
function closeLayoutModal() {
    const modal = document.getElementById('layoutModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
}

/**
 * Handle layout change
 */
function handleLayoutChange(e) {
    const layoutType = e.currentTarget.dataset.layout;
    
    if (!layoutType) {
        return;
    }
    
    console.log('Changing layout to:', layoutType);
    
    try {
        // Update layout
        window.dashboardLayout.setLayout(layoutType);
        
        // Store current layout
        currentLayout = layoutType;
        
        // Close modal
        closeLayoutModal();
        
        // Show success notification
        Notifications.success(`Layout changed to ${layoutType}`);
        
    } catch (error) {
        console.error('Error changing layout:', error);
        Notifications.error('Failed to change layout');
    }
}

/**
 * Initialize page when DOM is loaded
 */
document.addEventListener('DOMContentLoaded', () => {
    // Check if DashboardLayout is available
    if (!window.DashboardLayout) {
        console.error('DashboardLayout module not loaded!');
        Notifications.error('Failed to load dashboard components. Please refresh the page.');
        return;
    }
    
    // Initialize dashboard page
    initDashboardPage();
});
