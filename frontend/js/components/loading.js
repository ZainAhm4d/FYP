/**
 * Loading Component
 * Provides loading indicators and skeleton screens
 */

const Loading = {
    /**
     * Show full-screen loading overlay
     * @param {string} message - Optional loading message
     */
    show(message = 'Loading...') {
        // Remove existing overlay if present
        this.hide();
        
        const overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="flex flex-col items-center justify-center">
                <div class="spinner mb-4"></div>
                <p class="text-gray-700 text-lg font-medium">${message}</p>
            </div>
        `;
        
        document.body.appendChild(overlay);
    },
    
    /**
     * Hide loading overlay
     */
    hide() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    },
    
    /**
     * Show inline spinner
     * @param {string} containerId - Container element ID
     * @param {string} message - Optional message
     */
    showInline(containerId, message = 'Loading...') {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center py-12">
                <div class="spinner mb-4"></div>
                <p class="text-gray-600">${message}</p>
            </div>
        `;
    },
    
    /**
     * Show skeleton loader for table
     * @param {string} containerId - Container element ID
     * @param {number} rows - Number of skeleton rows
     */
    showTableSkeleton(containerId, rows = 5) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const skeletonRows = Array(rows).fill(0).map(() => `
            <tr class="animate-pulse">
                <td class="px-6 py-4">
                    <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                </td>
                <td class="px-6 py-4">
                    <div class="h-4 bg-gray-200 rounded w-1/2"></div>
                </td>
                <td class="px-6 py-4">
                    <div class="h-4 bg-gray-200 rounded w-1/4"></div>
                </td>
                <td class="px-6 py-4">
                    <div class="h-4 bg-gray-200 rounded w-1/3"></div>
                </td>
            </tr>
        `).join('');
        
        container.innerHTML = `
            <table class="w-full">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    ${skeletonRows}
                </tbody>
            </table>
        `;
    },
    
    /**
     * Show skeleton loader for cards
     * @param {string} containerId - Container element ID
     * @param {number} cards - Number of skeleton cards
     */
    showCardSkeleton(containerId, cards = 3) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const skeletonCards = Array(cards).fill(0).map(() => `
            <div class="card animate-pulse">
                <div class="h-6 bg-gray-200 rounded w-3/4 mb-4"></div>
                <div class="h-4 bg-gray-200 rounded w-full mb-2"></div>
                <div class="h-4 bg-gray-200 rounded w-5/6 mb-4"></div>
                <div class="h-10 bg-gray-200 rounded w-1/3"></div>
            </div>
        `).join('');
        
        container.innerHTML = `
            <div class="grid md:grid-cols-3 gap-6">
                ${skeletonCards}
            </div>
        `;
    },
    
    /**
     * Show empty state
     * @param {string} containerId - Container element ID
     * @param {Object} options - Empty state options
     */
    showEmpty(containerId, options = {}) {
        const {
            icon = '',
            title = 'No data available',
            message = 'Get started by adding some data.',
            actionText = null,
            actionLink = null
        } = options;
        
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const actionButton = actionText && actionLink 
            ? `<a href="${actionLink}" class="btn btn-primary px-6 py-3 mt-6 inline-block">${actionText}</a>`
            : '';
        
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center py-16 text-center">
                <div class="text-6xl mb-4">${icon}</div>
                <h3 class="text-2xl font-bold text-gray-800 mb-2">${title}</h3>
                <p class="text-gray-600 mb-4 max-w-md">${message}</p>
                ${actionButton}
            </div>
        `;
    },
    
    /**
     * Show progress bar
     * @param {number} percentage - Progress percentage (0-100)
     * @param {string} containerId - Container element ID
     */
    showProgress(percentage, containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const clampedPercentage = Math.max(0, Math.min(100, percentage));
        
        container.innerHTML = `
            <div class="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                <div class="bg-blue-600 h-4 rounded-full transition-all duration-300 flex items-center justify-center text-xs text-white font-semibold" 
                     style="width: ${clampedPercentage}%">
                    ${clampedPercentage}%
                </div>
            </div>
        `;
    }
};

// Add required CSS animations
const loadingStyles = document.createElement('style');
loadingStyles.textContent = `
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #0d9488;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        animation: spin 1s linear infinite;
    }
    
    @keyframes pulse {
        0%, 100% {
            opacity: 1;
        }
        50% {
            opacity: 0.5;
        }
    }
    
    .animate-pulse {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
`;

if (!document.getElementById('loading-styles')) {
    loadingStyles.id = 'loading-styles';
    document.head.appendChild(loadingStyles);
}
