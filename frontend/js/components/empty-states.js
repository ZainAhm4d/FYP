/**
 * Empty State Components
 * Reusable empty state generators for different scenarios
 */

const EmptyStates = {
    /**
     * SVG Icons for empty states
     */
    icons: {
        dataset: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
        </svg>`,
        
        dashboard: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 13a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1v-7z"></path>
        </svg>`,
        
        chart: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
        </svg>`,
        
        search: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
        </svg>`,
        
        error: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>`,
        
        upload: `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
        </svg>`
    },

    /**
     * Generate empty state HTML
     * @param {object} options - Configuration options
     * @returns {string} HTML string
     */
    generate(options = {}) {
        const {
            type = 'datasets',
            title = 'No Data Available',
            description = 'There is nothing to display here yet.',
            actionText = null,
            actionLink = null,
            size = 'normal', // normal, compact, inline
            animated = true
        } = options;

        const icon = this.icons[type] || this.icons.dataset;
        const sizeClass = size !== 'normal' ? `empty-state-${size}` : '';
        const animatedClass = animated ? 'empty-state-icon-animated' : '';
        const typeClass = `empty-state-${type}`;

        let html = `
            <div class="empty-state ${typeClass} ${sizeClass}">
                <div class="empty-state-icon ${animatedClass}">
                    ${icon}
                </div>
                <h3 class="empty-state-title">${title}</h3>
                <p class="empty-state-description">${description}</p>
        `;

        if (actionText && actionLink) {
            html += `
                <div class="empty-state-action">
                    <a href="${actionLink}" class="btn btn-primary">
                        ${actionText}
                    </a>
                </div>
            `;
        }

        html += '</div>';
        return html;
    },

    /**
     * No datasets uploaded
     */
    noDatasets() {
        return this.generate({
            type: 'dataset',
            title: 'No Datasets Uploaded Yet',
            description: 'Upload your first dataset to start analyzing your business data and creating insights.',
            actionText: 'Upload Dataset',
            actionLink: 'upload.html'
        });
    },

    /**
     * No saved dashboards
     */
    noDashboards() {
        return this.generate({
            type: 'dashboard',
            title: 'No Saved Dashboards Yet',
            description: 'Create your first dashboard from the Query Builder to visualize your data.',
            actionText: 'Go to Query Builder',
            actionLink: 'query.html'
        });
    },

    /**
     * No charts in dashboard
     */
    noCharts() {
        return this.generate({
            type: 'chart',
            title: 'No Charts Added',
            description: 'Add charts from the Query Builder to build your dashboard.',
            actionText: 'Create Chart',
            actionLink: 'query.html'
        });
    },

    /**
     * No search results
     */
    noResults(searchTerm = '') {
        const description = searchTerm 
            ? `No results found for "${searchTerm}". Try adjusting your search.`
            : 'No results found. Try adjusting your filters.';
            
        return this.generate({
            type: 'search',
            title: 'No Results Found',
            description: description
        });
    },

    /**
     * Error state
     */
    error(message = 'Something went wrong') {
        return this.generate({
            type: 'error',
            title: 'Oops! Something Went Wrong',
            description: message,
            animated: false
        });
    },

    /**
     * Show empty state in container
     * @param {HTMLElement|string} container - Container element or selector
     * @param {string} stateType - Type of empty state (noDatasets, noDashboards, etc.)
     * @param {object} options - Additional options
     */
    show(container, stateType, options = {}) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Empty state container not found:', container);
            return;
        }

        let html = '';
        
        // Predefined states
        if (typeof this[stateType] === 'function') {
            html = this[stateType](options);
        } 
        // Custom state
        else {
            html = this.generate(options);
        }

        element.innerHTML = html;
    },

    /**
     * Hide empty state
     * @param {HTMLElement|string} container - Container element or selector
     */
    hide(container) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Empty state container not found:', container);
            return;
        }

        const emptyState = element.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }
    },

    /**
     * Replace empty state with content
     * @param {HTMLElement|string} container - Container element or selector
     * @param {string|HTMLElement} content - Content to show
     */
    replace(container, content) {
        const element = typeof container === 'string' 
            ? document.querySelector(container)
            : container;
            
        if (!element) {
            console.error('Empty state container not found:', container);
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
window.EmptyStates = EmptyStates;
