import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import createCache from '@emotion/cache';
import { CacheProvider } from '@emotion/react';
import axios from 'axios';
import { getCsrfToken, fetchCsrfToken } from './csrf';

const nonceMeta = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content');
const nonce = nonceMeta && nonceMeta !== '__CSP_NONCE__' ? nonceMeta : undefined;

const cache = createCache({ key: 'css', nonce });

// Configure axios to include CSRF token in all requests
axios.interceptors.request.use(
    async (config) => {
        // Only add CSRF token for state-changing requests
        if (['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase())) {
            let token = getCsrfToken();
            if (!token) {
                // Fetch token if not available
                token = await fetchCsrfToken();
            }
            if (token) {
                // Add to header (preferred)
                config.headers['X-CSRF-Token'] = token;
                // Also add to JSON body if it's a JSON request
                if (config.data && typeof config.data === 'object' && !(config.data instanceof FormData)) {
                    config.data.csrf_token = token;
                    config.data.CSRFToken = token;
                    config.data.anticsrf = token;
                }
            }
        }
        // Include credentials for session cookies
        config.withCredentials = true;
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Handle CSRF token refresh on 403 errors
axios.interceptors.response.use(
    (response) => response,
    async (error) => {
        if (error.response?.status === 403 && error.response?.data?.error?.includes('CSRF')) {
            // CSRF token might be expired, fetch a new one
            const token = await fetchCsrfToken();
            if (token && error.config) {
                // Retry the request with new token
                error.config.headers['X-CSRF-Token'] = token;
                if (error.config.data && typeof error.config.data === 'object') {
                    error.config.data.csrf_token = token;
                    error.config.data.CSRFToken = token;
                    error.config.data.anticsrf = token;
                }
                return axios.request(error.config);
            }
        }
        return Promise.reject(error);
    }
);

// Pre-fetch CSRF token on page load
fetchCsrfToken().catch(err => {
    console.warn('Failed to pre-fetch CSRF token:', err);
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <CacheProvider value={cache}>
    <App />
  </CacheProvider>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();

