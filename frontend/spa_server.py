from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent / "dist"
os.chdir(ROOT)

BACKEND = "http://127.0.0.1:8000"

class SPAHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Help avoid stale SPA bundles behind CDN/browser caches.
        try:
            if self.path in ('/index.html', '/', ''):
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            elif self.path.startswith('/assets/'):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
        except Exception:
            pass
        return super().end_headers()

    def _proxy(self):
        # Proxy /api/* to backend
        url = BACKEND + self.path
        try:
            req = urllib.request.Request(url, method=self.command)
            # forward headers (minimal)
            auth = self.headers.get('Authorization')
            if auth:
                req.add_header('Authorization', auth)
            req.add_header('Content-Type', self.headers.get('Content-Type', 'application/json'))

            body = None
            if self.command in ('POST','PUT','PATCH'):
                length = int(self.headers.get('Content-Length', '0') or '0')
                body = self.rfile.read(length) if length > 0 else None
                if body is not None:
                    req.data = body

            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    # skip hop-by-hop
                    if k.lower() in ('transfer-encoding','connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailers','upgrade'):
                        continue
                    self.send_header(k, v)
                self.end_headers()
                data = resp.read()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            # Forward backend error status + body (avoid turning 4xx into 502)
            self.send_response(e.code)
            for k, v in (e.headers.items() if e.headers else []):
                if k.lower() in ('transfer-encoding','connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailers','upgrade'):
                    continue
                self.send_header(k, v)
            # If backend didn't specify content-type, fall back
            if not (e.headers and e.headers.get('Content-Type')):
                self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            body = e.read() if hasattr(e, 'read') else b''
            self.wfile.write(body)
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"proxy error: {e}".encode('utf-8'))

    def _rewrite_spa_path_if_needed(self):
        target = (ROOT / self.path.lstrip('/')).resolve()
        if self.path.startswith('/assets/') or self.path == '/vite.svg' or self.path == '/index.html':
            return
        if self.path == '/' or not target.exists() or target.is_dir():
            self.path = '/index.html'

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._proxy()
        self._rewrite_spa_path_if_needed()
        return super().do_GET()

    def do_HEAD(self):
        # Some CDNs/browsers use HEAD for route checks. Keep SPA behavior consistent.
        if self.path.startswith('/api/'):
            return self._proxy()
        self._rewrite_spa_path_if_needed()
        return super().do_HEAD()

    def do_POST(self):
        if self.path.startswith('/api/'):
            return self._proxy()
        return self.send_error(405)

if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', 8081), SPAHandler)
    print('SPA+API proxy server running on :8081')
    server.serve_forever()
