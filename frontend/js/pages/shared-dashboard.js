/**
 * Shared Dashboard — Public View
 * Loads a dashboard via share token, no authentication required.
 */

async function initSharedDashboard() {
    const params = new URLSearchParams(window.location.search);
    const token  = params.get('token');

    if (!token) {
        showError('No share token provided', 'Please check the link you were given.');
        return;
    }

    try {
        const dashboard = await API.get(`/dashboards/shared/${token}`, false);
        renderSharedDashboard(dashboard);
    } catch (err) {
        const is404 = err.message && (err.message.includes('404') || err.message.includes('not found'));
        if (is404) {
            showError(
                'Dashboard not available',
                'This dashboard may have been made private or the link is invalid.',
            );
        } else {
            showError('Failed to load dashboard', err.message || 'Unknown error');
        }
    }
}

let _sharedDashboard = null;
let _sharedActivePage = 0;

function renderSharedDashboard(dashboard) {
    _sharedDashboard = dashboard;

    // Update metadata
    document.title = `${dashboard.name} — BI Dashboard Generator`;
    document.getElementById('dashboardTitle').textContent = dashboard.name;
    document.getElementById('dashboardDescription').textContent = dashboard.description || '';

    const allCharts = dashboard.config_json?.charts || [];
    const chartOnly = allCharts.filter(c => (c.widget_type || 'chart') === 'chart');
    document.getElementById('chartCount').textContent =
        `${chartOnly.length} chart${chartOnly.length === 1 ? '' : 's'}`;
    document.getElementById('viewCount').textContent =
        `${dashboard.view_count} view${dashboard.view_count === 1 ? '' : 's'}`;

    // Saved theme (page chrome; Plotly patching happens in the layout engine)
    const theme = dashboard.config_json?.theme || 'light';
    document.body.classList.toggle('theme-dark', theme === 'dark');

    // Saved design (canvas/cards/banner CSS — palette applied at render below)
    const PALETTES = {
        indigo:    ['#4F46E5', '#818CF8', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'],
        ocean:     ['#0284c7', '#06b6d4', '#14b8a6', '#38bdf8', '#0ea5e9', '#22d3ee'],
        forest:    ['#16a34a', '#0d9488', '#65a30d', '#22c55e', '#84cc16', '#4ade80'],
        sunset:    ['#f97316', '#ef4444', '#f59e0b', '#ec4899', '#fb923c', '#facc15'],
        corporate: ['#1e40af', '#3b82f6', '#0f766e', '#60a5fa', '#334155', '#93c5fd'],
    };
    const design = { ...(dashboard.config_json?.design || {}) };
    design.paletteColors = PALETTES[design.palette] || null;
    _sharedDesign = design;
    if (window.applyDashboardDesignCSS) window.applyDashboardDesignCSS(design);

    // Hide loading, show content
    document.getElementById('loadingState').classList.add('hidden');
    document.getElementById('dashboardContent').classList.remove('hidden');

    if (allCharts.length === 0) {
        document.getElementById('dashboardGrid').innerHTML =
            '<p class="text-gray-400 text-center py-16">This dashboard has no charts.</p>';
        return;
    }

    _renderSharedPage();
}

/** Pages partition (read-only mirror of the editor's model). */
function _sharedPages() {
    const cfg = _sharedDashboard.config_json;
    const pages = (Array.isArray(cfg.pages) && cfg.pages.length > 0)
        ? cfg.pages
        : [{ name: 'Page 1', chartIds: (cfg.charts || []).map(c => c.id) }];
    // Any chart not assigned to a page belongs to the first one
    const assigned = new Set(pages.flatMap(p => p.chartIds || []));
    const orphans = (cfg.charts || []).filter(c => !assigned.has(c.id)).map(c => c.id);
    if (orphans.length) pages[0] = { ...pages[0], chartIds: [...(pages[0].chartIds || []), ...orphans] };
    return pages;
}

function _renderSharedTabs(pages) {
    const bar = document.getElementById('pageTabBar');
    if (!bar) return;
    if (pages.length <= 1) { bar.classList.add('hidden'); return; }
    const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    bar.classList.remove('hidden');
    bar.innerHTML = pages.map((p, i) => `
        <div class="dash-tab ${i === _sharedActivePage ? 'active' : ''}" onclick="switchSharedPage(${i})">
            <span>${esc(p.name)}</span>
        </div>`).join('');
}

function switchSharedPage(i) {
    if (i === _sharedActivePage) return;
    _sharedActivePage = i;
    _renderSharedPage();
}

let _sharedLayout = null;
let _sharedDesign = null;

function _renderSharedPage() {
    const cfg = _sharedDashboard.config_json;
    const pages = _sharedPages();
    if (_sharedActivePage >= pages.length) _sharedActivePage = 0;
    _renderSharedTabs(pages);

    const pageIds = new Set(pages[_sharedActivePage].chartIds || []);
    const allCharts = cfg.charts || [];
    const charts = allCharts.filter(c => pageIds.has(c.id));

    // Static gridstack: saved positions render exactly as in the editor,
    // but nothing is draggable. Falls back to the CSS grid if the CDN failed.
    // One instance is reused across page switches (re-initializing gridstack
    // on the same container leaks stale state).
    if (!_sharedLayout) {
        _sharedLayout = new window.DashboardLayout('dashboardGrid', {
            minChartHeight: 350,
            chartSpacing: 16,
            enableResize:     false,
            enableRemove:     false,
            enableFullscreen: true,
            enableEdit:       false,
            enableDragDrop:   true,
            staticGrid:       true,
            theme:            cfg.theme || 'light',
            design:           _sharedDesign || {},
            layout: cfg.layout || 'grid',
        });
        // Fullscreen buttons on cards call window.dashboardLayout.toggleFullscreen
        window.dashboardLayout = _sharedLayout;
    } else {
        _sharedLayout.clearDashboard();
    }

    // Remove any empty-page note left from a previous page switch
    document.querySelectorAll('#dashboardGrid .page-empty-note').forEach(el => el.remove());

    if (charts.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'page-empty-note text-gray-400 text-center py-16 col-span-full';
        empty.textContent = 'This page has no widgets.';
        document.getElementById('dashboardGrid').appendChild(empty);
        return;
    }

    charts.forEach(chartConfig => {
        try {
            const c = { ...chartConfig, size: chartConfig.size || 'medium' };
            // KPI cards recompute from their source chart's stored data
            if (c.widget_type === 'kpi' && c.kpi?.sourceId && window.computeKpiFromChart) {
                const source = allCharts.find(x => x.id === c.kpi.sourceId);
                if (source) {
                    const kpi = window.computeKpiFromChart(source, c.kpi.agg);
                    c.kpiValue = kpi.value;
                    c.kpiSub = kpi.sub;
                }
            }
            _sharedLayout.addChart(c);
        } catch (e) {
            console.error('Error rendering chart:', e);
        }
    });
}

function showError(title, message) {
    document.getElementById('loadingState').classList.add('hidden');
    document.getElementById('dashboardContent').classList.add('hidden');
    const errorState = document.getElementById('errorState');
    errorState.classList.remove('hidden');
    document.getElementById('errorTitle').textContent   = title;
    document.getElementById('errorMessage').textContent = message || '';
}
