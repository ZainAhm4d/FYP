/**
 * Chart Renderer Module
 * 
 * Reusable Plotly.js chart rendering system for the BI Dashboard Generator.
 * Supports all chart types: line, bar, pie, scatter, histogram.
 * 
 * Features:
 * - Render Plotly charts from JSON specifications
 * - Responsive resizing
 * - Interactive controls (hover, zoom, pan)
 * - Consistent styling
 * - Error handling
 * 
 * Usage:
 *   import { ChartRenderer } from './chart-renderer.js';
 *   const renderer = new ChartRenderer();
 *   renderer.renderChart(containerId, plotlySpec, options);
 */

class ChartRenderer {
    constructor() {
        this.charts = new Map(); // Store chart references by container ID
        this.defaultConfig = {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false,
            toImageButtonOptions: {
                format: 'png',
                filename: 'chart',
                height: 1080,
                width: 1920,
                scale: 2
            }
        };
    }

    /**
     * Render a Plotly chart in the specified container
     * 
     * @param {string} containerId - DOM element ID or element reference
     * @param {Object} plotlySpec - Plotly specification {data: [], layout: {}}
     * @param {Object} options - Additional options
     * @returns {Promise} Resolves when chart is rendered
     */
    async renderChart(containerId, plotlySpec, options = {}) {
        try {
            // Get container element
            const container = typeof containerId === 'string' 
                ? document.getElementById(containerId)
                : containerId;

            if (!container) {
                throw new Error(`Container not found: ${containerId}`);
            }

            // Validate plotlySpec
            if (!plotlySpec || !plotlySpec.data || !plotlySpec.layout) {
                throw new Error('Invalid Plotly specification. Must include data and layout.');
            }

            // Clear existing chart
            this.clearChart(containerId);

            // Merge config
            const config = {
                ...this.defaultConfig,
                ...options.config
            };

            // Apply responsive layout settings
            const layout = {
                ...plotlySpec.layout,
                autosize: true,
                ...options.layout
            };

            // Render chart
            await Plotly.newPlot(container, plotlySpec.data, layout, config);

            // Store chart reference
            this.charts.set(containerId, {
                container,
                spec: plotlySpec,
                config,
                timestamp: Date.now()
            });

            // Add resize listener
            this._attachResizeListener(container);

            return { success: true, containerId };

        } catch (error) {
            console.error('Chart rendering error:', error);
            this._displayError(containerId, error.message);
            return { success: false, error: error.message };
        }
    }

    /**
     * Update an existing chart with new data
     * 
     * @param {string} containerId - Container ID
     * @param {Object} updates - Data or layout updates
     */
    updateChart(containerId, updates = {}) {
        try {
            const container = typeof containerId === 'string'
                ? document.getElementById(containerId)
                : containerId;

            if (!container) {
                throw new Error(`Container not found: ${containerId}`);
            }

            // Update data
            if (updates.data) {
                Plotly.restyle(container, updates.data);
            }

            // Update layout
            if (updates.layout) {
                Plotly.relayout(container, updates.layout);
            }

            // Update stored spec
            const chartRef = this.charts.get(containerId);
            if (chartRef) {
                chartRef.spec = {
                    data: updates.data || chartRef.spec.data,
                    layout: updates.layout || chartRef.spec.layout
                };
            }

            return { success: true };

        } catch (error) {
            console.error('Chart update error:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Resize chart to fit container
     * 
     * @param {string} containerId - Container ID
     */
    resizeChart(containerId) {
        try {
            const container = typeof containerId === 'string'
                ? document.getElementById(containerId)
                : containerId;

            if (!container) return;

            // Pie/donut charts: Plotly.Plots.resize() doesn't reliably
            // recompute label/leader-line geometry when the container's
            // aspect ratio changes (e.g. a dashboard grid card settling to
            // its real size right after the initial render fires the
            // ResizeObserver below) — it can leave stale connector-line
            // artifacts through the slices. Plotly.react does a full,
            // correct recompute instead. Cartesian charts don't have this
            // issue, so they keep the cheaper resize() path.
            const chartRef = this.charts.get(containerId);
            const hasPie = chartRef?.spec?.data?.some(t => t.type === 'pie');
            if (hasPie) {
                Plotly.react(container, chartRef.spec.data, chartRef.spec.layout, chartRef.config);
            } else {
                Plotly.Plots.resize(container);
            }
        } catch (error) {
            console.error('Chart resize error:', error);
        }
    }

    /**
     * Clear/destroy a chart
     * 
     * @param {string} containerId - Container ID
     */
    clearChart(containerId) {
        try {
            const container = typeof containerId === 'string'
                ? document.getElementById(containerId)
                : containerId;

            if (container) {
                Plotly.purge(container);
            }

            this.charts.delete(containerId);
        } catch (error) {
            console.error('Chart clear error:', error);
        }
    }

    /**
     * Get chart specification for a rendered chart
     * 
     * @param {string} containerId - Container ID
     * @returns {Object|null} Plotly spec or null
     */
    getChartSpec(containerId) {
        const chartRef = this.charts.get(containerId);
        return chartRef ? chartRef.spec : null;
    }

    /**
     * Export chart as image data URL
     * 
     * @param {string} containerId - Container ID
     * @param {Object} options - Export options {format, width, height}
     * @returns {Promise<string>} Data URL
     */
    async exportChart(containerId, options = {}) {
        try {
            const container = typeof containerId === 'string'
                ? document.getElementById(containerId)
                : containerId;

            if (!container) {
                throw new Error(`Container not found: ${containerId}`);
            }

            const format = options.format || 'png';
            const width = options.width || 1920;
            const height = options.height || 1080;

            const imageData = await Plotly.toImage(container, {
                format,
                width,
                height,
                scale: 2
            });

            return imageData;

        } catch (error) {
            console.error('Chart export error:', error);
            throw error;
        }
    }

    /**
     * Render multiple charts in batch
     * 
     * @param {Array} chartConfigs - Array of {containerId, plotlySpec, options}
     * @returns {Promise<Array>} Results for each chart
     */
    async renderMultipleCharts(chartConfigs) {
        const results = [];

        for (const config of chartConfigs) {
            const result = await this.renderChart(
                config.containerId,
                config.plotlySpec,
                config.options
            );
            results.push(result);
        }

        return results;
    }

    /**
     * Create a simple chart from data and type
     * 
     * @param {string} containerId - Container ID
     * @param {Array} data - Chart data
     * @param {string} chartType - Chart type (line, bar, pie, scatter)
     * @param {Object} options - Chart options
     */
    async createSimpleChart(containerId, data, chartType, options = {}) {
        const plotlySpec = this._createSimpleSpec(data, chartType, options);
        return this.renderChart(containerId, plotlySpec, options);
    }

    /**
     * Display error message in container
     * 
     * @private
     */
    _displayError(containerId, message) {
        const container = typeof containerId === 'string'
            ? document.getElementById(containerId)
            : containerId;

        if (container) {
            container.innerHTML = `
                <div class="flex items-center justify-center h-full min-h-[300px] bg-red-50 border-2 border-red-200 rounded-lg">
                    <div class="text-center p-6">
                        <svg class="w-16 h-16 text-red-500 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <h3 class="text-lg font-semibold text-red-800 mb-2">Chart Rendering Error</h3>
                        <p class="text-red-600">${message}</p>
                    </div>
                </div>
            `;
        }
    }

    /**
     * Attach resize listener to container
     * 
     * @private
     */
    _attachResizeListener(container) {
        // Use ResizeObserver if available
        if (typeof ResizeObserver !== 'undefined') {
            const observer = new ResizeObserver(() => {
                this.resizeChart(container);
            });
            observer.observe(container);
        } else {
            // Fallback to window resize
            window.addEventListener('resize', () => {
                this.resizeChart(container);
            });
        }
    }

    /**
     * Create simple Plotly spec from basic data
     * 
     * @private
     */
    _createSimpleSpec(data, chartType, options = {}) {
        const title = options.title || 'Chart';
        const xLabel = options.xLabel || 'X';
        const yLabel = options.yLabel || 'Y';

        let trace;

        switch (chartType) {
            case 'line':
                trace = {
                    type: 'scatter',
                    mode: 'lines+markers',
                    x: data.x,
                    y: data.y,
                    name: options.name || 'Series',
                    line: { color: options.color || '#3B82F6', width: 3 },
                    marker: { size: 6 }
                };
                break;

            case 'bar':
                trace = {
                    type: 'bar',
                    x: data.x,
                    y: data.y,
                    name: options.name || 'Series',
                    marker: { color: options.color || '#6366F1' }
                };
                break;

            case 'pie':
                trace = {
                    type: 'pie',
                    labels: data.labels,
                    values: data.values,
                    textposition: 'inside',
                    textinfo: 'label+percent'
                };
                break;

            case 'scatter':
                trace = {
                    type: 'scatter',
                    mode: 'markers',
                    x: data.x,
                    y: data.y,
                    marker: {
                        size: 8,
                        color: options.color || '#10B981',
                        opacity: 0.7
                    }
                };
                break;

            default:
                throw new Error(`Unsupported chart type: ${chartType}`);
        }

        return {
            data: [trace],
            layout: {
                title: { text: title, font: { size: 20 } },
                xaxis: { title: xLabel },
                yaxis: { title: yLabel },
                plot_bgcolor: '#FFFFFF',
                paper_bgcolor: '#FFFFFF',
                font: { family: 'Arial, sans-serif' }
            }
        };
    }

    /**
     * Clear all charts
     */
    clearAllCharts() {
        for (const containerId of this.charts.keys()) {
            this.clearChart(containerId);
        }
    }

    /**
     * Get count of rendered charts
     */
    getChartCount() {
        return this.charts.size;
    }

    /**
     * Get all chart container IDs
     */
    getChartIds() {
        return Array.from(this.charts.keys());
    }
}

// Create singleton instance
const chartRenderer = new ChartRenderer();

// Expose to global scope
if (typeof window !== 'undefined') {
    window.ChartRenderer = ChartRenderer;
    window.chartRenderer = chartRenderer;
}
