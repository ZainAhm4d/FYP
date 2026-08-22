/**
 * View Dashboard Page
 * Loads and displays a specific saved dashboard with all its charts
 */

// Global variables
let currentDashboard = null;
let dashboardId = null;

/**
 * Initialize view dashboard page
 */
function initViewDashboardPage() {
    console.log('Initializing View Dashboard page...');
    
    // Get dashboard ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    dashboardId = parseInt(urlParams.get('id'));
    
    if (!dashboardId) {
        showError('Invalid dashboard ID');
        return;
    }
    
    console.log('Loading dashboard ID:', dashboardId);
    
    // Initialize dashboard layout (designer mode: drag, resize, remove widgets)
    window.dashboardLayout = new window.DashboardLayout('dashboardGrid', {
        minChartHeight: 350,
        chartSpacing: 16,
        enableResize: true,
        enableRemove: true,
        enableFullscreen: true,
        enableEdit: true,
        enableDragDrop: true,
        layout: 'grid'
    });

    // Handle edit button clicks from chart cards
    window.onChartEditRequested = openEditChartModal;
    
    // Setup event listeners
    setupEventListeners();
    
    // Load dashboard
    loadDashboard();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Refresh button — re-executes every chart's query against CURRENT data
    // (not just a reload of the saved snapshots)
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => refreshAllChartData(true));
    }

    // Auto-refresh interval
    document.getElementById('dashAutoRefresh')?.addEventListener('change', (e) => {
        const secs = parseInt(e.target.value, 10) || 0;
        if (currentDashboard) {
            currentDashboard.config_json.autoRefreshSecs = secs;
            _putConfig();
        }
        _startAutoRefresh(secs);
        Notifications.success(secs
            ? `Live updates + forced re-run every ${secs / 60} min`
            : 'Live — charts update when source data changes');
    });
    
    // Change Layout button
    const changeLayoutBtn = document.getElementById('changeLayoutBtn');
    if (changeLayoutBtn) {
        changeLayoutBtn.addEventListener('click', openLayoutModal);
    }
    
    // Export dropdown toggle
    const exportBtn = document.getElementById('exportBtn');
    const exportDropdown = document.getElementById('exportDropdown');
    if (exportBtn && exportDropdown) {
        // The toolbar bar scrolls horizontally (overflow-x: auto), and per the
        // CSS spec that silently forces overflow-y to 'auto' too — so a plain
        // position:absolute dropdown gets clipped at the toolbar's own edge no
        // matter what overflow-y is set to. Escaping via position:fixed with
        // JS-computed coordinates sidesteps that entirely (fixed positioning
        // ignores ancestor overflow/clipping).
        const positionExportDropdown = () => {
            const r = exportBtn.getBoundingClientRect();
            exportDropdown.style.position = 'fixed';
            exportDropdown.style.top = `${r.bottom + 6}px`;
            exportDropdown.style.right = `${window.innerWidth - r.right}px`;
            exportDropdown.style.left = 'auto';
            exportDropdown.style.marginTop = '0';
            exportDropdown.style.zIndex = '9999';
        };
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = !exportDropdown.classList.contains('hidden');
            if (!open) positionExportDropdown();
            exportDropdown.classList.toggle('hidden', open);
            exportBtn.setAttribute('aria-expanded', String(!open));
        });
        window.addEventListener('resize', () => {
            if (!exportDropdown.classList.contains('hidden')) positionExportDropdown();
        });
        document.addEventListener('click', () => {
            exportDropdown.classList.add('hidden');
            exportBtn.setAttribute('aria-expanded', 'false');
        });
        document.querySelectorAll('.export-option').forEach(btn => {
            btn.addEventListener('click', () => {
                exportDropdown.classList.add('hidden');
                exportDashboard(btn.dataset.format);
            });
        });
    }
    
    // Layout modal
    const closeLayoutModalBtn = document.getElementById('closeLayoutModalBtn');
    if (closeLayoutModalBtn) {
        closeLayoutModalBtn.addEventListener('click', closeLayoutModal);
    }
    
    // Layout options
    const layoutOptions = document.querySelectorAll('.layout-option');
    layoutOptions.forEach(option => {
        option.addEventListener('click', handleLayoutChange);
    });

    // Edit chart modal
    const closeEditChartModalBtn = document.getElementById('closeEditChartModalBtn');
    const cancelEditChartBtn = document.getElementById('cancelEditChartBtn');
    const editChartForm = document.getElementById('editChartForm');
    if (closeEditChartModalBtn) closeEditChartModalBtn.addEventListener('click', closeEditChartModal);
    if (cancelEditChartBtn) cancelEditChartBtn.addEventListener('click', closeEditChartModal);
    if (editChartForm) editChartForm.addEventListener('submit', handleSaveChart);

    // Share modal
    document.getElementById('shareBtn')?.addEventListener('click', openShareModal);
    document.getElementById('closeShareModalBtn')?.addEventListener('click', closeShareModal);
    document.getElementById('generateShareLinkBtn')?.addEventListener('click', generateShareLink);
    document.getElementById('copyShareLinkBtn')?.addEventListener('click', copyShareLink);
    document.getElementById('revokeShareBtn')?.addEventListener('click', revokeShareLink);

    // Schedule modal
    document.getElementById('scheduleBtn')?.addEventListener('click', openScheduleModal);
    document.getElementById('closeScheduleModal')?.addEventListener('click', closeScheduleModal);
    document.getElementById('saveScheduleBtn')?.addEventListener('click', saveSchedule);
    document.getElementById('sendNowBtn')?.addEventListener('click', sendScheduleNow);
    document.getElementById('deleteCancelBtn')?.addEventListener('click', _hideDeleteConfirm);
    document.getElementById('deleteConfirmBtn')?.addEventListener('click', _confirmDelete);

    // Frequency radio pill styling + day-picker visibility
    document.querySelectorAll('.freq-option input[type="radio"]').forEach(radio => {
        radio.addEventListener('change', () => { _updateFreqPills(); _updateDayPickers(); });
    });
    // CH-16: keep the "Next report: …" preview live as the form changes
    ['scheduleTime', 'scheduleTimezone', 'scheduleDow'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', _updateScheduleNextRun);
    });
    // Real calendar Prev/Next month navigation (browsing only — the day
    // number saved doesn't depend on which month is being viewed)
    document.getElementById('scheduleDomPrevBtn')?.addEventListener('click', () => _calNavigate(-1));
    document.getElementById('scheduleDomNextBtn')?.addEventListener('click', () => _calNavigate(1));

    // Collaboration modal
    document.getElementById('collaborateBtn')?.addEventListener('click', openCollaborateModal);
    document.getElementById('closeCollaborateModal')?.addEventListener('click', closeCollaborateModal);
    document.getElementById('inviteCollaboratorBtn')?.addEventListener('click', inviteCollaborator);

    // Add Widget dropdown + modal
    const widgetBtn = document.getElementById('addWidgetBtn');
    const widgetDropdown = document.getElementById('widgetDropdown');
    if (widgetBtn && widgetDropdown) {
        // Same fix as the Export dropdown: .dash-toolbar-bar scrolls horizontally
        // (overflow-x: auto), which per spec forces overflow-y to compute as
        // 'auto' too — clipping any absolutely-positioned child that pops open
        // taller than the bar. position:fixed with JS-computed coordinates
        // escapes that clipping entirely.
        const positionWidgetDropdown = () => {
            const r = widgetBtn.getBoundingClientRect();
            widgetDropdown.style.position = 'fixed';
            widgetDropdown.style.top = `${r.bottom + 6}px`;
            widgetDropdown.style.right = `${window.innerWidth - r.right}px`;
            widgetDropdown.style.left = 'auto';
            widgetDropdown.style.marginTop = '0';
            widgetDropdown.style.zIndex = '9999';
        };
        widgetBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = !widgetDropdown.classList.contains('hidden');
            if (!open) positionWidgetDropdown();
            widgetDropdown.classList.toggle('hidden');
        });
        window.addEventListener('resize', () => {
            if (!widgetDropdown.classList.contains('hidden')) positionWidgetDropdown();
        });
        document.addEventListener('click', () => widgetDropdown.classList.add('hidden'));
        document.querySelectorAll('.widget-option').forEach(btn => {
            btn.addEventListener('click', () => {
                widgetDropdown.classList.add('hidden');
                openWidgetModal(btn.dataset.widget);
            });
        });
    }
    document.getElementById('closeWidgetModal')?.addEventListener('click', closeWidgetModal);
    document.getElementById('widgetCreateBtn')?.addEventListener('click', createWidget);

    // Theme toggle
    document.getElementById('themeToggleBtn')?.addEventListener('click', toggleTheme);

    // Design panel
    _initDesignPanel();

    // Widget format modal
    document.getElementById('closeFormatModal')?.addEventListener('click', closeFormatModal);
    document.getElementById('fmtApplyBtn')?.addEventListener('click', applyWidgetFormat);
    document.getElementById('fmtBold')?.addEventListener('click', function () { this.classList.toggle('bg-indigo-100'); });
    document.getElementById('fmtItalic')?.addEventListener('click', function () { this.classList.toggle('bg-indigo-100'); });
    document.querySelectorAll('.fmt-align').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.fmt-align').forEach(b => b.classList.remove('bg-indigo-100'));
            btn.classList.add('bg-indigo-100');
        });
    });
}

// ── Live data: re-execute chart queries ──────────────────────────────────────

let _autoRefreshTimer = null;
let _changePollTimer = null;
let _lastKnownStamps = {};   // dataset_id -> last_refreshed ISO we rendered with
let _liveRefreshBusy = false;

/**
 * Change-detection loop (the near-real-time path): every 10 s, ask the server
 * for each used dataset's last-refreshed timestamp — a single cheap DB read.
 * Only when a source actually changed (push webhook or interval re-fetch)
 * do we re-execute queries. Edit in sheet → webhook → re-fetch → this poll
 * notices → charts update. Total latency ≈ 5–15 s, near-zero idle cost.
 */
function _startChangePolling() {
    clearInterval(_changePollTimer);
    const ids = [...new Set((currentDashboard?.config_json?.charts || [])
        .map(c => c.dataset?.id).filter(Boolean))];
    if (!ids.length) return;

    // On-open staleness check: if any dataset changed since this dashboard
    // last pulled data (config.lastDataRefresh), re-query immediately instead
    // of showing the old snapshot until something ELSE changes.
    (async () => {
        try {
            const stamps = await API.get(`/datasets/meta/last-updated?ids=${ids.join(',')}`, true);
            _lastKnownStamps = { ...stamps };
            const baseline = currentDashboard.config_json.lastDataRefresh;
            const stale = baseline
                ? Object.values(stamps).some(ts => new Date(ts) > new Date(baseline))
                : true;   // never refreshed since charts were added — treat as stale
            if (stale && !_liveRefreshBusy) {
                _liveRefreshBusy = true;
                Notifications.success('Data changed since last visit — updating charts…');
                await refreshAllChartData(false);
                _liveRefreshBusy = false;
            }
        } catch (_) { /* fall back to interval polling */ }
    })();

    _changePollTimer = setInterval(async () => {
        if (document.hidden || _liveRefreshBusy) return;
        try {
            const stamps = await API.get(`/datasets/meta/last-updated?ids=${ids.join(',')}`, true);
            const changed = Object.entries(stamps).some(([id, ts]) =>
                _lastKnownStamps[id] && ts !== _lastKnownStamps[id]);
            const first = Object.keys(_lastKnownStamps).length === 0;
            _lastKnownStamps = { ..._lastKnownStamps, ...stamps };
            if (changed && !first) {
                _liveRefreshBusy = true;
                Notifications.success('New data arrived — updating charts…');
                await refreshAllChartData(false);
                _liveRefreshBusy = false;
            }
        } catch (_) { /* transient — next tick retries */ }
    }, 10000);
}

function _startAutoRefresh(secs) {
    clearInterval(_autoRefreshTimer);
    _autoRefreshTimer = null;
    if (secs > 0) {
        _autoRefreshTimer = setInterval(() => {
            if (!document.hidden) refreshAllChartData(false);   // silent in background
        }, secs * 1000);
    }
}

/** "Data as of" badge — makes freshness visible instead of implied. */
function _updateFreshnessBadge() {
    const wrap = document.getElementById('dataFreshness');
    const txt = document.getElementById('dataFreshnessText');
    if (!wrap || !txt || !currentDashboard) return;
    const iso = currentDashboard.config_json.lastDataRefresh;
    if (!iso) { wrap.classList.add('hidden'); return; }
    const d = new Date(iso);
    const mins = Math.floor((Date.now() - d.getTime()) / 60000);
    txt.textContent = 'Data as of ' + (
        mins < 1 ? 'just now'
        : mins < 60 ? `${mins} min ago`
        : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    );
    wrap.classList.remove('hidden');
    wrap.classList.add('inline-flex');
}

/**
 * Re-run every chart's stored query against the CURRENT dataset contents and
 * update the dashboard in place. This is what makes dashboards live: when a
 * connected Google Sheet refreshes (or a dataset is re-cleaned), this pulls
 * the new numbers into every chart and KPI.
 */
async function refreshAllChartData(showFeedback = true) {
    if (!currentDashboard) return;
    const charts = currentDashboard.config_json.charts || [];
    const targets = charts.filter(c =>
        (c.widget_type || 'chart') === 'chart' && c.dataset?.id && c.template?.type);

    if (targets.length === 0) {
        loadDashboard();   // nothing re-runnable — plain reload
        return;
    }

    if (showFeedback) Loading.show(`Refreshing data (0/${targets.length})…`);
    let ok = 0, done = 0;

    for (const ch of targets) {
        try {
            const params = ch.queryResult?.parameters || ch.parameters || {};
            const resp = await API.post('/queries/execute', {
                template_type: ch.template.type,
                dataset_id: ch.dataset.id,
                parameters: params,
            }, true);
            if (resp?.success && resp.plotly_spec) {
                ch.plotlySpec = resp.plotly_spec;
                ch.queryResult = {
                    ...(resp.query_result || {}),
                    parameters: params,
                    insights: resp.insights || [],
                };
                ok++;
            }
        } catch (_) { /* chart keeps its previous data */ }
        done++;
        if (showFeedback) Loading.show(`Refreshing data (${done}/${targets.length})…`);
    }

    if (showFeedback) Loading.hide();
    // Record when we last pulled data — the on-open staleness check compares
    // dataset change stamps against this
    currentDashboard.config_json.lastDataRefresh = new Date().toISOString();
    _flushPendingSave();
    renderDashboard();          // fresh charts + KPIs recompute
    _putConfig();               // persist fresh snapshots (exports/reports see them too)
    if (showFeedback) {
        Notifications.success(`Data refreshed — ${ok}/${targets.length} chart(s) updated`);
    }
}

// ── Dashboard Design panel ────────────────────────────────────────────────────

const DZ_PALETTES = {
    default:   null,
    indigo:    ['#4F46E5', '#818CF8', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'],
    ocean:     ['#0284c7', '#06b6d4', '#14b8a6', '#38bdf8', '#0ea5e9', '#22d3ee'],
    forest:    ['#16a34a', '#0d9488', '#65a30d', '#22c55e', '#84cc16', '#4ade80'],
    sunset:    ['#f97316', '#ef4444', '#f59e0b', '#ec4899', '#fb923c', '#facc15'],
    corporate: ['#1e40af', '#3b82f6', '#0f766e', '#60a5fa', '#334155', '#93c5fd'],
};

let _dzPersistTimer = null;

function _design() {
    if (!currentDashboard.config_json.design) currentDashboard.config_json.design = {};
    return currentDashboard.config_json.design;
}

function _resolvedDesign() {
    const d = { ...(currentDashboard?.config_json?.design || {}) };
    d.paletteColors = DZ_PALETTES[d.palette] || null;
    return d;
}

function openDesignPanel() {
    const panel = document.getElementById('designPanel');
    if (!panel || !currentDashboard) return;
    const d = _design();

    document.getElementById('dzCanvasBg').value = d.canvasBg || '#f9fafb';
    document.getElementById('dzCardBg').value = d.cardBg || '#ffffff';
    document.getElementById('dzCardRadius').value = d.cardRadius !== undefined ? d.cardRadius : 12;
    document.getElementById('dzCardShadow').checked = d.cardShadow !== false;
    document.getElementById('dzCardBorder').checked = !!d.cardBorder;
    document.getElementById('dzAccent').value = d.accent || '#0d9488';
    document.getElementById('dzPalette').value = d.palette || 'default';
    _dzRenderPalettePreview();

    panel.classList.remove('translate-x-full');
    // CH-14: translucent backdrop — clicking anywhere outside closes the panel
    let backdrop = document.getElementById('designBackdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'designBackdrop';
        backdrop.className = 'fixed inset-0 bg-black/20 z-40';
        backdrop.addEventListener('click', closeDesignPanel);
        document.body.appendChild(backdrop);
    }
    backdrop.classList.remove('hidden');
}

function closeDesignPanel() {
    document.getElementById('designPanel')?.classList.add('translate-x-full');
    document.getElementById('designBackdrop')?.classList.add('hidden');
}

function _dzRenderPalettePreview() {
    const el = document.getElementById('dzPalettePreview');
    if (!el) return;
    const colors = DZ_PALETTES[document.getElementById('dzPalette').value];
    el.innerHTML = colors
        ? colors.map(c => `<span class="w-6 h-6 rounded-md" style="background:${c}"></span>`).join('')
        : '<span class="text-xs text-gray-400">Charts keep their own colors</span>';
}

/** Read the panel inputs into config_json.design, apply live, persist (debounced). */
function _dzUpdate(needsChartRerender = false) {
    if (!currentDashboard) return;
    const d = _design();
    const canvas = document.getElementById('dzCanvasBg').value;
    d.canvasBg = canvas === '#f9fafb' ? '' : canvas;   // default = unset
    d.cardBg = document.getElementById('dzCardBg').value;
    d.cardRadius = parseInt(document.getElementById('dzCardRadius').value, 10);
    d.cardShadow = document.getElementById('dzCardShadow').checked;
    d.cardBorder = document.getElementById('dzCardBorder').checked;
    d.accent = document.getElementById('dzAccent').value;
    d.palette = document.getElementById('dzPalette').value;

    window.applyDashboardDesignCSS(d);
    if (needsChartRerender) {
        _flushPendingSave();
        renderDashboard();   // charts must re-render to pick up palette/accent
    }
    clearTimeout(_dzPersistTimer);
    _dzPersistTimer = setTimeout(_putConfig, 800);
}

function _initDesignPanel() {
    document.getElementById('designBtn')?.addEventListener('click', openDesignPanel);
    document.getElementById('closeDesignPanel')?.addEventListener('click', closeDesignPanel);
    document.getElementById('designDoneBtn')?.addEventListener('click', closeDesignPanel);
    // CH-14: Escape closes the panel too
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDesignPanel();
    });

    // CSS-only knobs: instant, no chart re-render
    ['dzCanvasBg', 'dzCardBg',
     'dzCardRadius', 'dzCardShadow', 'dzCardBorder'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', () => _dzUpdate(false));
    });
    // Chart-affecting knobs: re-render required
    document.getElementById('dzAccent')?.addEventListener('change', () => _dzUpdate(true));
    document.getElementById('dzPalette')?.addEventListener('change', () => { _dzRenderPalettePreview(); _dzUpdate(true); });

    document.getElementById('dzCanvasReset')?.addEventListener('click', () => {
        document.getElementById('dzCanvasBg').value = '#f9fafb';
        _dzUpdate(false);
    });
    document.getElementById('dzReset')?.addEventListener('click', () => {
        currentDashboard.config_json.design = {};
        window.applyDashboardDesignCSS({});
        openDesignPanel();     // repopulate inputs with defaults
        _flushPendingSave();
        renderDashboard();
        _putConfig();
        Notifications.success('Design reset to defaults');
    });
}

// ── Widget Format popover ─────────────────────────────────────────────────────

let _formatChartId = null;   // layout-internal id of the widget being formatted

window.onWidgetFormatRequested = function (chartId) {
    const chart = window.dashboardLayout?.charts.find(c => c.id === chartId);
    if (!chart) return;
    _formatChartId = chartId;
    const cfg = chart.config;
    const style = cfg.style || {};
    const wt = cfg.widget_type || 'chart';

    document.getElementById('fmtFrame').checked = !style.frameless;
    document.getElementById('fmtTitle').checked = !style.hideTitle;
    document.getElementById('fmtTextSection').classList.toggle('hidden', wt !== 'text');
    document.getElementById('fmtKpiSection').classList.toggle('hidden', wt !== 'kpi');

    if (wt === 'text') {
        document.getElementById('fmtFontSize').value = style.fontSize || 'base';
        document.getElementById('fmtBold').classList.toggle('bg-indigo-100', !!style.bold);
        document.getElementById('fmtItalic').classList.toggle('bg-indigo-100', !!style.italic);
        document.getElementById('fmtTextColor').value = style.textColor || '#4b5563';
        document.querySelectorAll('.fmt-align').forEach(b => {
            b.classList.toggle('bg-indigo-100', b.dataset.align === (style.align || 'left'));
        });
    }
    if (wt === 'kpi') {
        document.getElementById('fmtKpiTitle').value = cfg.title || '';
        document.getElementById('fmtKpiTitleSize').value = style.kpiTitleSize || 'sm';
        document.getElementById('fmtKpiTitleColor').value = style.kpiTitleColor || '#6b7280';
        document.getElementById('fmtAccent').value = style.accent || '#0d9488';
        document.getElementById('fmtKpiSize').value = style.kpiSize || 'base';
        document.getElementById('fmtKpiShowSub').checked = style.hideKpiSub !== true;
    }

    const modal = document.getElementById('widgetFormatModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
};

function closeFormatModal() {
    const modal = document.getElementById('widgetFormatModal');
    modal?.classList.add('hidden');
    modal?.classList.remove('flex');
    _formatChartId = null;
}

function applyWidgetFormat() {
    const chart = window.dashboardLayout?.charts.find(c => c.id === _formatChartId);
    if (!chart) { closeFormatModal(); return; }
    const cfg = chart.config;
    const wt = cfg.widget_type || 'chart';

    const style = { ...(cfg.style || {}) };
    style.frameless = !document.getElementById('fmtFrame').checked;
    style.hideTitle = !document.getElementById('fmtTitle').checked;

    if (wt === 'text') {
        style.fontSize  = document.getElementById('fmtFontSize').value;
        style.bold      = document.getElementById('fmtBold').classList.contains('bg-indigo-100');
        style.italic    = document.getElementById('fmtItalic').classList.contains('bg-indigo-100');
        style.textColor = document.getElementById('fmtTextColor').value;
        style.align     = document.querySelector('.fmt-align.bg-indigo-100')?.dataset.align || 'left';
    }
    if (wt === 'kpi') {
        const newTitle = document.getElementById('fmtKpiTitle').value.trim();
        cfg.title = newTitle || 'KPI';
        style.kpiTitleSize = document.getElementById('fmtKpiTitleSize').value;
        style.kpiTitleColor = document.getElementById('fmtKpiTitleColor').value;
        style.accent = document.getElementById('fmtAccent').value;
        style.kpiSize = document.getElementById('fmtKpiSize').value;
        style.hideKpiSub = !document.getElementById('fmtKpiShowSub').checked;
    }

    cfg.style = style;
    closeFormatModal();
    // Persist FIRST: it merges the layout's configs (incl. the new style) into
    // config_json — renderDashboard rebuilds from config_json, so the order matters
    _persistDashboard(true);
    renderDashboard();
    Notifications.success('Formatting applied');
}

// ── Layout persistence (designer mode) ───────────────────────────────────────

let _layoutReady = false;      // suppress saves while the initial render populates the grid
let _saveLayoutTimer = null;
let _renderedIds = new Set();  // chart ids currently rendered (the active page)
let _activePage = 0;

/** PUT the current config_json as-is (used for page/theme operations). */
async function _putConfig() {
    try {
        await API.put(`/dashboards/${dashboardId}`, {
            config_json: currentDashboard.config_json
        }, true);
    } catch (e) {
        Notifications.error('Could not save: ' + (e.message || 'permission denied'));
    }
}

function _persistDashboard(immediate = false) {
    if (!_layoutReady || !currentDashboard || !window.dashboardLayout) return;
    clearTimeout(_saveLayoutTimer);
    _saveLayoutTimer = null;
    const doSave = async () => {
        _saveLayoutTimer = null;
        // The layout engine holds the active page's widgets (positions, additions,
        // removals). Merge: keep every chart belonging to OTHER pages untouched,
        // replace the active page's set from the live grid.
        const cfg = currentDashboard.config_json;
        const kept = (cfg.charts || []).filter(c => !_renderedIds.has(c.id));
        const pageCharts = window.dashboardLayout.charts.map(c => c.config);
        cfg.charts = [...kept, ...pageCharts];

        // Sync the active page's membership (handles adds and removals)
        const pages = _ensurePages();
        pages[_activePage].chartIds = pageCharts.map(c => c.id);
        _renderedIds = new Set(pages[_activePage].chartIds);

        await _putConfig();
    };
    if (immediate) doSave();
    else _saveLayoutTimer = setTimeout(doSave, 1200);
}

/** Flush a pending debounced save immediately (before switching page/context). */
function _flushPendingSave() {
    if (_saveLayoutTimer) {
        clearTimeout(_saveLayoutTimer);
        _saveLayoutTimer = null;
        _persistDashboard(true);
    }
}

// ── Multi-page tabs ───────────────────────────────────────────────────────────

const _escHtml = (s) => String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** Guarantee config_json.pages exists and every chart is assigned to a page. */
function _ensurePages() {
    const cfg = currentDashboard.config_json;
    if (!Array.isArray(cfg.pages) || cfg.pages.length === 0) {
        cfg.pages = [{ name: 'Page 1', chartIds: (cfg.charts || []).map(c => c.id) }];
    }
    const assigned = new Set(cfg.pages.flatMap(p => p.chartIds || []));
    (cfg.charts || []).forEach(c => {
        if (!assigned.has(c.id)) cfg.pages[0].chartIds.push(c.id);
    });
    return cfg.pages;
}

function renderPageTabs() {
    const bar = document.getElementById('pageTabBar');
    if (!bar) return;
    const pages = currentDashboard.config_json.pages;
    bar.classList.remove('hidden');
    bar.innerHTML = pages.map((p, i) => `
        <div class="dash-tab ${i === _activePage ? 'active' : ''}" onclick="switchPage(${i})">
            <span class="tab-name">${_escHtml(p.name)}</span>
            ${i === _activePage ? `
                <span class="tab-action" title="Rename page" onclick="event.stopPropagation(); renamePage(${i})">✎</span>
                ${pages.length > 1 ? `<span class="tab-action" title="Delete page" onclick="event.stopPropagation(); deletePage(${i})">✕</span>` : ''}
            ` : ''}
        </div>`).join('')
        + `<button class="dash-tab" onclick="addPage()" title="Add a new page">+ Page</button>`;
}

function switchPage(i) {
    if (i === _activePage) return;
    _flushPendingSave();          // don't lose in-flight layout edits
    _activePage = i;
    renderDashboard();
}

function addPage() {
    _flushPendingSave();
    const pages = _ensurePages();
    pages.push({ name: `Page ${pages.length + 1}`, chartIds: [] });
    _activePage = pages.length - 1;
    renderDashboard();
    _putConfig();
    Notifications.success('Page added — use "Add Widget" or move charts here via chart Edit');
}

function renamePage(i) {
    // Inline rename — no browser prompt
    const tab = document.querySelectorAll('#pageTabBar .dash-tab')[i];
    const nameSpan = tab?.querySelector('.tab-name');
    if (!nameSpan) return;
    const pages = currentDashboard.config_json.pages;
    const input = document.createElement('input');
    input.value = pages[i].name;
    input.maxLength = 40;
    input.className = 'border border-indigo-300 rounded px-2 py-0.5 text-sm w-32 focus:outline-none focus:ring-1 focus:ring-indigo-400';
    input.onclick = (e) => e.stopPropagation();
    const commit = () => {
        const name = input.value.trim();
        if (name) { pages[i].name = name; _putConfig(); }
        renderPageTabs();
    };
    input.onblur = commit;
    input.onkeydown = (e) => {
        if (e.key === 'Enter') input.blur();
        if (e.key === 'Escape') { input.onblur = null; renderPageTabs(); }
    };
    nameSpan.replaceWith(input);
    input.focus();
    input.select();
}

function deletePage(i) {
    const pages = currentDashboard.config_json.pages;
    if (pages.length <= 1) return;
    _flushPendingSave();
    // Non-destructive: the page's charts move to the first remaining page
    const removed = pages.splice(i, 1)[0];
    const target = pages[0];
    (removed.chartIds || []).forEach(id => {
        if (!target.chartIds.includes(id)) target.chartIds.push(id);
    });
    _activePage = 0;
    renderDashboard();
    _putConfig();
    Notifications.success(`Page "${removed.name}" deleted — its widgets moved to "${target.name}"`);
}

// ── Theme ─────────────────────────────────────────────────────────────────────

function toggleTheme() {
    if (!currentDashboard) return;
    const next = (currentDashboard.config_json.theme || 'light') === 'dark' ? 'light' : 'dark';
    currentDashboard.config_json.theme = next;
    _flushPendingSave();
    renderDashboard();     // re-renders charts with themed Plotly specs
    _putConfig();
}

// Called by DashboardLayout after any drag/resize
window.onLayoutChanged = () => _persistDashboard();

// Called by DashboardLayout after a widget/chart is removed
function onChartRemoved() {
    _persistDashboard(true);
    const countEl = document.getElementById('chartCount');
    if (countEl && window.dashboardLayout) {
        const n = window.dashboardLayout.charts.filter(c => (c.config.widget_type || 'chart') === 'chart').length;
        countEl.textContent = `${n} chart${n === 1 ? '' : 's'}`;
    }
}

// ── Widgets: text / KPI / divider ─────────────────────────────────────────────

let _pendingWidgetType = null;

function openWidgetModal(type) {
    _pendingWidgetType = type;
    const modal = document.getElementById('widgetModal');
    if (!modal) return;

    const titles = { kpi: 'Add KPI Card', text: 'Add Text Block', divider: 'Add Section Divider' };
    document.getElementById('widgetModalTitle').textContent = titles[type] || 'Add Widget';
    document.getElementById('widgetTitleInput').value = '';
    document.getElementById('widgetTitleLabel').textContent = type === 'divider' ? 'Section label (optional)' : 'Title';
    document.getElementById('widgetBodyWrap').classList.toggle('hidden', type !== 'text');
    document.getElementById('widgetKpiWrap').classList.toggle('hidden', type !== 'kpi');
    if (type === 'text') document.getElementById('widgetBodyInput').value = '';

    if (type === 'kpi') {
        const sel = document.getElementById('widgetKpiSource');
        sel.innerHTML = '';
        const chartConfigs = (window.dashboardLayout?.charts || [])
            .map(c => c.config)
            .filter(c => (c.widget_type || 'chart') === 'chart');
        if (chartConfigs.length === 0) {
            Notifications.error('Add at least one chart before creating a KPI card.');
            return;
        }
        chartConfigs.forEach(c => {
            const o = document.createElement('option');
            o.value = c.id;
            o.textContent = c.title || c.id;
            sel.appendChild(o);
        });
    }

    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeWidgetModal() {
    const modal = document.getElementById('widgetModal');
    modal?.classList.add('hidden');
    modal?.classList.remove('flex');
    _pendingWidgetType = null;
}

/** Compute a KPI value from a chart's stored query result (shared helper). */
function _computeKpi(chartCfg, agg) {
    return window.computeKpiFromChart(chartCfg, agg);
}

async function createWidget() {
    const type = _pendingWidgetType;
    if (!type || !currentDashboard) return;

    const title = document.getElementById('widgetTitleInput').value.trim();
    const config = {
        id: `widget-${Date.now()}`,
        widget_type: type,
        title,
        createdAt: new Date().toISOString(),
    };

    if (type === 'text') {
        config.body = document.getElementById('widgetBodyInput').value.trim();
        if (!config.title && !config.body) { Notifications.error('Give the text block a title or some text.'); return; }
    }

    if (type === 'kpi') {
        const sourceId = document.getElementById('widgetKpiSource').value;
        const agg = document.getElementById('widgetKpiAgg').value;
        const sourceCfg = (window.dashboardLayout?.charts || [])
            .map(c => c.config).find(c => c.id === sourceId);
        if (!sourceCfg) { Notifications.error('Pick a source chart.'); return; }
        const kpi = _computeKpi(sourceCfg, agg);
        config.kpi = { sourceId, agg };
        config.kpiValue = kpi.value;
        config.kpiSub = kpi.sub;
        if (!config.title) config.title = `${agg.toUpperCase()} — ${sourceCfg.title || ''}`.slice(0, 60);
    }

    await window.dashboardLayout.addChart(config);
    closeWidgetModal();
    _persistDashboard(true);
    Notifications.success('Widget added — drag it into place');
}

// ── Share modal ───────────────────────────────────────────────────────────────

function openShareModal() {
    const modal = document.getElementById('shareModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Reflect current sharing state from loaded dashboard
    if (currentDashboard && currentDashboard.is_public && currentDashboard.share_token) {
        _showShareActiveState(currentDashboard.share_token, currentDashboard.view_count || 0);
    } else {
        document.getElementById('shareNotSharedState')?.classList.remove('hidden');
        document.getElementById('shareActiveState')?.classList.add('hidden');
    }
}

function closeShareModal() {
    const modal = document.getElementById('shareModal');
    if (modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }
}

function _showShareActiveState(token, viewCount) {
    document.getElementById('shareNotSharedState')?.classList.add('hidden');
    const active = document.getElementById('shareActiveState');
    active?.classList.remove('hidden');

    const url = `${window.location.origin}/shared-dashboard.html?token=${token}`;
    const input = document.getElementById('shareLinkInput');
    if (input) input.value = url;

    const countEl = document.getElementById('shareViewCount');
    if (countEl) countEl.textContent = `${viewCount} view${viewCount === 1 ? '' : 's'}`;
}

async function generateShareLink() {
    try {
        document.getElementById('generateShareLinkBtn').textContent = 'Generating...';
        const data = await API.post(`/dashboards/${dashboardId}/share`, {}, true);
        // Update local dashboard object so modal stays correct on re-open
        if (currentDashboard) {
            currentDashboard.is_public = true;
            currentDashboard.share_token = data.share_token;
            currentDashboard.view_count  = data.view_count;
        }
        _showShareActiveState(data.share_token, data.view_count);
        Notifications.success('Share link generated!');
    } catch (err) {
        Notifications.error('Failed to generate share link: ' + (err.message || err));
        document.getElementById('generateShareLinkBtn').textContent = 'Generate Share Link';
    }
}

async function revokeShareLink() {
    if (!confirm('This will disable the share link. Anyone with it will no longer be able to view this dashboard. Continue?')) return;
    try {
        await API.delete(`/dashboards/${dashboardId}/share`, true);
        if (currentDashboard) {
            currentDashboard.is_public   = false;
            currentDashboard.share_token = null;
        }
        document.getElementById('shareActiveState')?.classList.add('hidden');
        document.getElementById('shareNotSharedState')?.classList.remove('hidden');
        Notifications.success('Sharing disabled. The link is no longer active.');
    } catch (err) {
        Notifications.error('Failed to revoke share link: ' + (err.message || err));
    }
}

function copyShareLink() {
    const input = document.getElementById('shareLinkInput');
    if (!input) return;
    navigator.clipboard.writeText(input.value).then(() => {
        const btn = document.getElementById('copyShareLinkBtn');
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
    }).catch(() => {
        input.select();
        document.execCommand('copy');
        Notifications.success('Link copied!');
    });
}

/**
 * Load dashboard from API
 */
async function loadDashboard() {
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const dashboardGrid = document.getElementById('dashboardGrid');
    
    try {
        console.log('Fetching dashboard from API...');
        
        // Show loading state
        if (loadingState) loadingState.classList.remove('hidden');
        if (errorState) errorState.classList.add('hidden');
        if (dashboardGrid) dashboardGrid.classList.add('hidden');
        
        // Fetch dashboard from API
        const dashboard = await API.get(`/dashboards/${dashboardId}`, true);
        
        console.log('Dashboard loaded:', dashboard);
        
        currentDashboard = dashboard;
        
        // Update page metadata
        updateDashboardMetadata();
        
        // Hide loading state
        if (loadingState) loadingState.classList.add('hidden');
        if (dashboardGrid) dashboardGrid.classList.remove('hidden');
        
        // Render dashboard
        renderDashboard();
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
        
        // Hide loading state
        if (loadingState) loadingState.classList.add('hidden');
        
        // Check if it's a 404 - try localStorage fallback
        if (error.message && error.message.includes('404')) {
            console.log('API not available, checking localStorage...');
            loadDashboardFromLocalStorage();
        } else {
            showError('Failed to load dashboard: ' + (error.message || 'Unknown error'));
        }
    }
}

/**
 * Load dashboard from localStorage (fallback)
 */
function loadDashboardFromLocalStorage() {
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const dashboardGrid = document.getElementById('dashboardGrid');
    
    console.log('Loading dashboard from localStorage...');
    
    const savedDashboards = Storage.get(Storage.userKey('savedDashboards')) || [];
    const dashboard = savedDashboards.find(d => d.id === dashboardId);
    
    if (!dashboard) {
        showError('Dashboard not found in local storage');
        return;
    }
    
    currentDashboard = dashboard;
    
    // Update page metadata
    updateDashboardMetadata();
    
    // Hide loading state
    if (loadingState) loadingState.classList.add('hidden');
    if (errorState) errorState.classList.add('hidden');
    if (dashboardGrid) dashboardGrid.classList.remove('hidden');
    
    // Render dashboard
    renderDashboard();
    
    // Show info about local storage
    Notifications.warning('Showing locally stored dashboard. Backend API will be available soon.');
}

/**
 * Update dashboard metadata in the page
 */
function updateDashboardMetadata() {
    if (!currentDashboard) return;
    document.title = `${currentDashboard.name} - BI Dashboard Generator`;

    // Update chart count
    const chartCountElement = document.getElementById('chartCount');
    if (chartCountElement) {
        const chartCount = currentDashboard.config_json?.charts?.length || 0;
        chartCountElement.textContent = `${chartCount} chart${chartCount !== 1 ? 's' : ''}`;
    }
    
    // Update created date
    const createdDateElement = document.getElementById('createdDate');
    if (createdDateElement) {
        const date = new Date(currentDashboard.created_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
        createdDateElement.textContent = `Created ${date}`;
    }
    
    // Update updated date
    const updatedDateElement = document.getElementById('updatedDate');
    if (updatedDateElement) {
        const date = new Date(currentDashboard.updated_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
        updatedDateElement.textContent = `Updated ${date}`;
    }
}

/**
 * Render dashboard with all charts
 */
function renderDashboard() {
    if (!currentDashboard || !window.dashboardLayout) {
        console.error('Dashboard or layout not initialized');
        return;
    }

    const config = currentDashboard.config_json;

    if (!config || !config.charts) {
        console.error('Invalid dashboard configuration');
        Notifications.error('Dashboard configuration is invalid');
        return;
    }

    // Apply saved theme (page chrome + Plotly patching in the layout engine)
    const theme = config.theme || 'light';
    document.body.classList.toggle('theme-dark', theme === 'dark');
    window.dashboardLayout.options.theme = theme;

    // Apply saved design (canvas/cards/banner CSS + chart palette/accent)
    const design = _resolvedDesign();
    window.applyDashboardDesignCSS(design);
    window.dashboardLayout.options.design = design;
    const themeLabel = document.getElementById('themeToggleLabel');
    if (themeLabel) themeLabel.textContent = theme === 'dark' ? 'Light' : 'Dark';

    // Pages: partition of the flat charts array (back-compat: single page)
    const pages = _ensurePages();
    if (_activePage >= pages.length) _activePage = 0;
    renderPageTabs();

    // Set layout mode + clear grid
    window.dashboardLayout.setLayout(config.layout || 'grid');
    window.dashboardLayout.clearDashboard();

    const allCharts = config.charts || [];
    if (allCharts.length === 0) {
        Notifications.warning('This dashboard has no charts');
        _layoutReady = true;   // still allow adding widgets to an empty dashboard
        _renderedIds = new Set();
        return;
    }

    // Only render the active page's widgets
    const pageIds = new Set(pages[_activePage].chartIds || []);
    const charts = allCharts.filter(c => pageIds.has(c.id));
    _renderedIds = new Set(charts.map(c => c.id));

    _layoutReady = false;   // suppress layout saves while populating

    charts.forEach((chartConfig, index) => {
        try {
            const cfg = { ...chartConfig, size: chartConfig.size || 'medium' };

            // Refresh KPI cards from their source chart's current data
            // (source may live on any page, so look it up in the full list)
            if (cfg.widget_type === 'kpi' && cfg.kpi?.sourceId) {
                const source = allCharts.find(c => c.id === cfg.kpi.sourceId);
                if (source) {
                    const kpi = _computeKpi(source, cfg.kpi.agg);
                    cfg.kpiValue = kpi.value;
                    cfg.kpiSub = kpi.sub;
                }
            }

            window.dashboardLayout.addChart(cfg);

        } catch (error) {
            console.error(`Error adding chart ${index + 1}:`, error);
            Notifications.error(`Failed to render chart: ${chartConfig.title}`);
        }
    });

    // Arm layout persistence once gridstack has settled from the initial load
    setTimeout(() => { _layoutReady = true; }, 800);

    // Sync the auto-refresh selector with the saved setting (starts the timer once)
    let arSecs = config.autoRefreshSecs || 0;
    // CH-10: 1-min blind polling was removed (change-detection covers it) —
    // migrate old dashboards saved with 60s to the 5-min forced re-run.
    if (arSecs > 0 && arSecs < 300) arSecs = 300;
    const arSel = document.getElementById('dashAutoRefresh');
    if (arSel && parseInt(arSel.value, 10) !== arSecs) {
        arSel.value = String(arSecs);
        _startAutoRefresh(arSecs);
    }

    // Near-real-time: watch used datasets for source changes (push/interval)
    if (!_changePollTimer) _startChangePolling();

    // Show when the on-screen numbers were last queried
    _updateFreshnessBadge();
}

/**
 * Show error state
 */
function showError(message) {
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const errorMessage = document.getElementById('errorMessage');
    const dashboardGrid = document.getElementById('dashboardGrid');
    
    if (loadingState) loadingState.classList.add('hidden');
    if (dashboardGrid) dashboardGrid.classList.add('hidden');
    if (errorState) errorState.classList.remove('hidden');
    if (errorMessage) errorMessage.textContent = message;
    
    Notifications.error(message);
}

/**
 * Open layout modal
 */
function openLayoutModal() {
    const modal = document.getElementById('layoutModal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
}

/**
 * Close layout modal
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
    
    if (!layoutType || !window.dashboardLayout) {
        return;
    }
    
    console.log('Changing layout to:', layoutType);
    
    try {
        // Update layout
        window.dashboardLayout.setLayout(layoutType);
        
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
 * Export dashboard in the requested format.
 * PDF and PNG are rendered client-side (fast — no server Kaleido needed).
 * CSV and JSON are fetched from the server.
 * @param {string} format  'pdf' | 'png' | 'csv' | 'json'
 */
async function exportDashboard(format = 'json') {
    if (!dashboardId) { Notifications.error('Invalid dashboard ID'); return; }

    const LABELS = { html: 'Interactive HTML', pdf: 'PDF Report', png: 'PNG Images', csv: 'CSV Data', json: 'Dashboard File' };
    Loading.show(`Exporting ${LABELS[format] || format}…`);

    try {
        if (format === 'html') {
            await _exportInteractiveHtml();
        } else if (format === 'pdf') {
            await _exportPdfClientSide();
        } else if (format === 'png') {
            await _exportPngClientSide();
        } else if (format === 'json') {
            const exportData = await API.get(`/dashboards/${dashboardId}/export?format=json`, true);
            _triggerDownload(
                new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' }),
                `${(exportData.dashboard_name || 'dashboard').replace(/\s+/g, '_')}.json`
            );
        } else if (format === 'csv') {
            const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
            const url = `${CONFIG.API_BASE_URL}${CONFIG.API_V1}/dashboards/${dashboardId}/export?format=csv`;
            const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
            if (!res.ok) { let m = `HTTP ${res.status}`; try { m = (await res.json()).detail || m; } catch(_){} throw new Error(m); }
            const disp = res.headers.get('Content-Disposition') || '';
            const fname = (disp.match(/filename="([^"]+)"/) || [])[1]
                       || `${(currentDashboard?.name || 'dashboard').replace(/\s+/g, '_')}_data.zip`;
            _triggerDownload(await res.blob(), fname);
        }
        Notifications.success(`${LABELS[format] || format} downloaded`);
    } catch (error) {
        console.error('Export error:', error);
        if (format === 'json' && currentDashboard) { _exportJsonFromLocalData(); }
        else { Notifications.error(`Export failed: ${error.message || 'Unknown error'}`); }
    } finally {
        Loading.hide();
    }
}

/**
 * Interactive HTML export — one self-contained file with the full dashboard:
 * every page, every widget, saved layout and theme, and fully interactive
 * Plotly charts (hover, zoom, pan, legend toggling). Works offline, no login.
 * The Plotly library is inlined so the file has zero external dependencies.
 */
async function _exportInteractiveHtml() {
    const html = await _buildInteractiveExportHtml();
    const safeName = (currentDashboard.name || 'dashboard').replace(/\s+/g, '_');
    _triggerDownload(new Blob([html], { type: 'text/html' }), `${safeName}_interactive.html`);
}

/**
 * "Preview Dashboard" toolbar button — builds the exact same standalone HTML
 * the Export > Interactive HTML download produces, but opens it in a new tab
 * instead of saving a file, so you can see exactly what the exported version
 * will look like before actually exporting it.
 */
async function previewDashboardExport() {
    if (!dashboardId) { Notifications.error('Invalid dashboard ID'); return; }
    Loading.show('Building preview…');
    try {
        const html = await _buildInteractiveExportHtml();
        const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
        const win = window.open(url, '_blank');
        if (!win) {
            Notifications.error('Preview blocked by the browser — allow pop-ups for this site and try again.');
            URL.revokeObjectURL(url);
            return;
        }
        // Release the blob once the preview tab has actually loaded it —
        // revoking too early would break the tab before it finishes reading it.
        win.addEventListener('load', () => URL.revokeObjectURL(url));
        setTimeout(() => URL.revokeObjectURL(url), 60000); // safety net if 'load' never fires
    } catch (error) {
        console.error('Preview error:', error);
        Notifications.error(`Could not build preview: ${error.message || 'Unknown error'}`);
    } finally {
        Loading.hide();
    }
}

async function _buildInteractiveExportHtml() {
    if (!currentDashboard) throw new Error('Dashboard not loaded');
    _flushPendingSave();   // preview/export exactly what's on screen

    const cfg   = currentDashboard.config_json;
    const pages = _ensurePages();
    const theme = cfg.theme || 'light';
    const dark  = theme === 'dark';
    const esc   = _escHtml;

    // ── Inline the Plotly library for a fully offline file ───────────────────
    Loading.show('Bundling chart engine…');
    let plotlySrc = '';
    try {
        const res = await fetch('https://cdn.plot.ly/plotly-2.26.0.min.js');
        if (res.ok) plotlySrc = await res.text();
    } catch (_) { /* fall through to CDN reference */ }
    const plotlyTag = plotlySrc
        ? `<script>${plotlySrc.replace(/<\/script/gi, '<\\/script')}<\/script>`
        : `<script src="https://cdn.plot.ly/plotly-2.26.0.min.js"><\/script>`;

    Loading.show('Building interactive HTML…');

    // ── Theme-patch chart specs (same rules as the live renderer) ────────────
    const patchSpec = (raw) => {
        if (!raw) return null;
        const layout = {
            ...raw.layout,
            autosize: true,
            margin: { l: 60, r: 30, t: 40, b: 60 },
            ...(dark ? {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor:  'rgba(0,0,0,0)',
                font:   { ...(raw.layout?.font || {}), color: '#cbd5e1' },
                xaxis:  { ...(raw.layout?.xaxis || {}), gridcolor: '#334155', zerolinecolor: '#475569' },
                yaxis:  { ...(raw.layout?.yaxis || {}), gridcolor: '#334155', zerolinecolor: '#475569' },
                legend: { ...(raw.layout?.legend || {}), font: { color: '#cbd5e1' } },
            } : {}),
        };
        return { data: raw.data, layout };
    };

    // ── Build widget HTML + collect chart specs ───────────────────────────────
    const specs = {};
    let specCounter = 0;
    const allCharts = cfg.charts || [];

    const gridStyle = (c) => {
        const l = c.layout;
        if (l && Number.isFinite(l.x)) {
            return `grid-column:${l.x + 1} / span ${l.w}; grid-row:${l.y + 1} / span ${l.h};`;
        }
        const spanBySize = { small: 4, medium: 6, large: 8, full: 12 };
        const wt = c.widget_type || 'chart';
        const span = wt === 'kpi' ? 3 : wt === 'text' ? 4 : wt === 'divider' ? 12 : (spanBySize[c.size] || 6);
        const rows = wt === 'kpi' ? 3 : wt === 'text' ? 4 : wt === 'divider' ? 1 : 7;
        return `grid-column:auto / span ${span}; grid-row:auto / span ${rows};`;
    };

    const widgetHtml = (c) => {
        const wt = c.widget_type || 'chart';
        const style = gridStyle(c);
        if (wt === 'divider') {
            return `<div class="item divider" style="${style}">
                ${c.title ? `<span>${esc(c.title)}</span>` : ''}<hr></div>`;
        }
        if (wt === 'kpi') {
            let val = c.kpiValue ?? '—', sub = c.kpiSub || '';
            if (c.kpi?.sourceId && window.computeKpiFromChart) {
                const source = allCharts.find(x => x.id === c.kpi.sourceId);
                if (source) { const k = window.computeKpiFromChart(source, c.kpi.agg); val = k.value; sub = k.sub; }
            }
            const kpiFontMap = { sm: '1.6rem', base: '2.2rem', lg: '2.8rem', xl: '3.4rem' };
            const kpiFontSize = kpiFontMap[c.style?.kpiSize] || kpiFontMap.base;
            const kpiTitleFontMap = { sm: '.82rem', base: '.9rem', lg: '1rem' };
            const kpiTitleFontSize = kpiTitleFontMap[c.style?.kpiTitleSize] || kpiTitleFontMap.sm;
            const kpiTitleColor = c.style?.kpiTitleColor || '#6b7280';
            const showSub = sub && !c.style?.hideKpiSub;
            return `<div class="item card kpi" style="${style}">
                <div class="card-head" style="font-size:${kpiTitleFontSize};color:${kpiTitleColor}">${esc(c.title || 'KPI')}</div>
                <div class="kpi-body"><span class="kpi-num" style="font-size:${kpiFontSize}">${esc(val)}</span>
                ${showSub ? `<span class="kpi-sub">${esc(sub)}</span>` : ''}</div></div>`;
        }
        if (wt === 'text') {
            const body = esc(c.body || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
            return `<div class="item card" style="${style}">
                <div class="card-head">${esc(c.title || 'Note')}</div>
                <div class="text-body">${body}</div></div>`;
        }
        // chart
        const sid = `c${specCounter++}`;
        specs[sid] = patchSpec(c.plotlySpec);
        return `<div class="item card" style="${style}">
            <div class="card-head">${esc(c.title || 'Chart')}</div>
            <div class="plot" id="${sid}"></div></div>`;
    };

    const pagesHtml = pages.map((p, i) => {
        const ids = new Set(p.chartIds || []);
        const widgets = allCharts.filter(c => ids.has(c.id)).map(widgetHtml).join('\n');
        return `<div class="page${i === 0 ? ' active' : ''}" data-page="${i}">
            <div class="grid">${widgets || '<p class="empty">This page has no widgets.</p>'}</div></div>`;
    }).join('\n');

    const tabsHtml = pages.length > 1
        ? `<nav class="tabs">${pages.map((p, i) =>
            `<button class="tab${i === 0 ? ' active' : ''}" data-page="${i}">${esc(p.name)}</button>`).join('')}</nav>`
        : '';

    const specsJson = JSON.stringify(specs).replace(/</g, '\\u003c');
    const exportedAt = new Date().toLocaleString();

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(currentDashboard.name)} — Interactive Dashboard</title>
${plotlyTag}
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: ${dark ? '#0f172a' : '#f8fafc'};
         color: ${dark ? '#e2e8f0' : '#1f2937'}; padding: 24px; }
  header { max-width: 1280px; margin: 0 auto 20px; }
  h1 { font-size: 1.7rem; font-weight: 800; }
  .desc { color: ${dark ? '#94a3b8' : '#6b7280'}; margin-top: 4px; }
  .meta { font-size: .75rem; color: ${dark ? '#64748b' : '#9ca3af'}; margin-top: 8px; }
  .tabs { max-width: 1280px; margin: 0 auto 12px; display: flex; gap: 4px;
          border-bottom: 1px solid ${dark ? '#334155' : '#e5e7eb'}; overflow-x: auto; }
  .tab { padding: 8px 18px; border: none; background: none; font: inherit; font-weight: 600;
         font-size: .875rem; color: ${dark ? '#94a3b8' : '#6b7280'}; cursor: pointer;
         border-radius: 10px 10px 0 0; }
  .tab.active { color: ${dark ? '#5eead4' : '#0d9488'}; background: ${dark ? '#1e293b' : '#fff'};
         border: 1px solid ${dark ? '#334155' : '#e5e7eb'}; border-bottom: none; }
  .page { display: none; max-width: 1280px; margin: 0 auto; }
  .page.active { display: block; }
  .grid { display: grid; grid-template-columns: repeat(12, 1fr); grid-auto-rows: 70px; gap: 8px; }
  .card { background: ${dark ? '#1e293b' : '#fff'}; border-radius: 10px; overflow: hidden;
          box-shadow: 0 2px 10px rgba(0,0,0,${dark ? '.4' : '.07'}); display: flex; flex-direction: column; }
  .card-head { padding: 9px 14px; font-size: .82rem; font-weight: 700;
          background: ${dark ? '#16213a' : '#f9fafb'}; border-bottom: 1px solid ${dark ? '#334155' : '#f3f4f6'}; }
  .plot { flex: 1; min-height: 0; }
  .kpi-body { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 12px 12px; text-align: center; }
  .kpi-num { font-size: 2.2rem; font-weight: 800; color: ${dark ? '#5eead4' : '#0d9488'}; }
  .kpi-sub { font-size: .7rem; color: ${dark ? '#64748b' : '#9ca3af'}; margin-top: 4px; }
  .text-body { flex: 1; padding: 12px 14px; font-size: .85rem; line-height: 1.55;
          color: ${dark ? '#94a3b8' : '#4b5563'}; overflow-y: auto; }
  .divider { display: flex; align-items: center; gap: 12px; }
  .divider span { font-size: .72rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
          color: ${dark ? '#64748b' : '#9ca3af'}; white-space: nowrap; }
  .divider hr { flex: 1; border: none; border-top: 2px solid ${dark ? '#334155' : '#e5e7eb'}; }
  .empty { grid-column: 1 / -1; text-align: center; color: #9ca3af; padding: 60px 0; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr; grid-auto-rows: auto; }
          .item { grid-column: auto !important; grid-row: auto !important; }
          .plot { min-height: 320px; } }
</style>
</head>
<body>
<header>
  <p class="meta">Interactive export · generated ${esc(exportedAt)} · BI Dashboard Generator</p>
</header>
${tabsHtml}
${pagesHtml}
<script>
const SPECS = ${specsJson};
const rendered = new Set();
function renderPage(pageEl) {
  pageEl.querySelectorAll('.plot').forEach(el => {
    if (rendered.has(el.id) || !SPECS[el.id]) return;
    Plotly.newPlot(el, SPECS[el.id].data, SPECS[el.id].layout,
      { responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
    rendered.add(el.id);
  });
}
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const page = document.querySelector('.page[data-page="' + tab.dataset.page + '"]');
    page.classList.add('active');
    renderPage(page);
    page.querySelectorAll('.plot').forEach(el => { try { el.data && el.data.some(t => t.type === 'pie') ? Plotly.react(el, el.data, el.layout) : Plotly.Plots.resize(el); } catch(e){} });
  });
});
renderPage(document.querySelector('.page.active'));
window.addEventListener('resize', () => {
  document.querySelectorAll('.page.active .plot').forEach(el => { try { el.data && el.data.some(t => t.type === 'pie') ? Plotly.react(el, el.data, el.layout) : Plotly.Plots.resize(el); } catch(e){} });
});
<\/script>
</body>
</html>`;

    return html;
}

/**
 * Capture each rendered chart as PNG via Plotly.toImage(), then POST the images
 * to the server for fast PDF assembly (no Kaleido on the server side).
 */
async function _exportPdfClientSide() {
    const charts = window.dashboardLayout?.charts || [];
    if (!charts.length) throw new Error('No charts to export');

    const chartPayload = [];
    for (let i = 0; i < charts.length; i++) {
        const ch = charts[i];
        const canvas = ch.element?.querySelector('.chart-canvas');
        Loading.show(`Rendering chart ${i + 1} of ${charts.length}…`);

        let imgB64 = '';
        if (canvas) {
            try {
                imgB64 = await Plotly.toImage(canvas, { format: 'png', width: 1200, height: 550, scale: 2 });
            } catch (e) {
                console.warn('Plotly.toImage failed for chart', ch.config?.title, e);
            }
        }

        chartPayload.push({
            title: ch.config?.title || `Chart ${i + 1}`,
            image_b64: imgB64,
            insights: ch.config?.queryResult?.insights || [],
        });
    }

    Loading.show('Assembling PDF…');
    const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
    const res = await fetch(
        `${CONFIG.API_BASE_URL}${CONFIG.API_V1}/dashboards/${dashboardId}/export/pdf`,
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
                dashboard_name: currentDashboard?.name || 'Dashboard',
                description: currentDashboard?.description || '',
                charts: chartPayload,
            }),
        }
    );
    if (!res.ok) { let m = `HTTP ${res.status}`; try { m = (await res.json()).detail || m; } catch(_){} throw new Error(m); }
    const safeName = (currentDashboard?.name || 'dashboard').replace(/\s+/g, '_');
    _triggerDownload(await res.blob(), `${safeName}.pdf`);
}

/**
 * Capture each rendered chart as PNG via Plotly.toImage(), then bundle into a
 * ZIP file in the browser using JSZip (no server round-trip needed).
 */
async function _exportPngClientSide() {
    const charts = window.dashboardLayout?.charts || [];
    if (!charts.length) throw new Error('No charts to export');
    if (typeof JSZip === 'undefined') throw new Error('JSZip library not loaded');

    const zip = new JSZip();
    let rendered = 0;

    for (let i = 0; i < charts.length; i++) {
        const ch = charts[i];
        const canvas = ch.element?.querySelector('.chart-canvas');
        Loading.show(`Rendering chart ${i + 1} of ${charts.length}…`);

        if (!canvas) continue;
        try {
            const dataUrl = await Plotly.toImage(canvas, { format: 'png', width: 1200, height: 600, scale: 2 });
            // dataUrl = "data:image/png;base64,<base64>"
            const b64 = dataUrl.split(',')[1];
            const slug = (ch.config?.title || `chart_${i + 1}`).replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40);
            zip.file(`${String(i + 1).padStart(2, '0')}_${slug}.png`, b64, { base64: true });
            rendered++;
        } catch (e) {
            console.warn('Plotly.toImage failed for chart', ch.config?.title, e);
        }
    }

    if (rendered === 0) throw new Error('No charts could be rendered to PNG');

    Loading.show('Building ZIP…');
    const zipBlob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
    const safeName = (currentDashboard?.name || 'dashboard').replace(/\s+/g, '_');
    _triggerDownload(zipBlob, `${safeName}_charts.zip`);
}

/** Trigger a browser file download from a Blob. */
function _triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/** JSON fallback: download from in-memory dashboard object when API is unreachable. */
function _exportJsonFromLocalData() {
    if (!currentDashboard) return;
    const exportData = {
        dashboard_name: currentDashboard.name,
        exported_at: new Date().toISOString(),
        charts: currentDashboard.config_json?.charts || [],
        data: {
            description: currentDashboard.description,
            layout: currentDashboard.config_json?.layout || 'grid',
            chart_count: currentDashboard.config_json?.charts?.length || 0,
            created_at: currentDashboard.created_at,
            updated_at: currentDashboard.updated_at,
        },
    };
    _triggerDownload(
        new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' }),
        `${currentDashboard.name.replace(/\s+/g, '_')}.json`
    );
    Notifications.success('JSON exported from local data');
}

// ─── Edit Chart ────────────────────────────────────────────────────────────

let editingChartId = null;      // layout-internal id (e.g. "chart-0")
let editingChartConfig = null;  // the chart's config object from currentDashboard

/**
 * Called by DashboardLayout when the pencil button is clicked.
 * chartId is the layout-internal id string.
 */
/** hex -> [h, s, l] (degrees, percent, percent) — same conversion query.js uses. */
function _hexToHsl(hex) {
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h, s;
    const l = (max + min) / 2;
    if (max === min) {
        h = s = 0;
    } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            default: h = (r - g) / d + 4;
        }
        h /= 6;
    }
    return [h * 360, s * 100, l * 100];
}

function _hslToHex(h, s, l) {
    s /= 100; l /= 100;
    const k = n => (n + h / 30) % 12;
    const a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    const toHex = x => Math.round(255 * x).toString(16).padStart(2, '0');
    return `#${toHex(f(0))}${toHex(f(8))}${toHex(f(4))}`;
}

/** Light-to-dark gradient of N related colors from one base color. */
function _generateShades(baseHex, n) {
    if (n <= 1) return [baseHex];
    const [h, s] = _hexToHsl(baseHex);
    const sat = Math.max(s, 35);
    const lightMax = 82, lightMin = 28;
    const shades = [];
    for (let i = 0; i < n; i++) {
        const l = lightMax - (i / (n - 1)) * (lightMax - lightMin);
        shades.push(_hslToHex(h, sat, l));
    }
    return shades;
}

/** Best-effort current color read from a saved chart's spec, for pre-filling the color input. */
function _extractChartColor(spec) {
    const t = spec?.data?.[0];
    const hexRe = /^#[0-9a-fA-F]{6}$/;
    if (!t) return '#0d9488';
    if (t.type === 'pie' && Array.isArray(t.marker?.colors) && hexRe.test(t.marker.colors[0])) return t.marker.colors[0];
    if (typeof t.marker?.color === 'string' && hexRe.test(t.marker.color)) return t.marker.color;
    if (typeof t.line?.color === 'string' && hexRe.test(t.line.color)) return t.line.color;
    return '#0d9488';
}

/**
 * Same per-chart-type coloring rules as Query Builder's applyChartColor —
 * pie needs marker.colors (plural, array), multi-trace charts (stacked bar,
 * multi-series line) need one shade per trace, single-trace charts get a
 * flat color. Operates on a plain spec object (not a live Plotly element),
 * since this recolors a SAVED chart before persisting it.
 */
function _applyColorToPlotlySpec(spec, color) {
    if (!spec || !Array.isArray(spec.data)) return spec;
    const traces = spec.data;
    const n = traces.length;
    const pieIndices = traces.map((t, i) => (t.type === 'pie' ? i : -1)).filter(i => i >= 0);
    const newData = traces.map(t => ({ ...t }));

    if (pieIndices.length) {
        pieIndices.forEach(i => {
            const sliceCount = (newData[i].labels || newData[i].values || []).length || 1;
            newData[i].marker = { ...(newData[i].marker || {}), colors: _generateShades(color, sliceCount) };
        });
        newData.forEach((t, i) => {
            if (pieIndices.includes(i)) return;
            t.marker = { ...(t.marker || {}), color };
            if (t.line) t.line = { ...t.line, color };
        });
    } else if (n > 1) {
        const shades = _generateShades(color, n);
        newData.forEach((t, i) => {
            t.marker = { ...(t.marker || {}), color: shades[i] };
            if (t.line) t.line = { ...t.line, color: shades[i] };
        });
    } else if (n === 1) {
        newData[0].marker = { ...(newData[0].marker || {}), color };
        if (newData[0].line) newData[0].line = { ...newData[0].line, color };
    }

    return { ...spec, data: newData };
}

function openEditChartModal(chartId) {
    const layoutChart = window.dashboardLayout.charts.find(c => c.id === chartId);
    if (!layoutChart) return;
    editingChartId = chartId;
    editingChartConfig = layoutChart.config;

    const cfg = editingChartConfig;
    document.getElementById('editChartTitle').value = cfg.title || '';
    document.getElementById('editChartSize').value = cfg.size || 'medium';
    document.getElementById('editChartColor').value = _extractChartColor(cfg.plotlySpec);
    document.getElementById('editChartDataset').textContent = cfg.dataset?.name || 'Unknown';
    document.getElementById('editChartTemplate').textContent = cfg.template?.name || cfg.template?.type || 'Unknown';

    // Page assignment dropdown
    const pageSel = document.getElementById('editChartPage');
    if (pageSel && currentDashboard) {
        const pages = _ensurePages();
        pageSel.innerHTML = '';
        pages.forEach((p, i) => {
            const o = document.createElement('option');
            o.value = i;
            o.textContent = p.name;
            if ((p.chartIds || []).includes(cfg.id)) o.selected = true;
            pageSel.appendChild(o);
        });
    }

    buildEditParamFields(cfg);

    const modal = document.getElementById('editChartModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeEditChartModal() {
    const modal = document.getElementById('editChartModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    editingChartId = null;
    editingChartConfig = null;
}

function buildEditParamFields(config) {
    const container = document.getElementById('editChartParams');
    container.innerHTML = '';
    const storedParams = config.queryResult?.parameters || config.parameters || {};
    if (Object.keys(storedParams).length === 0) {
        container.innerHTML = '<p class="text-sm text-gray-400">No parameters available — only title and size can be changed.</p>';
        return;
    }
    Object.entries(storedParams).forEach(([key, val]) => {
        const div = document.createElement('div');
        div.innerHTML = `
            <label class="block text-xs font-medium text-gray-600 mb-1">${key}</label>
            <input type="text" id="edit-param-${key}" value="${String(val).replace(/"/g, '&quot;')}"
                class="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
        `;
        container.appendChild(div);
    });
}

async function handleSaveChart(e) {
    e.preventDefault();
    if (!editingChartId || !editingChartConfig) return;

    const newTitle = document.getElementById('editChartTitle').value.trim() || editingChartConfig.title;
    const newSize = document.getElementById('editChartSize').value;

    const storedParams = editingChartConfig.queryResult?.parameters || editingChartConfig.parameters || {};
    const newParams = {};
    let paramsChanged = false;
    Object.keys(storedParams).forEach(key => {
        const input = document.getElementById(`edit-param-${key}`);
        if (input) {
            newParams[key] = input.value;
            if (String(input.value) !== String(storedParams[key])) paramsChanged = true;
        }
    });

    try {
        Loading.show('Saving chart…');

        let newPlotlySpec = editingChartConfig.plotlySpec;

        if (paramsChanged && editingChartConfig.dataset?.id && editingChartConfig.template?.type) {
            const response = await API.post('/queries/execute', {
                template_type: editingChartConfig.template.type,
                dataset_id: editingChartConfig.dataset.id,
                parameters: newParams
            }, true);
            if (response && response.plotly_spec) {
                newPlotlySpec = response.plotly_spec;
            }
        }

        const newColor = document.getElementById('editChartColor')?.value;
        if (newColor) newPlotlySpec = _applyColorToPlotlySpec(newPlotlySpec, newColor);

        // Patch the chart in currentDashboard.config_json.charts
        const charts = currentDashboard.config_json.charts;
        const idx = charts.findIndex(c => c.id === editingChartConfig.id);
        if (idx !== -1) {
            charts[idx] = {
                ...charts[idx],
                title: newTitle,
                size: newSize,
                plotlySpec: newPlotlySpec,
                ...(paramsChanged ? { parameters: newParams, queryResult: { ...charts[idx].queryResult, parameters: newParams } } : {})
            };
        }

        // Move to another page if requested
        const targetPage = parseInt(document.getElementById('editChartPage')?.value ?? '-1', 10);
        if (!isNaN(targetPage) && targetPage >= 0 && currentDashboard.config_json.pages) {
            const pages = _ensurePages();
            pages.forEach(p => {
                p.chartIds = (p.chartIds || []).filter(id => id !== editingChartConfig.id);
            });
            if (pages[targetPage] && !pages[targetPage].chartIds.includes(editingChartConfig.id)) {
                pages[targetPage].chartIds.push(editingChartConfig.id);
            }
        }

        // Persist to backend
        await API.put(`/dashboards/${dashboardId}`, {
            config_json: currentDashboard.config_json
        }, true);

        closeEditChartModal();
        Notifications.success('Chart updated!');
        renderDashboard();

    } catch (err) {
        console.error('Error saving chart:', err);
        Notifications.error('Failed to save chart: ' + (err.message || 'Unknown error'));
    } finally {
        Loading.hide();
    }
}

/**
 * Initialize page when DOM is loaded
 */
document.addEventListener('DOMContentLoaded', () => {
    // Check if DashboardLayout is available
    if (!window.DashboardLayout) {
        console.error('DashboardLayout module not loaded!');
        showError('Failed to load dashboard components. Please refresh the page.');
        return;
    }

    // Initialize view dashboard page
    initViewDashboardPage();
});

// ── Schedule Report Modal ─────────────────────────────────────────────────────

let _lastSavedScheduleId = null;
let _editingScheduleId = null;   // when set, Save updates instead of creating

const _COMMON_TIMEZONES = [
    'UTC', 'Asia/Karachi', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Singapore',
    'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Chicago',
    'America/Los_Angeles', 'Australia/Sydney',
];

function _initTimezoneSelect() {
    const sel = document.getElementById('scheduleTimezone');
    if (!sel || sel.options.length > 0) return;
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const zones = [...new Set([browserTz, ..._COMMON_TIMEZONES])];
    zones.forEach(tz => {
        const o = document.createElement('option');
        o.value = tz;
        o.textContent = tz === browserTz ? `${tz} (your timezone)` : tz;
        sel.appendChild(o);
    });
    sel.value = browserTz;
}

function _initDomSelect() {
    const sel = document.getElementById('scheduleDom');
    if (!sel || sel.options.length > 0) return;
    for (let d = 1; d <= 31; d++) {
        const o = document.createElement('option');
        o.value = d;
        o.textContent = `Day ${d}`;
        sel.appendChild(o);
    }
    _renderDomGrid();
}

const _CAL_WEEKDAY_LABELS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
const _CAL_MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];

// Which month/year the calendar is currently browsing — independent of the
// selected day. Reset to the real current month each time the modal opens.
let _calViewYear  = null;
let _calViewMonth = null;

function _resetCalendarView() {
    const today = new Date();
    _calViewYear  = today.getFullYear();
    _calViewMonth = today.getMonth();
}

/**
 * Real, navigable calendar for picking a day-of-month. Shows the true weekday
 * alignment and true day count (28/29/30/31) for whatever month is being
 * browsed — Prev/Next just change the browsed month, they never change WHAT
 * gets saved (the schedule recurs every month; only the day NUMBER is
 * stored). Every day 1-31 is selectable; if the saved day doesn't exist in a
 * given month, the backend clamps the fire date to that month's last day.
 */
function _renderDomGrid() {
    const grid = document.getElementById('scheduleDomGrid');
    const sel  = document.getElementById('scheduleDom');
    const monthLabel = document.getElementById('scheduleDomMonthLabel');
    if (!grid || !sel) return;
    if (_calViewYear === null) _resetCalendarView();
    const current = parseInt(sel.value || '1', 10);
    grid.innerHTML = '';

    if (monthLabel) {
        monthLabel.textContent = `${_CAL_MONTH_NAMES[_calViewMonth]} ${_calViewYear}`;
    }

    // Weekday header row (Monday-first)
    _CAL_WEEKDAY_LABELS.forEach(lbl => {
        const h = document.createElement('div');
        h.textContent = lbl;
        h.className = 'text-center text-[10px] font-bold text-gray-400 uppercase pb-1';
        grid.appendChild(h);
    });

    // Leading blank cells so day 1 lands on its real weekday for the browsed month
    const firstWeekday = new Date(_calViewYear, _calViewMonth, 1).getDay(); // 0=Sun..6=Sat
    const leadBlanks = (firstWeekday + 6) % 7; // convert to Monday-first (0=Mon..6=Sun)
    for (let i = 0; i < leadBlanks; i++) {
        grid.appendChild(document.createElement('div'));
    }

    const daysInMonth = new Date(_calViewYear, _calViewMonth + 1, 0).getDate(); // 28-31
    for (let d = 1; d <= daysInMonth; d++) {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = d;
        b.title = d > 28
            ? `The ${d}${_ordinalSuffix(d)} — clamps to the last day in shorter months`
            : `The ${d}${_ordinalSuffix(d)} of every month`;
        b.className = d === current
            ? 'py-1.5 rounded-lg text-sm font-bold bg-blue-600 text-white'
            : 'py-1.5 rounded-lg text-sm font-semibold text-gray-600 border border-gray-200 hover:border-blue-400 hover:text-blue-600';
        b.addEventListener('click', () => {
            sel.value = String(d);
            _renderDomGrid();
            _updateScheduleNextRun();
        });
        grid.appendChild(b);
    }
}

function _ordinalSuffix(n) {
    if (n % 10 === 1 && n % 100 !== 11) return 'st';
    if (n % 10 === 2 && n % 100 !== 12) return 'nd';
    if (n % 10 === 3 && n % 100 !== 13) return 'rd';
    return 'th';
}

function _calNavigate(delta) {
    _calViewMonth += delta;
    if (_calViewMonth < 0)  { _calViewMonth = 11; _calViewYear--; }
    if (_calViewMonth > 11) { _calViewMonth = 0;  _calViewYear++; }
    _renderDomGrid();
}

function _updateDayPickers() {
    const freq = document.querySelector('input[name="scheduleFreq"]:checked')?.value;
    document.getElementById('scheduleDowWrap')?.classList.toggle('hidden', freq !== 'weekly');
    document.getElementById('scheduleDomWrap')?.classList.toggle('hidden', freq !== 'monthly');
    _renderDomGrid();          // keep the day grid highlight in sync
    _updateScheduleNextRun();
}

/** CH-16: compute and display exactly when the next report will fire. */
function _updateScheduleNextRun() {
    const el = document.getElementById('scheduleNextRun');
    if (!el) return;
    try {
        const freq = document.querySelector('input[name="scheduleFreq"]:checked')?.value || 'weekly';
        const [hh, mm] = (document.getElementById('scheduleTime')?.value || '08:00')
            .split(':').map(n => parseInt(n, 10));
        const tz  = document.getElementById('scheduleTimezone')?.value || 'UTC';
        const dow = parseInt(document.getElementById('scheduleDow')?.value || '0', 10);   // 0 = Monday
        const dom = parseInt(document.getElementById('scheduleDom')?.value || '1', 10);
        const wdMap = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

        const now = new Date();
        for (let i = 0; i < 62; i++) {
            const cand = new Date(now.getTime() + i * 86400000);
            const parts = new Intl.DateTimeFormat('en-US', {
                timeZone: tz, weekday: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit', hour12: false,
            }).formatToParts(cand);
            const get = (t) => parts.find(p => p.type === t)?.value;
            const dayOk = freq === 'daily'
                || (freq === 'weekly'  && wdMap[get('weekday')] === dow)
                || (freq === 'monthly' && parseInt(get('day'), 10) === dom);
            const timeOk = i > 0
                || (parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10)) < (hh * 60 + mm);
            if (dayOk && timeOk) {
                const dateLabel = new Intl.DateTimeFormat(undefined, {
                    timeZone: tz, weekday: 'long', day: 'numeric', month: 'short', year: 'numeric',
                }).format(cand);
                el.textContent = `Next report: ${dateLabel}, `
                    + `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')} (${tz})`;
                el.classList.remove('hidden');
                return;
            }
        }
        el.classList.add('hidden');
    } catch (_) {
        el.classList.add('hidden');
    }
}

function openScheduleModal() {
    const modal = document.getElementById('scheduleModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    _editingScheduleId = null;
    _resetCalendarView();   // always start the day-picker on the real current month
    _initTimezoneSelect();
    _initDomSelect();
    _scheduleHideStatus();
    _updateFreqPills();
    _updateDayPickers();
    const saveBtn = document.getElementById('saveScheduleBtn');
    if (saveBtn) saveBtn.textContent = 'Save Schedule';
    _loadScheduleList();
}

function closeScheduleModal() {
    const modal = document.getElementById('scheduleModal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    _hideDeleteConfirm();
}

function _updateFreqPills() {
    document.querySelectorAll('.freq-option').forEach(label => {
        const radio = label.querySelector('input[type="radio"]');
        const span  = label.querySelector('span');
        if (!radio || !span) return;
        if (radio.checked) {
            span.className = 'block text-center border-2 border-blue-500 bg-blue-50 text-blue-700 rounded-xl py-2.5 text-sm font-semibold cursor-pointer transition-colors';
        } else {
            span.className = 'block text-center border-2 border-gray-200 rounded-xl py-2.5 text-sm font-semibold cursor-pointer hover:border-blue-400 transition-colors';
        }
    });
}

function _scheduleShowStatus(msg, type = 'info') {
    const el = document.getElementById('scheduleStatus');
    if (!el) return;
    const colors = {
        success: 'bg-green-50 border-green-500 text-green-800',
        error:   'bg-red-50   border-red-500   text-red-800',
        info:    'bg-blue-50  border-blue-500  text-blue-800',
    };
    el.className = `border-l-4 p-3 rounded-lg text-sm ${colors[type] || colors.info}`;
    el.textContent = msg;
    el.classList.remove('hidden');
}

function _scheduleHideStatus() {
    document.getElementById('scheduleStatus')?.classList.add('hidden');
}

function _collectScheduleForm() {
    const email = document.getElementById('scheduleEmail')?.value.trim();
    const freq  = document.querySelector('input[name="scheduleFreq"]:checked')?.value;
    const time  = document.getElementById('scheduleTime')?.value || '08:00';
    const [hh, mm] = time.split(':').map(v => parseInt(v, 10));

    const body = {
        recipient_email: email,
        frequency:       freq,
        send_hour:       isNaN(hh) ? 8 : hh,
        send_minute:     isNaN(mm) ? 0 : mm,
        timezone:        document.getElementById('scheduleTimezone')?.value || 'UTC',
    };
    if (freq === 'weekly')  body.day_of_week  = parseInt(document.getElementById('scheduleDow')?.value ?? '0', 10);
    if (freq === 'monthly') body.day_of_month = parseInt(document.getElementById('scheduleDom')?.value ?? '1', 10);
    return body;
}

async function saveSchedule() {
    const body = _collectScheduleForm();

    if (!body.recipient_email) { _scheduleShowStatus('Please enter a recipient email.', 'error'); return; }
    if (!body.frequency)       { _scheduleShowStatus('Please select a frequency.',       'error'); return; }
    if (!dashboardId)          { _scheduleShowStatus('Dashboard not loaded yet.',        'error'); return; }

    const btn = document.getElementById('saveScheduleBtn');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    _scheduleHideStatus();

    try {
        let resp;
        if (_editingScheduleId) {
            resp = await API.put(`/schedules/${_editingScheduleId}`, body, true);
        } else {
            resp = await API.post('/schedules', {
                dashboard_id: parseInt(dashboardId, 10), ...body,
            }, true);
        }

        _lastSavedScheduleId = resp.id;
        const nextRun = resp.next_run ? new Date(resp.next_run).toLocaleString() : 'N/A';
        _scheduleShowStatus(
            `${_editingScheduleId ? 'Schedule updated' : 'Schedule saved'}! Next send: ${nextRun}`,
            'success'
        );
        Notifications.success(_editingScheduleId ? 'Schedule updated' : 'Report scheduled');
        _editingScheduleId = null;
        btn.textContent = 'Save Schedule';
        _loadScheduleList();
    } catch (err) {
        _scheduleShowStatus(err.message || 'Failed to save schedule.', 'error');
    } finally {
        btn.disabled = false;
        if (!_editingScheduleId) btn.textContent = 'Save Schedule';
    }
}

/** Populate the form from an existing schedule for editing. */
function _editSchedule(s) {
    _editingScheduleId = s.id;
    document.getElementById('scheduleEmail').value = s.recipient_email || '';
    document.querySelectorAll('input[name="scheduleFreq"]').forEach(r => {
        r.checked = r.value === s.frequency;
    });
    const hh = String(s.send_hour ?? 8).padStart(2, '0');
    const mm = String(s.send_minute ?? 0).padStart(2, '0');
    document.getElementById('scheduleTime').value = `${hh}:${mm}`;
    const tzSel = document.getElementById('scheduleTimezone');
    if (tzSel && s.timezone) {
        if (![...tzSel.options].some(o => o.value === s.timezone)) {
            const o = document.createElement('option');
            o.value = o.textContent = s.timezone;
            tzSel.appendChild(o);
        }
        tzSel.value = s.timezone;
    }
    if (s.day_of_week != null)  document.getElementById('scheduleDow').value = s.day_of_week;
    if (s.day_of_month != null) document.getElementById('scheduleDom').value = s.day_of_month;
    _updateFreqPills();
    _updateDayPickers();
    const saveBtn = document.getElementById('saveScheduleBtn');
    if (saveBtn) saveBtn.textContent = 'Update Schedule';
    _scheduleShowStatus(`Editing schedule for ${s.recipient_email} — change the fields above and click Update.`, 'info');
}

async function sendScheduleNow() {
    const email = document.getElementById('scheduleEmail')?.value.trim();
    const freq  = document.querySelector('input[name="scheduleFreq"]:checked')?.value;

    if (!email) { _scheduleShowStatus('Enter a recipient email first, then save the schedule before sending a test.', 'error'); return; }

    // If no schedule saved yet for this session, save it first
    if (!_lastSavedScheduleId) {
        await saveSchedule();
        if (!_lastSavedScheduleId) return;
    }

    const btn = document.getElementById('sendNowBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';
    _scheduleHideStatus();

    try {
        await API.post(`/schedules/${_lastSavedScheduleId}/send-now`, {}, true);
        _scheduleShowStatus(`Test report sent to ${email}!`, 'success');
        Notifications.success('Test email sent');
        _loadScheduleList();
    } catch (err) {
        _scheduleShowStatus(err.message || 'Send failed. Check email config in .env.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Send Test Now';
    }
}

async function _loadScheduleList() {
    const list = document.getElementById('scheduleList');
    if (!list || !dashboardId) return;

    try {
        const all = await API.get('/schedules', true);
        const mine = (all || []).filter(s => s.dashboard_id === parseInt(dashboardId, 10));

        if (!mine.length) {
            list.innerHTML = '<p class="text-sm text-gray-400">No active schedules for this dashboard.</p>';
            return;
        }

        const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        list.innerHTML = mine.map(s => {
            const nextRun  = s.next_run  ? new Date(s.next_run).toLocaleString()  : '—';
            const lastRun  = s.last_run  ? new Date(s.last_run).toLocaleString()  : 'Never';
            const statusBadge = s.last_status === 'sent'
                ? '<span class="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">sent</span>'
                : s.last_status === 'failed'
                ? '<span class="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">failed</span>'
                : '';
            const hh = String(s.send_hour ?? 8).padStart(2, '0');
            const mm = String(s.send_minute ?? 0).padStart(2, '0');
            let when = `${s.frequency} at ${hh}:${mm}`;
            if (s.frequency === 'weekly'  && s.day_of_week  != null) when += ` (${DOW[s.day_of_week]})`;
            if (s.frequency === 'monthly' && s.day_of_month != null) when += ` (day ${s.day_of_month})`;
            if (s.timezone && s.timezone !== 'UTC') when += ` ${s.timezone}`;
            return `
            <div class="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3 text-sm gap-2">
                <div class="flex-1 min-w-0">
                    <p class="font-semibold text-gray-800 truncate">${s.recipient_email}</p>
                    <p class="text-gray-500 text-xs mt-0.5">
                        ${when} · Next: ${nextRun} · Last: ${lastRun} ${statusBadge}
                    </p>
                </div>
                <button onclick='_editSchedule(${JSON.stringify(s).replace(/'/g, "&#39;")})'
                        class="text-gray-400 hover:text-blue-500 transition-colors flex-shrink-0"
                        title="Edit schedule">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                </button>
                <button onclick="_deleteSchedule(${s.id})"
                        class="text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                        title="Delete schedule">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                    </svg>
                </button>
            </div>`;
        }).join('');
    } catch (_) {
        list.innerHTML = '<p class="text-sm text-red-500">Could not load schedules.</p>';
    }
}

let _pendingDeleteId = null;

function _deleteSchedule(scheduleId) {
    _pendingDeleteId = scheduleId;
    const banner = document.getElementById('deleteConfirmBanner');
    if (banner) {
        banner.classList.remove('hidden');
        banner.classList.add('flex');
    }
}

function _hideDeleteConfirm() {
    _pendingDeleteId = null;
    const banner = document.getElementById('deleteConfirmBanner');
    if (banner) {
        banner.classList.add('hidden');
        banner.classList.remove('flex');
    }
}

async function _confirmDelete() {
    const scheduleId = _pendingDeleteId;
    if (!scheduleId) return;
    _hideDeleteConfirm();
    try {
        const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
        await fetch(API.getUrl(`/schedules/${scheduleId}`), {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (_lastSavedScheduleId === scheduleId) _lastSavedScheduleId = null;
        Notifications.success('Schedule deleted');
        _loadScheduleList();
    } catch (err) {
        Notifications.error('Failed to delete schedule');
    }
}

// ── Collaboration Modal ───────────────────────────────────────────────────────

function openCollaborateModal() {
    const modal = document.getElementById('collaborateModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.getElementById('collaborateEmail').value = '';
    document.getElementById('collaborateRole').value = 'viewer';
    _loadCollaborators();
}

function closeCollaborateModal() {
    const modal = document.getElementById('collaborateModal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function _loadCollaborators() {
    const list = document.getElementById('collaboratorsList');
    if (!list || !dashboardId) return;

    list.innerHTML = '<p class="text-sm text-gray-400">Loading…</p>';
    try {
        const collabs = await API.get(`/dashboards/${dashboardId}/collaborators`, true);
        if (!collabs || collabs.length === 0) {
            list.innerHTML = '<p class="text-sm text-gray-400">No collaborators yet. Invite someone above.</p>';
            return;
        }
        list.innerHTML = collabs.map(c => {
            const roleBadge = c.role === 'editor'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-600';
            const since = c.created_at
                ? new Date(c.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
                : '';
            return `
            <div class="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3 text-sm gap-3">
                <div class="flex-1 min-w-0">
                    <p class="font-semibold text-gray-800 truncate">${c.full_name || c.email}</p>
                    <p class="text-gray-400 text-xs truncate">${c.email} · added ${since}</p>
                </div>
                <select onchange="_updateCollaboratorRole(${c.id}, this.value)"
                        class="border border-gray-200 rounded-lg px-2 py-1 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-indigo-400">
                    <option value="viewer" ${c.role === 'viewer' ? 'selected' : ''}>Viewer</option>
                    <option value="editor" ${c.role === 'editor' ? 'selected' : ''}>Editor</option>
                </select>
                <button onclick="_revokeCollaborator(${c.id})"
                        class="text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                        title="Remove collaborator">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>`;
        }).join('');
    } catch (err) {
        list.innerHTML = `<p class="text-sm text-red-500">${err.message || 'Could not load collaborators.'}</p>`;
    }
}

async function inviteCollaborator() {
    const email = document.getElementById('collaborateEmail')?.value.trim();
    const role  = document.getElementById('collaborateRole')?.value || 'viewer';
    if (!email) { Notifications.error('Enter an email address first.'); return; }

    const btn = document.getElementById('inviteCollaboratorBtn');
    btn.disabled = true;
    btn.textContent = 'Inviting…';

    try {
        await API.post(`/dashboards/${dashboardId}/collaborators`, { email, role }, true);
        document.getElementById('collaborateEmail').value = '';
        Notifications.success(`${email} invited as ${role}`);
        _loadCollaborators();
    } catch (err) {
        Notifications.error(err.message || 'Invite failed.');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Invite';
    }
}

async function _updateCollaboratorRole(collaboratorId, role) {
    try {
        await API.put(`/dashboards/${dashboardId}/collaborators/${collaboratorId}`, { role }, true);
        Notifications.success(`Role updated to ${role}`);
        _loadCollaborators();
    } catch (err) {
        Notifications.error(err.message || 'Failed to update role.');
        _loadCollaborators();
    }
}

async function _revokeCollaborator(collaboratorId) {
    try {
        const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
        const res = await fetch(
            API.getUrl(`/dashboards/${dashboardId}/collaborators/${collaboratorId}`),
            { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }
        );
        if (!res.ok) { let m = `HTTP ${res.status}`; try { m = (await res.json()).detail || m; } catch(_){} throw new Error(m); }
        Notifications.success('Collaborator removed');
        _loadCollaborators();
    } catch (err) {
        Notifications.error(err.message || 'Failed to remove collaborator.');
    }
}
