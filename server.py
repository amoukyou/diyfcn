#!/usr/bin/env python3
"""FCN Calculator local server - proxies Yahoo Finance API"""
import http.server
import json
import os
import time
import urllib.request
import urllib.parse

PORT = 8899
DIR = os.path.dirname(os.path.abspath(__file__))

# Yahoo Finance auth cache
_cookie = None
_crumb = None
_auth_time = 0

def get_yahoo_auth():
    global _cookie, _crumb, _auth_time
    now = time.time()
    if _cookie and _crumb and (now - _auth_time) < 300:
        return _cookie, _crumb

    # Get A3 cookie
    req = urllib.request.Request('https://fc.yahoo.com', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        if hasattr(e, 'headers'):
            sc = e.headers.get('Set-Cookie', '')
        else:
            raise
    else:
        sc = ''

    import re
    m = re.search(r'A3=([^;]+)', sc)
    if not m:
        # Try again with redirect
        req2 = urllib.request.Request('https://fc.yahoo.com', headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req2)
        sc = resp.headers.get('Set-Cookie', '')
        m = re.search(r'A3=([^;]+)', sc)

    if not m:
        raise Exception('Failed to get A3 cookie')

    a3 = 'A3=' + m.group(1)

    # Get crumb
    req3 = urllib.request.Request(
        'https://query2.finance.yahoo.com/v1/test/getcrumb',
        headers={'User-Agent': 'Mozilla/5.0', 'Cookie': a3}
    )
    crumb = urllib.request.urlopen(req3).read().decode()

    if not crumb or '<' in crumb:
        raise Exception('Failed to get crumb')

    _cookie = a3
    _crumb = crumb
    _auth_time = now
    return a3, crumb

def yahoo_fetch(api_type, ticker, date=None):
    cookie, crumb = get_yahoo_auth()
    enc_crumb = urllib.parse.quote(crumb)

    if api_type == 'options':
        url = f'https://query1.finance.yahoo.com/v7/finance/options/{ticker}?crumb={enc_crumb}'
        if date:
            url += f'&date={date}'
    else:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d&crumb={enc_crumb}'

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Cookie': cookie,
    })
    resp = urllib.request.urlopen(req)
    return resp.read()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api':
            params = urllib.parse.parse_qs(parsed.query)
            ticker = params.get('ticker', [None])[0]
            api_type = params.get('type', ['quote'])[0]
            date = params.get('date', [None])[0]

            if not ticker:
                self._json_response({'error': 'Missing ticker'}, 400)
                return

            try:
                data = yahoo_fetch(api_type, ticker, date)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._json_response({'error': str(e)}, 502)
            return

        super().do_GET()

    def _json_response(self, obj, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def log_message(self, format, *args):
        print(f'[{self.log_date_time_string()}] {args[0]}')

if __name__ == '__main__':
    print(f'FCN Calculator running at http://localhost:{PORT}')
    print(f'Open http://localhost:{PORT}/index.html')
    server = http.server.HTTPServer(('', PORT), Handler)
    server.serve_forever()
