import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/health" or path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = {
                "status": "online",
                "service": "DRAK WEB OSINT API",
                "version": "3.0",
                "message": "Platform core active"
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # Web Command Center Landing Page
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DRAK WEB // AI-Powered Dark Web OSINT</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #0A0E17;
            --bg-card: rgba(17, 24, 39, 0.85);
            --border-cyan: rgba(56, 189, 248, 0.25);
            --accent-cyan: #06B6D4;
            --accent-emerald: #10B981;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-main);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem 1rem;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(6, 182, 212, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
        }
        .container {
            max-width: 800px;
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border-cyan);
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
            text-align: center;
            backdrop-filter: blur(12px);
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.35);
            color: #34D399;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 9999px;
            margin-bottom: 1.25rem;
        }
        h1 {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #F8FAFC 0%, #38BDF8 50%, #818CF8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.75rem;
        }
        p {
            color: var(--text-secondary);
            font-size: 1.05rem;
            line-height: 1.6;
            margin-bottom: 2rem;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
            text-align: left;
        }
        .card {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(56, 189, 248, 0.15);
            border-radius: 10px;
            padding: 1.2rem;
        }
        .card-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.95rem;
            font-weight: 700;
            color: #38BDF8;
            margin-bottom: 0.4rem;
        }
        .card-desc {
            font-size: 0.85rem;
            color: var(--text-secondary);
            line-height: 1.4;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, #0891B2 0%, #06B6D4 50%, #0284C7 100%);
            color: #FFFFFF;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 0.95rem;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            transition: all 0.2s ease;
            box-shadow: 0 4px 16px rgba(6, 182, 212, 0.35);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 22px rgba(6, 182, 212, 0.5);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="badge">● VERCEL DEPLOYMENT ACTIVE</div>
        <h1>DRAK WEB // OSINT COMMAND CENTER</h1>
        <p>High-Speed Autonomous Dark Web Harvester & Neural Intelligence Engine.</p>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">🌐 Multi-Node Tor Search</div>
                <div class="card-desc">Parallel harvesting across 10+ resilient dark web search engines.</div>
            </div>
            <div class="card">
                <div class="card-title">🤖 Neural Intelligence</div>
                <div class="card-desc">AI-powered threat analysis, IOC extraction & strategic dossier synthesis.</div>
            </div>
            <div class="card">
                <div class="card-title">📂 Dossier Vault</div>
                <div class="card-desc">Persistent investigation management with export & analysis workflows.</div>
            </div>
        </div>

        <a href="https://github.com/aegisforensicsmonk/fuking-brooooo" target="_blank" class="btn">
            📂 View GitHub Repository
        </a>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

# WSGI Application wrapper
def app(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html; charset=utf-8')]
    start_response(status, headers)
    return [b"<h1>DRAK WEB // DEPLOYED</h1>"]
