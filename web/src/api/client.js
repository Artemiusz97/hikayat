export const apiCall = async (endpoint, options = {}) => {
  const timeoutMs = options.timeout || 120000;
  let timedOut = false;
  const controller = new AbortController();
  const id = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener('abort', onExternalAbort, { once: true });
    }
  }

  let authHeaders = {};
  try {
    const rawUser = localStorage.getItem('cf_user');
    if (rawUser) {
      const parsed = JSON.parse(rawUser);
      if (parsed && typeof parsed.auth_token === 'string' && parsed.auth_token.trim()) {
        authHeaders['X-Hikayat-Token'] = parsed.auth_token.trim();
      }
    }
  } catch (e) {
    // Ignore storage parse issues
  }

  try {
    const res = await fetch(endpoint, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...options.headers,
      },
    });
    clearTimeout(id);
    let data;
    try {
      data = await res.json();
    } catch {
      data = { detail: res.statusText || `HTTP ${res.status}` };
    }
    if (!res.ok) {
      if (res.status === 401 && !String(endpoint).startsWith('/api/auth/')) {
        window.dispatchEvent(new CustomEvent('hikayat:auth-expired'));
      }
      throw new Error(data.detail || 'API Error');
    }
    return data;
  } catch (error) {
    clearTimeout(id);
    if (error.name === 'AbortError') {
      if (timedOut) {
        console.error(`API Timeout (${timeoutMs}ms) at ${endpoint}`);
        throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      error.isUserAbort = true;
      throw error;
    }
    console.error(`API Error at ${endpoint}:`, error);
    throw error;
  } finally {
    clearTimeout(id);
    if (options.signal) {
      options.signal.removeEventListener('abort', onExternalAbort);
    }
  }
};
