#!/usr/bin/env python3
"""FCN Calculator local server - uses Futu OpenAPI for real-time data, Yahoo as fallback for spot price"""
import http.server
import json
import os
import time
import urllib.request
import urllib.parse
import re
import sys

PORT = 8899
DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Yahoo Finance (spot price only) ----
_yf_cookie = None
_yf_crumb = None
_yf_auth_time = 0

def get_yahoo_auth():
    global _yf_cookie, _yf_crumb, _yf_auth_time
    now = time.time()
    if _yf_cookie and _yf_crumb and (now - _yf_auth_time) < 300:
        return _yf_cookie, _yf_crumb
    req = urllib.request.Request('https://fc.yahoo.com', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        urllib.request.urlopen(req)
        sc = ''
    except Exception as e:
        sc = e.headers.get('Set-Cookie', '') if hasattr(e, 'headers') else ''
    m = re.search(r'A3=([^;]+)', sc)
    if not m:
        raise Exception('Failed to get Yahoo cookie')
    a3 = 'A3=' + m.group(1)
    req2 = urllib.request.Request(
        'https://query2.finance.yahoo.com/v1/test/getcrumb',
        headers={'User-Agent': 'Mozilla/5.0', 'Cookie': a3}
    )
    crumb = urllib.request.urlopen(req2).read().decode()
    if not crumb or '<' in crumb:
        raise Exception('Failed to get Yahoo crumb')
    _yf_cookie, _yf_crumb, _yf_auth_time = a3, crumb, now
    return a3, crumb

def yahoo_spot(ticker):
    cookie, crumb = get_yahoo_auth()
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d&crumb={urllib.parse.quote(crumb)}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cookie': cookie})
    data = json.loads(urllib.request.urlopen(req).read())
    result = data['chart']['result'][0]
    return {
        'symbol': result['meta']['symbol'],
        'name': result['meta'].get('shortName', result['meta']['symbol']),
        'price': result['meta']['regularMarketPrice'],
    }

# ---- Futu OpenAPI ----
def futu_available():
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ctx.close()
        return True
    except:
        return False

_futu_ok = None

def check_futu():
    global _futu_ok
    if _futu_ok is None:
        _futu_ok = futu_available()
        print(f'Futu OpenD: {"connected" if _futu_ok else "not available"}')
    return _futu_ok

def futu_spot(ticker):
    """Get spot price from Futu, returns dict or None"""
    try:
        from futu import OpenQuoteContext, RET_OK
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ret, data = ctx.get_market_snapshot([f'US.{ticker}'])
        ctx.close()
        if ret == RET_OK and not data.empty:
            row = data.iloc[0]
            return {
                'symbol': ticker,
                'name': row.get('name', ticker),
                'price': float(row['last_price']),
            }
    except:
        pass
    return None

def futu_option_expirations(ticker):
    from futu import OpenQuoteContext, RET_OK
    ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data = ctx.get_option_expiration_date(f'US.{ticker}')
    ctx.close()
    if ret != RET_OK:
        raise Exception(f'Futu error: {data}')
    return data['strike_time'].tolist()

def futu_option_chain(ticker, expiry_date):
    from futu import OpenQuoteContext, RET_OK, OptionType
    ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

    # Get put option codes for this expiry
    ret, chain = ctx.get_option_chain(
        f'US.{ticker}',
        start=expiry_date, end=expiry_date,
        option_type=OptionType.PUT
    )
    if ret != RET_OK or chain.empty:
        ctx.close()
        raise Exception(f'No options for {expiry_date}')

    codes = chain['code'].tolist()
    strikes = dict(zip(chain['code'], chain['strike_price']))

    # Get real-time snapshot for all put codes
    ret, snap = ctx.get_market_snapshot(codes)
    ctx.close()

    if ret != RET_OK:
        raise Exception(f'Snapshot error: {snap}')

    puts = []
    for _, row in snap.iterrows():
        code = row['code']
        puts.append({
            'strike': float(strikes[code]),
            'bid': float(row['bid_price']) if row['bid_price'] else 0,
            'ask': float(row['ask_price']) if row['ask_price'] else 0,
            'lastPrice': float(row['last_price']) if row['last_price'] else 0,
            'volume': int(row['volume']) if row['volume'] else 0,
            'openInterest': int(row.get('open_interest', 0)) if row.get('open_interest') else 0,
        })

    puts.sort(key=lambda p: p['strike'])
    return puts

# ---- Yahoo fallback for options ----
def yahoo_option_expirations(ticker):
    cookie, crumb = get_yahoo_auth()
    url = f'https://query1.finance.yahoo.com/v7/finance/options/{ticker}?crumb={urllib.parse.quote(crumb)}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cookie': cookie})
    data = json.loads(urllib.request.urlopen(req).read())
    result = data['optionChain']['result'][0]
    # Convert epochs to date strings
    import datetime
    dates = [datetime.datetime.fromtimestamp(e).strftime('%Y-%m-%d') for e in result['expirationDates']]
    return dates

def yahoo_option_chain(ticker, expiry_date):
    import datetime
    # Convert date string to epoch
    dt = datetime.datetime.strptime(expiry_date, '%Y-%m-%d')
    epoch = int(dt.timestamp())
    cookie, crumb = get_yahoo_auth()
    url = f'https://query1.finance.yahoo.com/v7/finance/options/{ticker}?date={epoch}&crumb={urllib.parse.quote(crumb)}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cookie': cookie})
    data = json.loads(urllib.request.urlopen(req).read())
    yf_puts = data['optionChain']['result'][0]['options'][0]['puts']
    puts = []
    for p in yf_puts:
        puts.append({
            'strike': p['strike'],
            'bid': p.get('bid', 0) or 0,
            'ask': p.get('ask', 0) or 0,
            'lastPrice': p.get('lastPrice', 0) or 0,
            'volume': p.get('volume', 0) or 0,
            'openInterest': p.get('openInterest', 0) or 0,
        })
    return puts

# ---- HTTP Handler ----
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
                self._json({'error': 'Missing ticker'}, 400)
                return

            ticker = ticker.upper()

            try:
                if api_type == 'quote':
                    # Try Futu first, fallback to Yahoo
                    result = None
                    if check_futu():
                        result = futu_spot(ticker)
                    if not result:
                        result = yahoo_spot(ticker)
                    self._json(result)

                elif api_type == 'expirations':
                    if check_futu():
                        dates = futu_option_expirations(ticker)
                    else:
                        dates = yahoo_option_expirations(ticker)
                    self._json({'expirations': dates})

                elif api_type == 'options':
                    if not date:
                        self._json({'error': 'Missing date param (YYYY-MM-DD)'}, 400)
                        return
                    if check_futu():
                        puts = futu_option_chain(ticker, date)
                    else:
                        puts = yahoo_option_chain(ticker, date)
                    self._json({'puts': puts})

                else:
                    self._json({'error': f'Unknown type: {api_type}'}, 400)
            except Exception as e:
                self._json({'error': str(e)}, 502)
            return

        super().do_GET()

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f'[{self.log_date_time_string()}] {args[0]}')

if __name__ == '__main__':
    check_futu()
    print(f'FCN Calculator running at http://localhost:{PORT}')
    server = http.server.HTTPServer(('', PORT), Handler)
    server.serve_forever()
