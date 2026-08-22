/**
 * Skeleton Loader Component
 * Generates skeleton loading screens for different content types
 */

const SkeletonLoader = {
    /**
     * Generate skeleton for dataset list
     * @param {number} count - Number of skeleton rows
     * @returns {string} HTML string
     */
    datasetList(count = 3) {
        let html = '';
        for (let i = 0; i < count; i++) {
            html += `
                <div class="skeleton-dataset-row">
                    <div class="skeleton skeleton-avatar"></div>
                    <div class="skeleton-content">
                        <div class="skeleton skeleton-text" style="width: 40%;"></div>
                        <div class="skeleton skeleton-text skeleton-text-short"></div>
                    </div>
                    <div class="skeleton skeleton-button"></div>
                </div>
            `;
        }
        return html;
    },

    /**
     * Generate skeleton for dashboard cards grid
     * @param {number} count - Number of skeleton cards
     * @returns {string} HTML string
     */
    dashboardGrid(count = 6) {
        let html = '<div class="skeleton-grid">';
        for (let i = 0; i < count; i++) {
            html += `
                <div class="skeleton-dashboard-card">
                    <div class="skeleton skeleton-title"></div>
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text skeleton-text-short"></div>
                    <div class="skeleton-footer">
                        <div class="skeleton skeleton-button"></div>
                        <div class="skeleton skeleton-button"></div>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        return html;
    },

    /**
     * Generate skeleton for data table
     * @param {number} rows - Number of rows
     * @param {number} columns - Number of columns
     * @returns {string} HTML string
     */
    dataTable(rows = 5, columns = 5) {
        let html = '<div class="skeleton-table">';
        
        // Header
        html += '<div class="skeleton-table-header">';
        for (let i = 0; i < columns; i++) {
            html += '<div class="skeleton skeleton-text"></div>';
        }
        html += '</div>';
        
        // Rows
        for (let i = 0; i < rows; i++) {
            html += '<div class="skeleton-table-row">';
            for (let j = 0; j < columns; j++) {
                html += '<div class="skeleton skeleton-text"></div>';
            }
            html += '</div>';
        }
        
        html += '</div>';
        return html;
    },

    /**
     * Generate skeleton for query form
     * @returns {string} HTML string
     */
    queryForm() {
        return `
            <div class="skeleton-query-form">
                <div>
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-input"></div>
                </div>
                <div>
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-input"></div>
                </div>
                <div>
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-input"></div>
                </div>
                <div class="skeleton skeleton-button"></div>
            </div>
        `;
    },

    /**
     * Generate skeleton for chart
     * @returns {string} HTML string
     */
    chart() {
        return '<div class="skeleton skeleton-chart"></div>';
    },

    /**
     * Generate skeleton for multiple charts
     * @param {number} count - Number of charts
     * @returns {string} HTML string
     */
    chartGrid(count = 2) {
        let html = '<div class="grid md:grid-cols-2 gap-6">';
        for (let i = 0; i < count; i++) {
            html += `
                <div class="bg-white p-6 rounded-lg shadow">
                    <div class="skeleton skeleton-title"></div>
                    <div class="skeleton skeleton-chart"></div>
                </div>
            `;
        }
        html += '</div>';
        return html;
    },

    /**
     * Generate skeleton for single card
     * @returns {string} HTML string
     */
    card() {
        return `
            <div class="skeleton-dashboard-card">
                <div class="skeleton skeleton-title"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text skeleton-text-long"></div>
                <div class="skeleton skeleton-button"></div>
            </div>
        `;
    },

    /**
     * Show skeleton in container
     * @param {HTMLElement|string} container - Container element or selector
     * @param {string} type - Skeleton type (datasetList, dashboardGrid, etc.)
     * @param {*} options - Additional options (count, rows, columns, etc.)
     */
    show(container, type, options = {}) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Skeleton container not found:', container);
            return;
        }

        let html = '';
        switch (type) {
            case 'datasetList':
                html = this.datasetList(options.count || 3);
                break;
            case 'dashboardGrid':
                html = this.dashboardGrid(options.count || 6);
                break;
            case 'dataTable':
                html = this.dataTable(options.rows || 5, options.columns || 5);
                break;
            case 'queryForm':
                html = this.queryForm();
                break;
            case 'chart':
                html = this.chart();
                break;
            case 'chartGrid':
                html = this.chartGrid(options.count || 2);
                break;
            case 'card':
                html = this.card();
                break;
            default:
                console.warn('Unknown skeleton type:', type);
                return;
        }

        element.innerHTML = html;
    },

    /**
     * Hide skeleton and show content
     * @param {HTMLElement|string} container - Container element or selector
     */
    hide(container) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Skeleton container not found:', container);
            return;
        }

        element.innerHTML = '';
    },

    /**
     * Replace skeleton with content
     * @param {HTMLElement|string} container - Container element or selector
     * @param {string|HTMLElement} content - Content to show
     */
    replace(container, content) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Skeleton container not found:', container);
            return;
        }

        if (typeof content === 'string') {
            element.innerHTML = content;
        } else {
            element.innerHTML = '';
            element.appendChild(content);
        }
    }
};

// Make globally available
window.SkeletonLoader = SkeletonLoader;
