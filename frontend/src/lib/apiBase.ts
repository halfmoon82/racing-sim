// Centralized API base URL.
// In production (served behind Cloudflare Tunnel), we want same-origin requests.
// In local dev, you can set VITE_API_URL=http://localhost:8000
export const API_BASE_URL: string =
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' ? window.location.origin : '');
