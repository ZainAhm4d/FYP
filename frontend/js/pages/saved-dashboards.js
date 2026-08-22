/**
 * Saved Dashboards Page
 * Displays list of user's saved dashboards with view/delete options
 */

// Global variables
let dashboards = [];
let dashboardToDelete = null;
let dashboardToEdit = null;
let importPendingData = null;

/**
 * Initialize saved dashboards page
 */
function initSavedDashboardsPage() {
    console.log('Initializing Saved Dashboards page...');
    
    // Setup event listeners
    setupEventListeners();
    
    // Load dashboards
    loadDashboards();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Edit modal buttons
    const closeEditModalBtn = document.getElementById('closeEditModalBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    const editDashboardForm = document.getElementById('editDashboardForm');
    const editDescInput = document.getElementById('editDashboardDescription');
    const editDescCharCount = document.getElementById('editDescCharCount');

    if (closeEditModalBtn) closeEditModalBtn.addEventListener('click', closeEditModal);
    if (cancelEditBtn) cancelEditBtn.addEventListener('click', closeEditModal);
    if (editDashboardForm) editDashboardForm.addEventListener('submit', handleEditDashboard);
    if (editDescInput && editDescCharCount) {
        editDescInput.addEventListener('input', () => {
            editDescCharCount.textContent = editDescInput.value.length;
        });
    }

    // Import button + file input
    const importDashboardBtn = document.getElementById('importDashboardBtn');
    const importFileInput = document.getElementById('importFileInput');
    const closeImportModalBtn = document.getElementById('closeImportModalBtn');
    const cancelImportBtn = document.getElementById('cancelImportBtn');
    const confirmImportBtn = document.getElementById('confirmImportBtn');

    if (importDashboardBtn) {
        importDashboardBtn.addEventListener('click', () => importFileInput && importFileInput.click());
    }
    if (importFileInput) {
        importFileInput.addEventListener('change', handleImportFile);
    }
    if (closeImportModalBtn) {
        closeImportModalBtn.addEventListener('click', closeImportModal);
    }
    if (cancelImportBtn) {
        cancelImportBtn.addEventListener('click', closeImportModal);
    }
    if (confirmImportBtn) {
        confirmImportBtn.addEventListener('click', confirmImport);
    }

    // Delete modal buttons
    const closeDeleteModalBtn = document.getElementById('closeDeleteModalBtn');
    const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    
    if (closeDeleteModalBtn) {
        closeDeleteModalBtn.addEventListener('click', closeDeleteModal);
    }
    
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', closeDeleteModal);
    }
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', confirmDelete);
    }
}

/**
 * Load dashboards from API
 */
async function loadDashboards() {
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');
    const dashboardsGrid = document.getElementById('dashboardsGrid');
    
    try {
        console.log('Fetching dashboards from API...');
        
        // Show loading skeleton
        if (dashboardsGrid) {
            SkeletonLoader.show(dashboardsGrid, 'dashboardGrid', { count: 6 });
        }
        if (emptyState) emptyState.classList.add('hidden');
        if (loadingState) loadingState.classList.add('hidden');
        
        // Fetch dashboards from API
        const response = await API.get('/dashboards', true);
        
        console.log('Dashboards loaded:', response);
        
        dashboards = response;
        
        // Update count badge
        updateDashboardCount();
        
        if (dashboards.length === 0) {
            // Show empty state
            if (dashboardsGrid) {
                EmptyStates.show(dashboardsGrid, 'noDashboards');
            }
        } else {
            // Render dashboards
            renderDashboards();
        }
        
    } catch (error) {
        console.error('Error loading dashboards:', error);
        
        // Check if it's a 404 (not implemented yet) - try localStorage fallback
        if (error.message && error.message.includes('404')) {
            console.log('API not available, checking localStorage...');
            loadDashboardsFromLocalStorage();
        } else {
            Notifications.error('Failed to load dashboards: ' + (error.message || 'Unknown error'));
            
            // Show empty state
            if (dashboardsGrid) {
                EmptyStates.show(dashboardsGrid, 'noDashboards');
            }
        }
    }
}

/**
 * Load dashboards from localStorage (fallback)
 */
function loadDashboardsFromLocalStorage() {
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');
    const dashboardsGrid = document.getElementById('dashboardsGrid');
    
    console.log('Loading dashboards from localStorage...');
    
    // Get saved dashboards from localStorage
    const savedDashboards = Storage.get(Storage.userKey('savedDashboards')) || [];
    
    dashboards = savedDashboards;
    
    // Hide loading state
    if (loadingState) loadingState.classList.add('hidden');
    
    // Update count badge
    updateDashboardCount();
    
    if (dashboards.length === 0) {
        // Show empty state
        if (dashboardsGrid) {
            EmptyStates.show(dashboardsGrid, 'noDashboards');
        }
    } else {
        // Render dashboards
        renderDashboards();
        
        // Show info about local storage
        Notifications.warning('Showing locally stored dashboards. Backend API will be available soon.');
    }
}

/**
 * Update dashboard count badge
 */
function updateDashboardCount() {
    const countSpan = document.getElementById('dashboardCount');
    if (countSpan) {
        countSpan.textContent = dashboards.length;
    }
}

/**
 * Render dashboards grid
 */
function renderDashboards() {
    const dashboardsGrid = document.getElementById('dashboardsGrid');
    
    if (!dashboardsGrid) return;
    
    // Clear grid
    dashboardsGrid.innerHTML = '';
    
    // Render each dashboard card
    dashboards.forEach(dashboard => {
        const card = createDashboardCard(dashboard);
        dashboardsGrid.appendChild(card);
    });
}

/**
 * Create dashboard card element
 */
function createDashboardCard(dashboard) {
    const card = document.createElement('div');
    card.className = 'card bg-white shadow hover:shadow-lg transition-shadow cursor-pointer';
    
    // Format dates
    const createdDate = new Date(dashboard.created_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
    
    const updatedDate = new Date(dashboard.updated_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
    
    card.innerHTML = `
        <div class="flex items-start justify-between mb-3">
            <div class="flex-1">
                <h3 class="text-xl font-bold text-gray-800 mb-1">${escapeHtml(dashboard.name)}</h3>
                ${dashboard.description ? `<p class="text-sm text-gray-600 mb-2">${escapeHtml(dashboard.description)}</p>` : ''}
            </div>
            <button 
                class="edit-btn text-gray-400 hover:text-blue-500 p-2 rounded hover:bg-blue-50 transition"
                data-dashboard-id="${dashboard.id}"
                title="Edit dashboard"
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                </svg>
            </button>
            <button 
                class="delete-btn text-gray-400 hover:text-red-500 p-2 rounded hover:bg-red-50 transition"
                data-dashboard-id="${dashboard.id}"
                data-dashboard-name="${escapeHtml(dashboard.name)}"
                title="Delete dashboard"
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
            </button>
        </div>
        
        <div class="flex items-center gap-4 mb-4 text-sm text-gray-500">
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"></path>
                </svg>
                <span>${dashboard.chart_count || 0} charts</span>
            </div>
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                </svg>
                <span>Created ${createdDate}</span>
            </div>
        </div>
        
        <div class="flex gap-2">
            <button 
                class="view-btn btn btn-primary flex-1"
                data-dashboard-id="${dashboard.id}"
            >
                <svg class="w-4 h-4 mr-2 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
                View Dashboard
            </button>
            <button 
                class="export-btn btn btn-outline"
                data-dashboard-id="${dashboard.id}"
                title="Export dashboard data"
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                </svg>
            </button>
        </div>
    `;
    
    // Add event listeners
    const viewBtn = card.querySelector('.view-btn');
    const editBtn = card.querySelector('.edit-btn');
    const deleteBtn = card.querySelector('.delete-btn');
    const exportBtn = card.querySelector('.export-btn');
    
    if (viewBtn) {
        viewBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            viewDashboard(dashboard.id);
        });
    }

    if (editBtn) {
        editBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openEditModal(dashboard.id, dashboard.name, dashboard.description || '');
        });
    }
    
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openDeleteModal(dashboard.id, dashboard.name);
        });
    }
    
    if (exportBtn) {
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportDashboard(dashboard.id);
        });
    }
    
    return card;
}

/**
 * View dashboard
 */
function viewDashboard(dashboardId) {
    console.log('Viewing dashboard:', dashboardId);
    
    // Navigate to dashboard view page
    window.location.href = `view-dashboard.html?id=${dashboardId}`;
}

/**
 * Open delete confirmation modal
 */
function openDeleteModal(dashboardId, dashboardName) {
    const modal = document.getElementById('deleteModal');
    const nameSpan = document.getElementById('deleteDashboardName');
    
    if (!modal || !nameSpan) return;
    
    dashboardToDelete = dashboardId;
    nameSpan.textContent = dashboardName;
    
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

/**
 * Close delete confirmation modal
 */
function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    
    if (!modal) return;
    
    dashboardToDelete = null;
    
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

/**
 * Confirm delete dashboard
 */
async function confirmDelete() {
    if (!dashboardToDelete) return;
    
    console.log('Deleting dashboard:', dashboardToDelete);
    
    try {
        // Show loading
        Loading.show('Deleting dashboard...');
        
        // Delete from API
        await API.delete(`/dashboards/${dashboardToDelete}`, true);
        
        console.log('Dashboard deleted successfully');
        
        // Close modal
        closeDeleteModal();
        
        // Show success notification
        Notifications.success('Dashboard deleted successfully');
        
        // Reload dashboards
        loadDashboards();
        
    } catch (error) {
        console.error('Error deleting dashboard:', error);
        
        // Check if it's a 404 (not implemented yet) - try localStorage
        if (error.message && error.message.includes('404')) {
            console.log('API not available, deleting from localStorage...');
            deleteFromLocalStorage(dashboardToDelete);
        } else {
            Notifications.error('Failed to delete dashboard: ' + (error.message || 'Unknown error'));
        }
    } finally {
        Loading.hide();
    }
}

/**
 * Delete dashboard from localStorage (fallback)
 */
function deleteFromLocalStorage(dashboardId) {
    const savedDashboards = Storage.get(Storage.userKey('savedDashboards')) || [];
    
    const updatedDashboards = savedDashboards.filter(d => d.id !== dashboardId);
    
    Storage.set(Storage.userKey('savedDashboards'), updatedDashboards);
    
    // Close modal
    closeDeleteModal();
    
    // Show success notification
    Notifications.success('Dashboard deleted successfully (local storage)');
    
    // Reload dashboards
    loadDashboardsFromLocalStorage();
}

/**
 * Export dashboard data
 */
async function exportDashboard(dashboardId) {
    console.log('Exporting dashboard:', dashboardId);
    
    try {
        // Show loading
        Loading.show('Exporting dashboard...');
        
        // Get dashboard data from API
        const exportData = await API.get(`/dashboards/${dashboardId}/export`, true);
        
        console.log('Export data:', exportData);
        
        // Convert to JSON string
        const jsonString = JSON.stringify(exportData, null, 2);
        
        // Create blob and download
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${exportData.dashboard_name.replace(/\s+/g, '_')}_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        Notifications.success('Dashboard exported successfully');
        
    } catch (error) {
        console.error('Error exporting dashboard:', error);
        
        // Fallback: export from current data
        if (error.message && error.message.includes('404')) {
            exportFromLocalData(dashboardId);
        } else {
            Notifications.error('Failed to export dashboard: ' + (error.message || 'Unknown error'));
        }
    } finally {
        Loading.hide();
    }
}

/**
 * Export dashboard from local data (fallback)
 */
function exportFromLocalData(dashboardId) {
    const dashboard = dashboards.find(d => d.id === dashboardId);
    
    if (!dashboard) {
        Notifications.error('Dashboard not found');
        return;
    }
    
    const exportData = {
        dashboard_name: dashboard.name,
        exported_at: new Date().toISOString(),
        charts: dashboard.config_json?.charts || [],
        data: {
            description: dashboard.description,
            layout: dashboard.config_json?.layout || 'grid',
            chart_count: dashboard.chart_count || 0,
            created_at: dashboard.created_at,
            updated_at: dashboard.updated_at
        }
    };
    
    const jsonString = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${dashboard.name.replace(/\s+/g, '_')}_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    Notifications.success('Dashboard exported successfully (local data)');
}

/**
 * Open edit dashboard modal
 */
function openEditModal(dashboardId, name, description) {
    dashboardToEdit = dashboardId;

    const nameInput = document.getElementById('editDashboardName');
    const descInput = document.getElementById('editDashboardDescription');
    const charCount = document.getElementById('editDescCharCount');

    if (nameInput) nameInput.value = name;
    if (descInput) {
        descInput.value = description;
        if (charCount) charCount.textContent = description.length;
    }

    const modal = document.getElementById('editModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    setTimeout(() => nameInput && nameInput.focus(), 100);
}

/**
 * Close edit dashboard modal
 */
function closeEditModal() {
    const modal = document.getElementById('editModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    dashboardToEdit = null;
}

/**
 * Handle edit form submission
 */
async function handleEditDashboard(e) {
    e.preventDefault();
    if (!dashboardToEdit) return;

    const name = document.getElementById('editDashboardName').value.trim();
    const description = document.getElementById('editDashboardDescription').value.trim();

    if (!name) {
        Notifications.error('Dashboard name is required');
        return;
    }

    try {
        Loading.show('Saving changes...');

        await API.put(`/dashboards/${dashboardToEdit}`, { name, description }, true);

        closeEditModal();
        Notifications.success('Dashboard updated successfully!');
        loadDashboards();

    } catch (error) {
        console.error('Edit error:', error);
        Notifications.error('Failed to update dashboard: ' + (error.message || 'Unknown error'));
    } finally {
        Loading.hide();
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * Handle imported JSON file selection
 */
function handleImportFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
        try {
            const data = JSON.parse(evt.target.result);

            // Support both export format { dashboard_name, charts, data } and raw save format { name, config_json }
            const name = data.dashboard_name || data.name;
            const charts = data.charts || data.config_json?.charts || [];
            const description = data.data?.description || data.description || '';
            const layout = data.data?.layout || data.config_json?.layout || 'grid';

            // CH-12: accept only this app's exports — each chart entry must
            // carry something renderable, not just any JSON with a name.
            if (!name || !Array.isArray(charts) || charts.length === 0) {
                Notifications.error('Invalid dashboard file — this importer accepts dashboards exported from this app (.json).');
                return;
            }
            const renderable = (c) => c && typeof c === 'object'
                && (c.plotlySpec || c.plotly_spec || c.chart || c.chart_config || c.config);
            if (!charts.every(renderable)) {
                Notifications.error('Invalid dashboard file — one or more charts are missing their chart data. Export the dashboard from this app and import that file.');
                return;
            }
            if (data.schema_version && data.schema_version > 1) {
                (Notifications.warning || Notifications.error)(
                    `This file was exported by a newer version (schema v${data.schema_version}) — some settings may not import.`);
            }

            importPendingData = { name, description, charts, layout };

            // Show confirmation modal
            document.getElementById('importFileName').textContent = file.name;
            document.getElementById('importDashboardName').textContent = name;
            document.getElementById('importChartCount').textContent = charts.length;

            const modal = document.getElementById('importModal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');

        } catch (err) {
            Notifications.error('Could not parse file — make sure it is a valid dashboard JSON');
        }
        // Reset so same file can be re-selected
        e.target.value = '';
    };
    reader.readAsText(file);
}

/**
 * Close import confirmation modal
 */
function closeImportModal() {
    const modal = document.getElementById('importModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    importPendingData = null;
}

/**
 * Confirm and save the imported dashboard
 */
async function confirmImport() {
    if (!importPendingData) return;

    const nameToShow = importPendingData.name;

    try {
        Loading.show('Importing dashboard...');

        const dashboardData = {
            name: importPendingData.name,
            description: importPendingData.description,
            config_json: {
                layout: importPendingData.layout,
                charts: importPendingData.charts,
                created_at: new Date().toISOString(),
                chart_count: importPendingData.charts.length
            }
        };

        await API.post('/dashboards', dashboardData, true);

        closeImportModal();
        Notifications.success(`Dashboard "${nameToShow}" imported successfully!`);
        loadDashboards();

    } catch (error) {
        console.error('Import error:', error);
        Notifications.error('Failed to import dashboard: ' + (error.message || 'Unknown error'));
    } finally {
        Loading.hide();
    }
}

/**
 * Initialize page when DOM is loaded
 */
document.addEventListener('DOMContentLoaded', () => {
    initSavedDashboardsPage();
});

