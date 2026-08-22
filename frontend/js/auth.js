/**
 * Authentication Utility
 * Manages user authentication state and operations
 */

const Auth = {
    /**
     * Check if user is authenticated
     * @returns {boolean} True if user has valid token
     */
    isAuthenticated() {
        return Storage.has(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
    },

    /**
     * Get current user data from storage
     * @returns {Object|null} User data or null
     */
    getCurrentUser() {
        return Storage.get(CONFIG.STORAGE_KEYS.USER_DATA);
    },

    /**
     * Save authentication token
     * @param {string} token - JWT access token
     */
    setToken(token) {
        Storage.set(CONFIG.STORAGE_KEYS.ACCESS_TOKEN, token);
    },

    /**
     * Get authentication token
     * @returns {string|null} JWT token or null
     */
    getToken() {
        return Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
    },

    /**
     * Save user data
     * @param {Object} userData - User information
     */
    setUser(userData) {
        Storage.set(CONFIG.STORAGE_KEYS.USER_DATA, userData);
    },

    /**
     * Register a new user
     * @param {string} email - User email
     * @param {string} password - User password
     * @param {string} fullName - User full name
     * @returns {Promise<Object>} User data
     */
    async register(email, password, fullName) {
        try {
            const response = await API.post(CONFIG.ENDPOINTS.AUTH.REGISTER, {
                email,
                password,
                full_name: fullName
            });

            return response;
        } catch (error) {
            throw error;
        }
    },

    /**
     * Login user
     * @param {string} email - User email
     * @param {string} password - User password
     * @returns {Promise<Object>} Token and user data
     */
    async login(email, password) {
        try {
            // Login with form data (OAuth2 expects username field)
            const tokenResponse = await API.postForm(CONFIG.ENDPOINTS.AUTH.LOGIN, {
                username: email,
                password: password
            });

            // Save token
            this.setToken(tokenResponse.access_token);

            // Fetch user data
            const userData = await this.fetchUserData();
            this.setUser(userData);

            return { token: tokenResponse, user: userData };
        } catch (error) {
            throw error;
        }
    },

    /**
     * Fetch current user data from API
     * @returns {Promise<Object>} User data
     */
    async fetchUserData() {
        try {
            const response = await API.get(CONFIG.ENDPOINTS.AUTH.ME, true);
            return response;
        } catch (error) {
            throw error;
        }
    },

    /**
     * Logout user
     */
    logout() {
        Storage.remove(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
        Storage.remove(CONFIG.STORAGE_KEYS.USER_DATA);
    },

    /**
     * Validate password strength
     * @param {string} password - Password to validate
     * @returns {Object} Validation result { valid: boolean, message: string }
     */
    validatePassword(password) {
        if (password.length < 8) {
            return { valid: false, message: 'Password must be at least 8 characters long' };
        }

        if (!/[A-Z]/.test(password)) {
            return { valid: false, message: 'Password must contain at least one uppercase letter' };
        }

        if (!/[a-z]/.test(password)) {
            return { valid: false, message: 'Password must contain at least one lowercase letter' };
        }

        if (!/\d/.test(password)) {
            return { valid: false, message: 'Password must contain at least one number' };
        }

        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
            return { valid: false, message: 'Password must contain at least one special character' };
        }

        return { valid: true, message: 'Password is strong' };
    },

    /**
     * Validate email format
     * @param {string} email - Email to validate
     * @returns {boolean} True if email is valid
     */
    validateEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },

    /**
     * Redirect to login page if not authenticated
     */
    requireAuth() {
        if (!this.isAuthenticated()) {
            // login.html is no longer the app's real entry point — index.html's
            // login modal is. Send the visitor there with ?login=1 to auto-open
            // it, plus ?next=<this page> so they land back where they were
            // headed instead of always dumping them on the dashboard.
            const next = encodeURIComponent(window.location.pathname.split('/').pop() + window.location.search);
            window.location.href = `index.html?login=1&next=${next}`;
        }
    }
};
