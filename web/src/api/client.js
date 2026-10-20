export const apiCall = async (endpoint, options = {}) => {
  const timeoutMs = options.timeout || 90000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(endpoint, {
      ...options,
      signal: options.signal || controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    clearTimeout(id);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'API Error');
    }
    return data;
  } catch (error) {
    clearTimeout(id);
    if (error.name === 'AbortError') {
      console.error(`API Timeout (${timeoutMs}ms) at ${endpoint}`);
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    console.error(`API Error at ${endpoint}:`, error);
    throw error;
  }
};
