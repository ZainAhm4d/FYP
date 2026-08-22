/**
 * Application Configuration
 * Centralized configuration for API endpoints and app settings
 */

const CONFIG = {
    // API Base URL
    API_BASE_URL: 'http://localhost:8000',
    API_V1: '/api/v1',
    
    // Storage Keys
    STORAGE_KEYS: {
        ACCESS_TOKEN: 'access_token',
        USER_DATA: 'user_data'
    },
    
    // App Settings
    APP_NAME: 'BI Dashboard Generator',
    APP_VERSION: '1.0.0',
    
    // Endpoints
    ENDPOINTS: {
        AUTH: {
            REGISTER: '/auth/register',
            LOGIN: '/auth/login',
            ME: '/auth/users/me',
            TEST_TOKEN: '/auth/test-token'
        },
        DATASETS: {
            LIST: '/datasets',
            UPLOAD: '/datasets',
            GET: '/datasets/:id',
            PREVIEW: '/datasets/:id/preview',
            DELETE: '/datasets/:id'
        },
        QUERIES: {
            TEMPLATE: '/queries/template'
        },
        DASHBOARDS: {
            LIST: '/dashboards',
            CREATE: '/dashboards',
            GET: '/dashboards/:id',
            UPDATE: '/dashboards/:id',
            DELETE: '/dashboards/:id',
            EXPORT: '/dashboards/:id/export'
        }
    }
};

// Freeze configuration to prevent modifications
Object.freeze(CONFIG);
Object.freeze(CONFIG.STORAGE_KEYS);
Object.freeze(CONFIG.ENDPOINTS);
