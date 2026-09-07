/**
 * Application Configuration
 * Centralized configuration for API endpoints and app settings
 */

// ── API base URL ────────────────────────────────────────────────────────────
// This is a static, no-build site (deployed as-is to Vercel), so there's no
// build step to inject an environment variable — instead, the URL is picked
// by hostname at page-load time. Local dev needs no changes; PRODUCTION_API_URL
// is the one line to edit after deploying the backend (Render/Railway).
const PRODUCTION_API_URL = 'https://your-backend.onrender.com'; // <-- EDIT AFTER DEPLOYING THE BACKEND

const _isLocalHost = ['localhost', '127.0.0.1', ''].includes(window.location.hostname);
const _API_BASE_URL = _isLocalHost ? 'http://localhost:8000' : PRODUCTION_API_URL;

const CONFIG = {
    // API Base URL — auto-detected (see PRODUCTION_API_URL above)
    API_BASE_URL: _API_BASE_URL,
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
