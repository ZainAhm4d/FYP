/**
 * API Utility
 * Handles all HTTP requests to the backend API
 */

const API = {
    /**
     * Get full API URL
     * @param {string} endpoint - API endpoint path
     * @returns {string} Full URL
     */
    getUrl(endpoint) {
        return `${CONFIG.API_BASE_URL}${CONFIG.API_V1}${endpoint}`;
    },

    /**
     * Get authorization headers with JWT token
     * @returns {Object} Headers object
     */
    getAuthHeaders() {
        const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        return headers;
    },

    /**
     * Make a GET request
     * @param {string} endpoint - API endpoint
     * @param {boolean} auth - Whether to include auth headers
     * @returns {Promise} Response data
     */
    async get(endpoint, auth = false) {
        try {
            const headers = auth ? this.getAuthHeaders() : { 'Content-Type': 'application/json' };
            
            const response = await fetch(this.getUrl(endpoint), {
                method: 'GET',
                headers
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Make a POST request
     * @param {string} endpoint - API endpoint
     * @param {Object} data - Request body data
     * @param {boolean} auth - Whether to include auth headers
     * @returns {Promise} Response data
     */
    async post(endpoint, data, auth = false) {
        try {
            const headers = auth ? this.getAuthHeaders() : { 'Content-Type': 'application/json' };
            
            const response = await fetch(this.getUrl(endpoint), {
                method: 'POST',
                headers,
                body: JSON.stringify(data)
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Make a POST request with form data (for OAuth2 login)
     * @param {string} endpoint - API endpoint
     * @param {Object} data - Form data
     * @returns {Promise} Response data
     */
    async postForm(endpoint, data) {
        try {
            const formData = new URLSearchParams();
            for (const key in data) {
                formData.append(key, data[key]);
            }
            
            const response = await fetch(this.getUrl(endpoint), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Upload a file with FormData.
     * @param {string} endpoint - API endpoint
     * @param {FormData} formData - FormData with file
     * @param {boolean} auth - Whether to include auth headers
     * @param {(percent: number) => void} [onProgress] - Called with 0-100 as
     *   the actual bytes upload (fetch() has no upload-progress event at
     *   all, so this uses XMLHttpRequest specifically to get real progress).
     * @returns {Promise} Response data
     */
    async uploadFile(endpoint, formData, auth = true, onProgress = null) {
        const headers = {};
        if (auth) {
            const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
            if (token) headers['Authorization'] = `Bearer ${token}`;
        }

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', this.getUrl(endpoint), true);
            Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
            // Don't set Content-Type — the browser sets it with the correct boundary.

            if (onProgress && xhr.upload) {
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
                });
            }

            xhr.onload = () => {
                const contentType = xhr.getResponseHeader('content-type') || '';
                let body = xhr.responseText;
                if (contentType.includes('application/json')) {
                    try { body = JSON.parse(xhr.responseText); } catch (_) { /* leave as text */ }
                }
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(body);
                    return;
                }
                let errorMessage = `HTTP Error: ${xhr.status}`;
                if (body && typeof body === 'object') {
                    if (typeof body.detail === 'string') errorMessage = body.detail;
                    else if (Array.isArray(body.detail)) errorMessage = body.detail.map(err => err.msg).join(', ');
                    else if (body.detail) errorMessage = JSON.stringify(body.detail);
                    else if (body.message) errorMessage = body.message;
                } else if (typeof body === 'string' && body) {
                    errorMessage = xhr.statusText || errorMessage;
                }
                reject(this.handleError(new Error(errorMessage)));
            };
            xhr.onerror = () => reject(this.handleError(new Error('Network error during upload')));
            xhr.send(formData);
        });
    },

    /**
     * Make a PUT request
     * @param {string} endpoint - API endpoint
     * @param {Object} data - Request body data
     * @param {boolean} auth - Whether to include auth headers
     * @returns {Promise} Response data
     */
    async put(endpoint, data, auth = true) {
        try {
            const headers = auth ? this.getAuthHeaders() : { 'Content-Type': 'application/json' };
            
            const response = await fetch(this.getUrl(endpoint), {
                method: 'PUT',
                headers,
                body: JSON.stringify(data)
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Make a PATCH request
     * @param {string} endpoint - API endpoint
     * @param {Object} data - Request body data
     * @param {boolean} auth - Whether to include auth headers
     * @returns {Promise} Response data
     */
    async patch(endpoint, data, auth = true) {
        try {
            const headers = auth ? this.getAuthHeaders() : { 'Content-Type': 'application/json' };

            const response = await fetch(this.getUrl(endpoint), {
                method: 'PATCH',
                headers,
                body: JSON.stringify(data)
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Make a DELETE request
     * @param {string} endpoint - API endpoint
     * @param {boolean} auth - Whether to include auth headers
     * @returns {Promise} Response data
     */
    async delete(endpoint, auth = true) {
        try {
            const headers = auth ? this.getAuthHeaders() : { 'Content-Type': 'application/json' };
            
            const response = await fetch(this.getUrl(endpoint), {
                method: 'DELETE',
                headers
            });

            return await this.handleResponse(response);
        } catch (error) {
            throw this.handleError(error);
        }
    },

    /**
     * Handle API response
     * @param {Response} response - Fetch API response
     * @returns {Promise} Parsed response data
     */
    async handleResponse(response) {
        if (response.ok) {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            return await response.text();
        }

        // Handle error responses
        let errorMessage = `HTTP Error: ${response.status}`;
        try {
            const errorData = await response.json();
            // Handle different error formats
            if (errorData.detail) {
                if (typeof errorData.detail === 'string') {
                    errorMessage = errorData.detail;
                } else if (Array.isArray(errorData.detail)) {
                    // FastAPI validation errors
                    errorMessage = errorData.detail.map(err => err.msg).join(', ');
                } else if (typeof errorData.detail === 'object') {
                    errorMessage = JSON.stringify(errorData.detail);
                }
            } else if (errorData.message) {
                errorMessage = errorData.message;
            }
        } catch (e) {
            // If error response is not JSON, use status text
            errorMessage = response.statusText || errorMessage;
        }

        throw new Error(errorMessage);
    },

    /**
     * Handle API errors
     * @param {Error} error - Error object
     * @returns {Error} Formatted error
     */
    handleError(error) {
        console.error('API Error:', error);
        return error;
    }
};
