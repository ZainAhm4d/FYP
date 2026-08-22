/**
 * Dashboard Layout Module
 * 
 * Grid-based layout system for organizing multiple charts on dashboards.
 * Supports flexible grid layouts, responsive design, and chart management.
 * 
 * Features:
 * - Multiple layout modes (1-col, 2-col, 3-col, grid)
 * - Add/remove charts dynamically
 * - Responsive resizing
 * - Chart positioning
 * - Layout persistence
 * 
 * Usage:
 *   const layout = new DashboardLayout('dashboard-container');
 *   layout.addChart(chartId, plotlySpec, position);
 */

class DashboardLayout {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        
        if (!this.container) {
            throw new Error(`Dashboard container not found: ${containerId}`);
        }

        this.charts = [];
        this.layout = options.layout || 'grid'; // grid, 1-col, 2-col, 3-col
        this.chartIdCounter = 0;
        this.grid = null; // GridStack instance when drag-drop mode is active

        // Default options
        this.options = {
            minChartHeight: 400,
            chartSpacing: 16,
            enableResize: true,
            enableRemove: true,
            enableFullscreen: false,
            enableEdit: false,
            enableDragDrop: false,   // gridstack drag/resize designer mode
            staticGrid: false,       // gridstack positions applied but locked (public share view)
            theme: 'light',          // 'light' | 'dark' — affects Plotly spec patching
            ...options
        };

        // Drag-drop requires the gridstack library; fall back silently if absent
        this.useGrid = this.options.enableDragDrop && typeof window.GridStack !== 'undefined';

        this._initializeLayout();
    }

    /**
     * Initialize the dashboard layout structure
     *
     * @private
     */
    _initializeLayout() {
        this.container.innerHTML = '';
        if (this.useGrid) {
            this.container.className = 'grid-stack';
            this.grid = window.GridStack.init({
                column: 12,
                cellHeight: 70,
                margin: 8,
                handle: '.chart-header',      // drag by the card header only
                float: false,                 // auto-compact upward
                animate: true,
                staticGrid: this.options.staticGrid,  // read-only positions (share view)
            }, this.container);

            // Persist positions after any drag/resize
            this.grid.on('change', () => {
                this._syncLayoutsFromGrid();
                if (typeof window.onLayoutChanged === 'function') window.onLayoutChanged();
            });
            // Re-fit Plotly charts after a resize. Delay past gridstack's
            // 300ms size animation — resizing immediately measures the OLD
            // cell size and the chart stays wrong.
            this.grid.on('resizestop', (e, el) => {
                setTimeout(() => {
                    const gd = el.querySelector('.chart-canvas');
                    if (gd && gd.data && window.Plotly) {
                        try {
                            // Plotly.Plots.resize() doesn't reliably recompute
                            // pie/donut label leader-line geometry on an aspect
                            // ratio change — leaves stale connector lines. A
                            // full react() recomputes correctly.
                            if (gd.data.some(t => t.type === 'pie')) {
                                window.Plotly.react(gd, gd.data, gd.layout);
                            } else {
                                window.Plotly.Plots.resize(gd);
                            }
                        } catch (_) {}
                    }
                }, 350);
            });
        } else {
            this.container.className = this._getLayoutClasses();
        }
    }

    /** Default grid dimensions per widget/size (12-column grid). @private */
    _defaultDims(config) {
        const wt = config.widget_type || 'chart';
        if (wt === 'kpi')     return { w: 3,  h: 3 };
        if (wt === 'text')    return { w: 4,  h: 4 };
        if (wt === 'divider') return { w: 12, h: 1 };
        switch (config.size) {
            case 'small': return { w: 4,  h: 6 };
            case 'large': return { w: 8,  h: 7 };
            case 'full':  return { w: 12, h: 7 };
            default:      return { w: 6,  h: 7 };   // medium
        }
    }

    /** Copy the live gridstack node positions back into each chart's config. @private */
    _syncLayoutsFromGrid() {
        if (!this.grid) return;
        this.charts.forEach(chart => {
            const el = document.getElementById(`wrapper-${chart.id}`);
            const node = el && el.gridstackNode;
            if (node) {
                chart.config.layout = { x: node.x, y: node.y, w: node.w, h: node.h };
            }
        });
    }

    /**
     * Get CSS classes for current layout mode
     * 
     * @private
     */
    _getLayoutClasses() {
        const baseClasses = 'dashboard-grid gap-4';
        
        switch (this.layout) {
            case '1-col':
                return `${baseClasses} grid-cols-1`;
            case '2-col':
                return `${baseClasses} grid-cols-1 md:grid-cols-2`;
            case '3-col':
                return `${baseClasses} grid-cols-1 md:grid-cols-2 lg:grid-cols-3`;
            case 'grid':
            default:
                return `${baseClasses} grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3`;
        }
    }

    /**
     * Add a chart to the dashboard
     * 
     * @param {Object} chartConfig - Chart configuration
     *   {
     *     plotlySpec: Object,
     *     title: string,
     *     position: number,
     *     size: string ('small', 'medium', 'large', 'full')
     *   }
     * @returns {string} Chart ID
     */
    async addChart(chartConfig) {
        const chartId = `chart-${this.chartIdCounter++}`;
        const widgetType = chartConfig.widget_type || 'chart';

        let chartWrapper;

        if (this.useGrid) {
            // ── Gridstack mode: positioned, draggable, resizable ─────────────
            chartWrapper = document.createElement('div');
            chartWrapper.id = `wrapper-${chartId}`;
            chartWrapper.className = 'grid-stack-item';
            chartWrapper.innerHTML = `
                <div class="grid-stack-item-content" style="overflow:hidden;">
                    ${this._buildCardHTML(chartId, chartConfig)}
                </div>`;

            const dims = this._defaultDims(chartConfig);
            const saved = chartConfig.layout;
            this.grid.addWidget(chartWrapper, saved
                ? { x: saved.x, y: saved.y, w: saved.w, h: saved.h }
                : { w: dims.w, h: dims.h, autoPosition: true });
        } else {
            // ── Legacy CSS-grid mode ─────────────────────────────────────────
            chartWrapper = this._createChartWrapper(chartId, chartConfig);
            if (chartConfig.position !== undefined && chartConfig.position < this.charts.length) {
                const referenceChart = this.charts[chartConfig.position];
                const referenceElement = document.getElementById(`wrapper-${referenceChart.id}`);
                this.container.insertBefore(chartWrapper, referenceElement);
            } else {
                this.container.appendChild(chartWrapper);
            }
        }

        // Render the Plotly figure (chart widgets only).
        // Patch the spec: the chart title is already in the HTML header, so remove it from
        // the Plotly figure and use the freed space for a larger bottom margin so the
        // x-axis title is never cut off.
        if (widgetType === 'chart') {
            const chartContainer = chartWrapper.querySelector('.chart-canvas');
            const rawSpec = chartConfig.plotlySpec;
            const dark = this.options.theme === 'dark';
            const palette = this.options.design?.paletteColors || null;

            // Recolor traces when a dashboard-level palette is chosen
            const paletteData = (palette && rawSpec?.data)
                ? rawSpec.data.map((t, i) => {
                    const c = palette[i % palette.length];
                    const out = { ...t };
                    if (t.type === 'pie') {
                        out.marker = { ...(t.marker || {}), colors: palette };
                    } else {
                        if (t.marker && !Array.isArray(t.marker.color)) out.marker = { ...t.marker, color: c };
                        else if (!t.marker) out.marker = { color: c };
                        if (t.line) out.line = { ...t.line, color: c };
                    }
                    return out;
                })
                : rawSpec?.data;

            // Strip fixed pixel dimensions: a hardcoded layout.height defeats
            // autosize — the chart keeps its original size when the card is
            // resized and gets clipped by overflow:hidden.
            const { width: _fixedW, height: _fixedH, ...fluidLayout } = rawSpec?.layout || {};

            const patchedSpec = rawSpec ? {
                ...rawSpec,
                data: paletteData,
                layout: {
                    ...fluidLayout,
                    autosize: true,
                    ...(palette ? { colorway: palette } : {}),
                    title: { text: '' },
                    // CH-13: automargin lets axis titles/tick labels reflow when the
                    // card is resized instead of clipping (also fixes old saved specs
                    // that carry fixed margins). Floors keep small cards readable.
                    margin: {
                        l: Math.max(45, Math.min(rawSpec.layout?.margin?.l ?? 60, 60)),
                        r: Math.max(20, Math.min(rawSpec.layout?.margin?.r ?? 30, 40)),
                        t: 30,
                        b: Math.max(40, Math.min(rawSpec.layout?.margin?.b ?? 60, this.useGrid ? 60 : 120))
                    },
                    xaxis: { automargin: true, ...(fluidLayout.xaxis || {}) },
                    yaxis: { automargin: true, ...(fluidLayout.yaxis || {}) },
                    ...(dark ? {
                        paper_bgcolor: 'rgba(0,0,0,0)',
                        plot_bgcolor:  'rgba(0,0,0,0)',
                        font: { ...(rawSpec.layout?.font || {}), color: '#cbd5e1' },
                        xaxis: { automargin: true, ...(rawSpec.layout?.xaxis || {}), gridcolor: '#334155', zerolinecolor: '#475569', linecolor: '#475569' },
                        yaxis: { automargin: true, ...(rawSpec.layout?.yaxis || {}), gridcolor: '#334155', zerolinecolor: '#475569', linecolor: '#475569' },
                        legend: { ...(rawSpec.layout?.legend || {}), font: { color: '#cbd5e1' } },
                    } : {})
                }
            } : rawSpec;
            await window.chartRenderer.renderChart(chartContainer, patchedSpec);
        }

        // Store chart reference
        this.charts.push({
            id: chartId,
            config: chartConfig,
            element: chartWrapper
        });

        return chartId;
    }

    /**
     * Inner card HTML for any widget type (chart / text / kpi / divider).
     *
     * @private
     */
    _buildCardHTML(chartId, config) {
        const widgetType = config.widget_type || 'chart';
        const style = config.style || {};
        const esc = (s) => String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        const removeBtn = this.options.enableRemove ? `
            <button class="btn-icon text-red-600 hover:bg-red-50" onclick="window.dashboardLayout.removeChart('${chartId}')" title="Remove">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>` : '';

        // Format (paintbrush) button — opens the per-widget style popover
        const formatBtn = (this.options.enableEdit && typeof window.onWidgetFormatRequested === 'function') ? `
            <button class="btn-icon text-indigo-600 hover:bg-indigo-50" onclick="window.onWidgetFormatRequested('${chartId}')" title="Format widget">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"/>
                </svg>
            </button>` : '';

        // Visual style knobs (PowerBI-style formatting)
        const frameless = !!style.frameless;
        const cardShell = frameless
            ? 'chart-card h-full flex flex-col overflow-hidden'   // no bg, border, shadow
            : 'chart-card bg-white rounded-lg shadow-md h-full flex flex-col overflow-hidden';
        const headerShell = style.hideTitle
            ? `chart-header flex items-center justify-end px-2 py-1 cursor-move opacity-0 hover:opacity-100 transition-opacity`
            : null; // per-type defaults used below
        const fontSizeMap = { sm: '0.8rem', base: '0.9rem', lg: '1.1rem', xl: '1.4rem' };
        const textCss = [
            `font-size:${fontSizeMap[style.fontSize] || fontSizeMap.base}`,
            style.bold ? 'font-weight:700' : '',
            style.italic ? 'font-style:italic' : '',
            `text-align:${style.align || 'left'}`,
            style.textColor ? `color:${style.textColor}` : '',
        ].filter(Boolean).join(';');

        if (widgetType === 'divider') {
            return `
                <div class="chart-card h-full flex items-center gap-3 px-2 group">
                    <div class="chart-header flex items-center gap-3 flex-1 cursor-move">
                        ${config.title && !style.hideTitle ? `<span class="text-sm font-bold text-gray-500 uppercase tracking-widest whitespace-nowrap" style="${style.textColor ? `color:${style.textColor}` : ''}">${esc(config.title)}</span>` : ''}
                        <div class="flex-1 border-t-2 border-gray-200"></div>
                    </div>
                    <span class="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">${formatBtn}${removeBtn}</span>
                </div>`;
        }

        if (widgetType === 'kpi') {
            const accent = style.accent || this.options.design?.accent || '#0d9488';
            const kpiSizeMap = { sm: 'text-2xl', base: 'text-4xl', lg: 'text-5xl', xl: 'text-6xl' };
            const kpiSizeClass = kpiSizeMap[style.kpiSize] || kpiSizeMap.base;
            const kpiTitleSizeMap = { sm: 'text-xs', base: 'text-sm', lg: 'text-base' };
            const kpiTitleSizeClass = kpiTitleSizeMap[style.kpiTitleSize] || kpiTitleSizeMap.sm;
            const kpiTitleColor = style.kpiTitleColor || '#6b7280';
            const header = style.hideTitle
                ? `<div class="${headerShell}"><div class="chart-controls flex gap-1">${formatBtn}${removeBtn}</div></div>`
                : `<div class="chart-header flex items-center justify-between px-4 py-2 cursor-move">
                       <span class="${kpiTitleSizeClass} font-semibold uppercase tracking-wide truncate" style="color:${kpiTitleColor}">${esc(config.title || 'KPI')}</span>
                       <div class="chart-controls flex gap-1">${formatBtn}${removeBtn}</div>
                   </div>`;
            return `
                <div class="${cardShell}">
                    ${header}
                    <div class="flex-1 flex flex-col items-center justify-center px-4 pb-4 text-center">
                        <span class="kpi-value ${kpiSizeClass} font-extrabold leading-tight break-all" style="color:${accent}">${esc(config.kpiValue ?? '—')}</span>
                        ${(config.kpiSub && !style.hideKpiSub) ? `<span class="text-xs text-gray-400 mt-1.5">${esc(config.kpiSub)}</span>` : ''}
                    </div>
                </div>`;
        }

        if (widgetType === 'text') {
            const body = esc(config.body || '')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\n/g, '<br>');
            const header = style.hideTitle
                ? `<div class="${headerShell}"><div class="chart-controls flex gap-1">${formatBtn}${removeBtn}</div></div>`
                : `<div class="chart-header flex items-center justify-between px-4 py-2.5 ${frameless ? '' : 'border-b border-gray-100'} cursor-move">
                       <h3 class="text-sm font-bold text-gray-800 truncate">${esc(config.title || 'Note')}</h3>
                       <div class="chart-controls flex gap-1">${formatBtn}${removeBtn}</div>
                   </div>`;
            return `
                <div class="${cardShell}">
                    ${header}
                    <div class="flex-1 px-4 py-3 text-gray-600 leading-relaxed overflow-y-auto" style="${textCss}">${body}</div>
                </div>`;
        }

        // Default: chart card
        const title = config.title || 'Chart';
        const showControls = this.options.enableRemove || this.options.enableFullscreen || this.options.enableEdit;
        const chartHeader = style.hideTitle
            ? `<div class="${headerShell}"><div class="chart-controls flex gap-1">${formatBtn}${removeBtn}</div></div>`
            : `<div class="chart-header flex items-center justify-between px-4 py-3 ${frameless ? '' : 'border-b border-gray-200 bg-gray-50'} ${this.useGrid ? 'cursor-move' : ''}">
                <h3 class="text-base font-semibold text-gray-800 truncate">${esc(title)}</h3>
                ${showControls ? `
                    <div class="chart-controls flex gap-2">
                        ${this.options.enableEdit ? `
                            <button class="btn-icon text-blue-600 hover:bg-blue-50" onclick="window.onChartEditRequested('${chartId}')" title="Edit chart">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                </svg>
                            </button>` : ''}
                        ${formatBtn}
                        ${this.options.enableFullscreen ? `
                            <button class="btn-icon" onclick="window.dashboardLayout.toggleFullscreen('${chartId}')" title="Fullscreen">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
                                </svg>
                            </button>` : ''}
                        ${removeBtn}
                    </div>` : ''}
            </div>`;
        return `
            <div class="${cardShell}">
                ${chartHeader}
                <div class="chart-canvas flex-1 p-2 ${this.useGrid ? '' : `min-h-[${this.options.minChartHeight}px]`}" id="${chartId}"></div>
            </div>`;
    }

    /**
     * Create chart wrapper with controls
     * 
     * @private
     */
    _createChartWrapper(chartId, config) {
        const wrapper = document.createElement('div');
        wrapper.id = `wrapper-${chartId}`;
        wrapper.className = this._getChartWrapperClasses(config.size);
        wrapper.innerHTML = this._buildCardHTML(chartId, config);
        return wrapper;
    }

    /**
     * Get chart wrapper CSS classes based on size
     * 
     * @private
     */
    _getChartWrapperClasses(size = 'medium') {
        const baseClasses = 'chart-wrapper';
        
        switch (size) {
            case 'small':
                return `${baseClasses} col-span-1`;
            case 'large':
                return `${baseClasses} col-span-1 md:col-span-2`;
            case 'full':
                return `${baseClasses} col-span-full`;
            case 'medium':
            default:
                return `${baseClasses} col-span-1`;
        }
    }

    /**
     * Remove a chart from the dashboard
     * 
     * @param {string} chartId - Chart ID to remove
     */
    removeChart(chartId) {
        const chartIndex = this.charts.findIndex(c => c.id === chartId);

        if (chartIndex === -1) {
            console.warn(`Chart not found: ${chartId}`);
            return;
        }

        // Clear Plotly chart (chart widgets only — others have no canvas)
        const removed = this.charts[chartIndex];
        if ((removed.config.widget_type || 'chart') === 'chart') {
            window.chartRenderer.clearChart(chartId);
        }

        // Remove DOM element
        const wrapper = document.getElementById(`wrapper-${chartId}`);
        if (wrapper) {
            if (this.grid) this.grid.removeWidget(wrapper);
            else wrapper.remove();
        }

        // Remove from charts array
        this.charts.splice(chartIndex, 1);

        // Notify dashboard page to sync pendingCharts and update UI
        if (typeof onChartRemoved === 'function') {
            onChartRemoved(chartId);
        }
    }

    /**
     * Update chart at specific position
     * 
     * @param {string} chartId - Chart ID
     * @param {Object} updates - Chart updates
     */
    updateChart(chartId, updates) {
        const chart = this.charts.find(c => c.id === chartId);
        
        if (!chart) {
            console.warn(`Chart not found: ${chartId}`);
            return;
        }

        // Update title
        if (updates.title) {
            const header = document.querySelector(`#wrapper-${chartId} .chart-header h3`);
            if (header) {
                header.textContent = updates.title;
            }
            chart.config.title = updates.title;
        }

        // Update chart data/layout
        if (updates.plotlySpec) {
            window.chartRenderer.updateChart(chartId, updates.plotlySpec);
            chart.config.plotlySpec = updates.plotlySpec;
        }
    }

    /**
     * Change dashboard layout mode
     * 
     * @param {string} layoutMode - Layout mode (grid, 1-col, 2-col, 3-col)
     */
    setLayout(layoutMode) {
        this.layout = layoutMode;
        if (!this.useGrid) {
            // Preset column layouts only apply in legacy CSS-grid mode;
            // gridstack positions are explicit per widget.
            this.container.className = this._getLayoutClasses();
        }
        // Trigger resize on all charts
        this.resizeAllCharts();
    }

    /**
     * Toggle fullscreen mode for a chart
     * 
     * @param {string} chartId - Chart ID
     */
    toggleFullscreen(chartId) {
        const wrapper = document.getElementById(`wrapper-${chartId}`);
        
        if (!wrapper) return;

        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            wrapper.requestFullscreen().then(() => {
                // Resize chart after entering fullscreen
                setTimeout(() => {
                    window.chartRenderer.resizeChart(chartId);
                }, 100);
            });
        }
    }

    /**
     * Resize all charts in the dashboard
     */
    resizeAllCharts() {
        this.charts.forEach(chart => {
            if ((chart.config.widget_type || 'chart') === 'chart') {
                window.chartRenderer.resizeChart(chart.id);
            }
        });
    }

    /**
     * Clear all charts from dashboard
     */
    clearDashboard() {
        this.charts.forEach(chart => {
            if ((chart.config.widget_type || 'chart') === 'chart') {
                window.chartRenderer.clearChart(chart.id);
            }
        });
        this.charts = [];
        if (this.grid) this.grid.removeAll();
        else this.container.innerHTML = '';
        this.chartIdCounter = 0;
    }

    /**
     * Get dashboard configuration for saving
     * 
     * @returns {Object} Dashboard configuration
     */
    getDashboardConfig() {
        return {
            layout: this.layout,
            charts: this.charts.map(chart => ({
                id: chart.id,
                config: chart.config
            }))
        };
    }

    /**
     * Load dashboard from configuration
     * 
     * @param {Object} config - Dashboard configuration
     */
    async loadDashboardConfig(config) {
        // Clear existing
        this.clearDashboard();

        // Set layout
        if (config.layout) {
            this.setLayout(config.layout);
        }

        // Add charts
        if (config.charts && Array.isArray(config.charts)) {
            for (const chartConfig of config.charts) {
                await this.addChart(chartConfig.config);
            }
        }
    }

    /**
     * Export dashboard as image
     * 
     * @returns {Promise<string>} Data URL of dashboard screenshot
     */
    async exportDashboard() {
        // This is a placeholder - full implementation would use html2canvas or similar
        console.warn('Dashboard export not yet implemented');
        return null;
    }

    /**
     * Get chart count
     */
    getChartCount() {
        return this.charts.length;
    }

    /**
     * Get chart by ID
     */
    getChart(chartId) {
        return this.charts.find(c => c.id === chartId);
    }

    /**
     * Check if dashboard is empty
     */
    isEmpty() {
        return this.charts.length === 0;
    }

    /**
     * Display empty state
     */
    showEmptyState() {
        this.container.innerHTML = `
            <div class="empty-state col-span-full flex flex-col items-center justify-center py-16 px-4">
                <svg class="w-24 h-24 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                </svg>
                <h3 class="text-xl font-semibold text-gray-600 mb-2">No Charts Yet</h3>
                <p class="text-gray-500 text-center max-w-md">
                    Add charts from the Query Builder to create your dashboard
                </p>
                <a href="query.html" class="btn-primary mt-6">
                    Go to Query Builder
                </a>
            </div>
        `;
    }
}

/**
 * Apply dashboard-level design settings as CSS (canvas background, card
 * background/radius/shadow/border, title banner). Shared by the designer
 * page and the public share view. Chart palettes are applied at render
 * time via layout options — this handles the pure-CSS part.
 */
function applyDashboardDesignCSS(design) {
    design = design || {};
    const root = document.documentElement;
    const body = document.body;

    // Canvas background
    if (design.canvasBg) {
        root.style.setProperty('--dz-canvas', design.canvasBg);
        body.classList.add('dz-canvas');
    } else {
        body.classList.remove('dz-canvas');
    }

    // Card styling
    const hasCardCustom = design.cardBg || design.cardRadius !== undefined;
    if (design.cardBg) root.style.setProperty('--dz-card-bg', design.cardBg);
    else root.style.removeProperty('--dz-card-bg');
    root.style.setProperty('--dz-radius', `${design.cardRadius !== undefined ? design.cardRadius : 12}px`);
    body.classList.toggle('dz-cards', !!hasCardCustom);
    body.classList.toggle('dz-noshadow', design.cardShadow === false);
    body.classList.toggle('dz-border', !!design.cardBorder);
}

/**
 * Compute a KPI value from a chart config's stored query result.
 * Shared by the dashboard designer and the public share view.
 */
function computeKpiFromChart(chartCfg, agg) {
    const data = chartCfg?.queryResult?.data || [];
    if (!data.length) return { value: '—', sub: 'no data' };

    if (agg === 'count') {
        return { value: data.length.toLocaleString(), sub: `rows · ${chartCfg.title || ''}` };
    }

    const keys = Object.keys(data[0]);
    const key = keys.includes('value') && typeof data[0].value === 'number'
        ? 'value'
        : keys.find(k => typeof data[0][k] === 'number');
    if (!key) return { value: '—', sub: 'no numeric column' };

    const values = data.map(r => r[key]).filter(v => typeof v === 'number' && isFinite(v));
    if (!values.length) return { value: '—', sub: 'no numeric values' };

    let v;
    if (agg === 'sum')  v = values.reduce((a, b) => a + b, 0);
    if (agg === 'avg')  v = values.reduce((a, b) => a + b, 0) / values.length;
    if (agg === 'max')  v = Math.max(...values);
    if (agg === 'min')  v = Math.min(...values);
    if (agg === 'last') v = values[values.length - 1];

    const formatted = Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'B'
        : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + 'M'
        : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return { value: formatted, sub: `${agg} of ${key} · ${chartCfg.title || ''}`.slice(0, 60) };
}

// Create singleton instance
let dashboardLayout = null;

function initDashboardLayout(containerId, options) {
    dashboardLayout = new DashboardLayout(containerId, options);
    return dashboardLayout;
}

// Expose to global scope
if (typeof window !== 'undefined') {
    window.DashboardLayout = DashboardLayout;
    window.initDashboardLayout = initDashboardLayout;
    window.dashboardLayout = dashboardLayout;
    window.computeKpiFromChart = computeKpiFromChart;
    window.applyDashboardDesignCSS = applyDashboardDesignCSS;
}
