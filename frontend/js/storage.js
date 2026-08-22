/**
 * Local Storage Utility
 * Manages data persistence in browser localStorage
 */

const Storage = {
    /**
     * Set item in localStorage
     * @param {string} key - Storage key
     * @param {*} value - Value to store (will be JSON stringified)
     */
    set(key, value) {
        try {
            const serialized = JSON.stringify(value);
            localStorage.setItem(key, serialized);
        } catch (error) {
            console.error('Error saving to localStorage:', error);
        }
    },

    /**
     * Get item from localStorage
     * @param {string} key - Storage key
     * @returns {*} Parsed value or null if not found
     */
    get(key) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : null;
        } catch (error) {
            console.error('Error reading from localStorage:', error);
            return null;
        }
    },

    /**
     * Remove item from localStorage
     * @param {string} key - Storage key
     */
    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.error('Error removing from localStorage:', error);
        }
    },

    /**
     * Clear all items from localStorage
     */
    clear() {
        try {
            localStorage.clear();
        } catch (error) {
            console.error('Error clearing localStorage:', error);
        }
    },

    /**
     * Check if key exists in localStorage
     * @param {string} key - Storage key
     * @returns {boolean} True if key exists
     */
    has(key) {
        return localStorage.getItem(key) !== null;
    },

    /**
     * Namespace a key to the logged-in user, so per-user draft/UI state
     * (e.g. staged dashboard charts) can't leak to a different account
     * that logs in later on the same browser.
     * @param {string} key - Base storage key
     * @returns {string} Key suffixed with the current user's id, or the
     *   base key unchanged if nobody is logged in yet.
     */
    userKey(key) {
        const user = Storage.get(CONFIG.STORAGE_KEYS.USER_DATA);
        return user?.id != null ? `${key}_u${user.id}` : key;
    }
};
