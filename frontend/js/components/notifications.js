/**
 * Notification System
 * Displays toast notifications to users
 */

const Notifications = {
    /**
     * Show a notification
     * @param {string} message - Notification message
     * @param {string} type - Type: 'success', 'error', 'warning', 'info'
     * @param {number} duration - Display duration in ms (default: 5000)
     */
    show(message, type = 'info', duration = 5000) {
        const container = this.getOrCreateContainer();
        const notification = this.createNotification(message, type);
        
        container.appendChild(notification);
        
        // Trigger animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        // Auto-remove after duration
        setTimeout(() => {
            this.remove(notification);
        }, duration);
    },

    /**
     * Show success notification
     * @param {string} message - Success message
     */
    success(message) {
        this.show(message, 'success');
    },

    /**
     * Show error notification
     * @param {string} message - Error message
     */
    error(message) {
        this.show(message, 'error');
    },

    /**
     * Show warning notification
     * @param {string} message - Warning message
     */
    warning(message) {
        this.show(message, 'warning');
    },

    /**
     * Show info notification
     * @param {string} message - Info message
     */
    info(message) {
        this.show(message, 'info');
    },

    /**
     * Get or create notification container
     * @returns {HTMLElement} Container element
     */
    getOrCreateContainer() {
        let container = document.getElementById('notification-container');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.className = 'fixed top-4 right-4 space-y-2';
            container.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:99999;display:flex;flex-direction:column;gap:0.5rem;';
            document.body.appendChild(container);
        }
        
        return container;
    },

    /**
     * Create notification element
     * @param {string} message - Notification message
     * @param {string} type - Notification type
     * @returns {HTMLElement} Notification element
     */
    createNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `notification ${type} transform transition-all duration-300 translate-x-full opacity-0`;
        
        const colors = {
            success: 'bg-green-50 border-green-500 text-green-900',
            error: 'bg-red-50 border-red-500 text-red-900',
            warning: 'bg-yellow-50 border-yellow-500 text-yellow-900',
            info: 'bg-blue-50 border-blue-500 text-blue-900'
        };
        
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        
        notification.innerHTML = `
            <div class="flex items-center p-4 border-l-4 ${colors[type]} rounded shadow-lg max-w-md">
                <span class="text-2xl mr-3">${icons[type]}</span>
                <p class="flex-1">${message}</p>
                <button class="ml-4 text-gray-400 hover:text-gray-600" onclick="Notifications.remove(this.parentElement.parentElement)">
                    ✕
                </button>
            </div>
        `;
        
        // Add show class for animation
        notification.classList.add('show');
        
        return notification;
    },

    /**
     * Remove notification
     * @param {HTMLElement} notification - Notification element to remove
     */
    remove(notification) {
        notification.classList.remove('show');
        notification.classList.add('translate-x-full', 'opacity-0');
        
        setTimeout(() => {
            notification.remove();
        }, 300);
    }
};

// Add CSS for notifications
const style = document.createElement('style');
style.textContent = `
    .notification.show {
        transform: translateX(0) !important;
        opacity: 1 !important;
    }
`;
document.head.appendChild(style);
