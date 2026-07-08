/**
 * Auth helper for Playwright e2e tests.
 *
 * Attempts to log in via the backend API and injects the JWT token into
 * the browser's localStorage so that subsequent page loads are already
 * authenticated.
 *
 * Test credentials are read from environment variables:
 *   TEST_USERNAME (default: "admin")
 *   TEST_PASSWORD (default: "admin")
 *
 * If the backend is unreachable or the credentials are wrong the helper
 * returns { authenticated: false } and callers should skip auth-gated
 * assertions.
 */

const API_BASE = 'http://localhost:8000/api';

export async function loginViaAPI(page, {
  username = process.env.TEST_USERNAME || 'admin',
  password = process.env.TEST_PASSWORD || 'admin',
} = {}) {
  try {
    const response = await page.request.post(`${API_BASE}/auth/login`, {
      data: { username, password },
    });

    if (!response.ok()) {
      return { authenticated: false, reason: `Login returned ${response.status()}` };
    }

    const body = await response.json();
    const token = body.access_token;

    if (!token) {
      return { authenticated: false, reason: 'No access_token in response' };
    }

    // Inject the token into localStorage before navigating to the app
    await page.goto('/');
    await page.evaluate((t) => {
      localStorage.setItem('token', t);
    }, token);

    // Reload so the app picks up the stored token
    await page.reload();

    return { authenticated: true, token };
  } catch (err) {
    return { authenticated: false, reason: err.message };
  }
}
