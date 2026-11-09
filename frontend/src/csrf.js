// CSRF token utility
let csrfToken = null;

// Get CSRF token from meta tag or fetch from API
export function getCsrfToken() {
    if (csrfToken) {
        return csrfToken;
    }
    
    // Try to get from meta tag first
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag && metaTag.getAttribute('content') && metaTag.getAttribute('content') !== '__CSRF_TOKEN__') {
        csrfToken = metaTag.getAttribute('content');
        return csrfToken;
    }
    
    // If not in meta tag, fetch from API
    // This will be set by axios interceptor on first request
    return null;
}

// Set CSRF token (called by axios interceptor)
export function setCsrfToken(token) {
    csrfToken = token;
}

// Get CSRF token from API endpoint
export async function fetchCsrfToken() {
    try {
        const response = await fetch('/too/api/csrf-token', {
            credentials: 'include' // Include cookies for session
        });
        if (response.ok) {
            const data = await response.json();
            setCsrfToken(data.csrf_token);
            return data.csrf_token;
        }
    } catch (error) {
        console.error('Failed to fetch CSRF token:', error);
    }
    return null;
}

// Get CSRF token for form fields (synchronous)
export function getCsrfTokenForForm() {
    return getCsrfToken() || '';
}
