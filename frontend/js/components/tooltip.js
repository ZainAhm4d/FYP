/**
 * Tooltip System
 * Easy-to-use tooltip functionality for help text
 */

const Tooltip = {
    /**
     * Initialize tooltips on page load
     * Finds all elements with data-tooltip attribute
     */
    init() {
        // Find all elements with data-tooltip
        const elements = document.querySelectorAll('[data-tooltip]');
        
        elements.forEach(element => {
            this.attach(element);
        });
    },

    /**
     * Attach tooltip to an element
     * @param {HTMLElement} element - Element to attach tooltip to
     */
    attach(element) {
        const tooltipText = element.getAttribute('data-tooltip');
        const position = element.getAttribute('data-tooltip-position') || 'top';
        const variant = element.getAttribute('data-tooltip-variant') || '';
        const multiline = element.hasAttribute('data-tooltip-multiline');

        if (!tooltipText) return;

        // Create tooltip wrapper if element is not already wrapped
        if (!element.classList.contains('tooltip')) {
            const wrapper = document.createElement('span');
            wrapper.className = 'tooltip';
            element.parentNode.insertBefore(wrapper, element);
            wrapper.appendChild(element);
        }

        // Create tooltip text element
        const tooltip = document.createElement('span');
        tooltip.className = `tooltip-text tooltip-${position}`;
        
        if (variant) {
            tooltip.classList.add(`tooltip-${variant}`);
        }
        
        if (multiline) {
            tooltip.classList.add('tooltip-multiline');
        }
        
        tooltip.textContent = tooltipText;

        // Append to wrapper
        const wrapper = element.closest('.tooltip');
        wrapper.appendChild(tooltip);
    },

    /**
     * Create tooltip icon with text
     * @param {string} text - Tooltip text
     * @param {string} position - Position (top, bottom, left, right)
     * @param {string} variant - Variant (info, success, warning, error)
     * @returns {HTMLElement} Tooltip icon element
     */
    createIcon(text, position = 'top', variant = '') {
        const container = document.createElement('span');
        container.className = 'tooltip';

        const icon = document.createElement('span');
        icon.className = 'tooltip-icon';
        icon.textContent = '?';

        const tooltip = document.createElement('span');
        tooltip.className = `tooltip-text tooltip-${position}`;
        
        if (variant) {
            tooltip.classList.add(`tooltip-${variant}`);
        }
        
        tooltip.textContent = text;

        container.appendChild(icon);
        container.appendChild(tooltip);

        return container;
    },

    /**
     * Add tooltip programmatically
     * @param {string} selector - Element selector
     * @param {string} text - Tooltip text
     * @param {object} options - Options (position, variant, multiline)
     */
    add(selector, text, options = {}) {
        const element = document.querySelector(selector);
        if (!element) {
            console.error('Tooltip element not found:', selector);
            return;
        }

        element.setAttribute('data-tooltip', text);
        
        if (options.position) {
            element.setAttribute('data-tooltip-position', options.position);
        }
        
        if (options.variant) {
            element.setAttribute('data-tooltip-variant', options.variant);
        }
        
        if (options.multiline) {
            element.setAttribute('data-tooltip-multiline', '');
        }

        this.attach(element);
    },

    /**
     * Remove tooltip from element
     * @param {string} selector - Element selector
     */
    remove(selector) {
        const element = document.querySelector(selector);
        if (!element) return;

        element.removeAttribute('data-tooltip');
        element.removeAttribute('data-tooltip-position');
        element.removeAttribute('data-tooltip-variant');
        element.removeAttribute('data-tooltip-multiline');

        const wrapper = element.closest('.tooltip');
        if (wrapper) {
            const tooltipText = wrapper.querySelector('.tooltip-text');
            if (tooltipText) {
                tooltipText.remove();
            }
        }
    },

    /**
     * Update tooltip text
     * @param {string} selector - Element selector
     * @param {string} newText - New tooltip text
     */
    update(selector, newText) {
        const element = document.querySelector(selector);
        if (!element) return;

        element.setAttribute('data-tooltip', newText);

        const wrapper = element.closest('.tooltip');
        if (wrapper) {
            const tooltipText = wrapper.querySelector('.tooltip-text');
            if (tooltipText) {
                tooltipText.textContent = newText;
            }
        }
    },

    /**
     * Create help icon with tooltip
     * Useful for inline help text next to labels
     * @param {string} text - Help text
     * @param {string} position - Tooltip position
     * @returns {string} HTML string
     */
    helpIcon(text, position = 'top') {
        return `
            <span class="tooltip" style="display: inline-flex; align-items: center; vertical-align: middle;">
                <span class="tooltip-icon" style="cursor: help;">?</span>
                <span class="tooltip-text tooltip-${position}">${text}</span>
            </span>
        `;
    }
};

// Auto-initialize tooltips when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Tooltip.init());
} else {
    Tooltip.init();
}

// Make globally available
window.Tooltip = Tooltip;
