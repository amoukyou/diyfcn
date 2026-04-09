// Cloudflare Worker - Yahoo Finance proxy
// Deploy: wrangler deploy
// Or paste into Cloudflare Dashboard > Workers > Create Worker

const ALLOWED_ORIGINS = ['*']; // Restrict in production

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const ticker = url.searchParams.get('ticker');
    const type = url.searchParams.get('type') || 'quote'; // quote | options
    const date = url.searchParams.get('date') || '';

    if (!ticker) {
      return new Response(JSON.stringify({ error: 'Missing ticker param' }), {
        status: 400,
        headers: corsHeaders(),
      });
    }

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    let yahooUrl;
    if (type === 'options') {
      yahooUrl = `https://query1.finance.yahoo.com/v7/finance/options/${ticker}`;
      if (date) yahooUrl += `?date=${date}`;
    } else {
      yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1d&interval=1d`;
    }

    try {
      const resp = await fetch(yahooUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0',
        },
      });
      const data = await resp.text();
      return new Response(data, {
        status: resp.status,
        headers: {
          ...corsHeaders(),
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=60',
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 502,
        headers: corsHeaders(),
      });
    }
  },
};

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}
