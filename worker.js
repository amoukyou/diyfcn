// Cloudflare Worker - Yahoo Finance proxy with cookie/crumb auth

let cachedCookie = null;
let cachedCrumb = null;
let cacheTime = 0;
const CACHE_TTL = 300000; // 5 minutes

async function getAuth() {
  const now = Date.now();
  if (cachedCookie && cachedCrumb && (now - cacheTime) < CACHE_TTL) {
    return { cookie: cachedCookie, crumb: cachedCrumb };
  }

  // Step 1: get cookies
  const initRes = await fetch('https://fc.yahoo.com', {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    redirect: 'manual',
  });
  const setCookie = initRes.headers.get('set-cookie') || '';
  const cookies = setCookie.split(',').map(c => c.split(';')[0].trim()).join('; ');

  // Step 2: get crumb
  const crumbRes = await fetch('https://query2.finance.yahoo.com/v1/test/getcrumb', {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Cookie': cookies,
    },
  });
  const crumb = await crumbRes.text();

  if (!crumb || crumb.includes('<')) {
    throw new Error('Failed to get crumb');
  }

  cachedCookie = cookies;
  cachedCrumb = crumb;
  cacheTime = now;
  return { cookie: cookies, crumb };
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    const url = new URL(request.url);
    const ticker = url.searchParams.get('ticker');
    const type = url.searchParams.get('type') || 'quote';
    const date = url.searchParams.get('date') || '';

    if (!ticker) {
      return new Response(JSON.stringify({ error: 'Missing ticker param' }), {
        status: 400,
        headers: corsHeaders(),
      });
    }

    try {
      const { cookie, crumb } = await getAuth();

      let yahooUrl;
      if (type === 'options') {
        yahooUrl = `https://query1.finance.yahoo.com/v7/finance/options/${ticker}?crumb=${encodeURIComponent(crumb)}`;
        if (date) yahooUrl += `&date=${date}`;
      } else {
        yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1d&interval=1d&crumb=${encodeURIComponent(crumb)}`;
      }

      const resp = await fetch(yahooUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0',
          'Cookie': cookie,
        },
      });

      // If 401, invalidate cache and retry once
      if (resp.status === 401) {
        cachedCookie = null;
        cachedCrumb = null;
        const auth2 = await getAuth();
        let retryUrl;
        if (type === 'options') {
          retryUrl = `https://query1.finance.yahoo.com/v7/finance/options/${ticker}?crumb=${encodeURIComponent(auth2.crumb)}`;
          if (date) retryUrl += `&date=${date}`;
        } else {
          retryUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1d&interval=1d&crumb=${encodeURIComponent(auth2.crumb)}`;
        }
        const resp2 = await fetch(retryUrl, {
          headers: {
            'User-Agent': 'Mozilla/5.0',
            'Cookie': auth2.cookie,
          },
        });
        const data2 = await resp2.text();
        return new Response(data2, {
          status: resp2.status,
          headers: { ...corsHeaders(), 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' },
        });
      }

      const data = await resp.text();
      return new Response(data, {
        status: resp.status,
        headers: { ...corsHeaders(), 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 502,
        headers: corsHeaders(),
      });
    }
  },
};
