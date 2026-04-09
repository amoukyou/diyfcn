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

  // Step 1: get A3 cookie from Yahoo
  const initRes = await fetch('https://fc.yahoo.com', {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    redirect: 'manual',
  });

  // Extract A3 cookie
  const setCookieHeader = initRes.headers.get('set-cookie') || '';
  const a3Match = setCookieHeader.match(/A3=([^;]+)/);
  if (!a3Match) throw new Error('Failed to get A3 cookie');
  const a3Cookie = 'A3=' + a3Match[1];

  // Step 2: get crumb using A3 cookie
  const crumbRes = await fetch('https://query2.finance.yahoo.com/v1/test/getcrumb', {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Cookie': a3Cookie,
    },
  });
  const crumb = await crumbRes.text();

  if (!crumb || crumb.includes('<') || crumb.includes('{')) {
    throw new Error('Failed to get crumb: ' + crumb.substring(0, 100));
  }

  cachedCookie = a3Cookie;
  cachedCrumb = crumb;
  cacheTime = now;
  return { cookie: a3Cookie, crumb };
}

async function yahooFetch(type, ticker, date, cookie, crumb) {
  let yahooUrl;
  if (type === 'options') {
    yahooUrl = `https://query1.finance.yahoo.com/v7/finance/options/${ticker}?crumb=${encodeURIComponent(crumb)}`;
    if (date) yahooUrl += `&date=${date}`;
  } else {
    yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1d&interval=1d&crumb=${encodeURIComponent(crumb)}`;
  }
  return await fetch(yahooUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Cookie': cookie,
    },
  });
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
      let { cookie, crumb } = await getAuth();
      let resp = await yahooFetch(type, ticker, date, cookie, crumb);

      // If 401, invalidate cache and retry once
      if (resp.status === 401) {
        cachedCookie = null;
        cachedCrumb = null;
        const auth2 = await getAuth();
        resp = await yahooFetch(type, ticker, date, auth2.cookie, auth2.crumb);
      }

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
