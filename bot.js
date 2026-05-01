'use strict';

// Manual .env loader — no npm dependencies needed
const fs   = require('fs');
const path = require('path');

try {
  const env = fs.readFileSync(path.join(__dirname, '.env'), 'utf8');
  for (const line of env.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq < 1) continue;
    const k = t.slice(0, eq).trim();
    const v = t.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '');
    if (k && !(k in process.env)) process.env[k] = v;
  }
} catch { /* no .env file, rely on environment */ }

const https = require('https');
const http  = require('http');
const url   = require('url');
const os    = require('os');

// ─── Config ────────────────────────────────────────────────────────────────
const TOKEN = process.env.BOT_TOKEN || '';
const PORT  = parseInt(process.env.PORT || '3000', 10);
const DATA  = path.join(__dirname, 'data.json');
const HTML  = path.join(__dirname, 'finance_dashboard.html');

if (!TOKEN) {
  console.error('\n  ERROR: BOT_TOKEN is not set.');
  console.error('  Create a .env file and add:  BOT_TOKEN=your_token_here');
  process.exit(1);
}

// ─── Upstash Redis (free HTTP-based storage, no npm needed) ───────────────
const UPSTASH_URL   = (process.env.UPSTASH_REST_URL   || '').replace(/\/$/, '');
const UPSTASH_TOKEN = process.env.UPSTASH_REST_TOKEN  || '';

function upstashReq(method, urlPath, body) {
  return new Promise((ok, fail) => {
    if (!UPSTASH_URL || !UPSTASH_TOKEN) { ok(null); return; }
    const u    = new URL(UPSTASH_URL + urlPath);
    const opts = {
      hostname: u.hostname, path: u.pathname + u.search, method,
      headers: { 'Authorization': 'Bearer ' + UPSTASH_TOKEN }
    };
    let raw = null;
    if (body !== undefined) {
      raw = JSON.stringify(body);
      opts.headers['Content-Type']   = 'application/json';
      opts.headers['Content-Length'] = Buffer.byteLength(raw);
    }
    const req = https.request(opts, res => {
      let d = ''; res.on('data', c => d += c);
      res.on('end', () => { try { ok(JSON.parse(d)); } catch { ok(null); } });
    });
    req.on('error', e => { console.error('Upstash error:', e.message); ok(null); });
    if (raw) req.write(raw);
    req.end();
  });
}

async function upstashGet(key) {
  const r = await upstashReq('GET', '/get/' + encodeURIComponent(key));
  return r && r.result ? r.result : null;
}

async function upstashSet(key, value) {
  // Use POST /set/<key> with value as JSON string in body array form
  await upstashReq('POST', '/', ['SET', key, typeof value === 'string' ? value : JSON.stringify(value)]);
}

async function initUpstash() {
  if (!UPSTASH_URL || !UPSTASH_TOKEN) return;
  try {
    const stored = await upstashGet('tracker-data');
    if (stored) {
      const parsed = typeof stored === 'string' ? JSON.parse(stored) : stored;
      fs.writeFileSync(DATA, JSON.stringify(parsed, null, 2), 'utf8');
      console.log(`  Redis:      ${(parsed.transactions||[]).length} transactions restored from Upstash`);
    } else {
      const local = load();
      await upstashSet('tracker-data', JSON.stringify(local));
      console.log('  Redis:      initialised from local data.json');
    }
  } catch (e) {
    console.error('  Upstash init error:', e.message);
  }
}

// ─── Data helpers ──────────────────────────────────────────────────────────
const load = () => {
  try { return JSON.parse(fs.readFileSync(DATA, 'utf8')); }
  catch { return { transactions: [], fixedCosts: [] }; }
};

// SSE clients — every connected browser tab gets instant push on save
const sseClients = new Set();

const save = d => {
  fs.writeFileSync(DATA, JSON.stringify(d, null, 2), 'utf8');
  // Write-through to Upstash (async, don't await)
  if (UPSTASH_URL && UPSTASH_TOKEN) {
    upstashSet('tracker-data', JSON.stringify(d))
      .catch(e => console.error('Upstash write:', e.message));
  }
  const payload = `data: ${JSON.stringify(d)}\n\n`;
  for (const client of sseClients) {
    try { client.write(payload); } catch { sseClients.delete(client); }
  }
};

// ─── Telegram API ──────────────────────────────────────────────────────────
const tg = (method, body = {}) => new Promise((resolve, reject) => {
  const raw = JSON.stringify(body);
  const req = https.request({
    hostname: 'api.telegram.org',
    path: `/bot${TOKEN}/${method}`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(raw) }
  }, res => {
    let buf = '';
    res.on('data', c => buf += c);
    res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { resolve({ ok: false }); } });
  });
  req.on('error', reject);
  req.write(raw);
  req.end();
});

const say = (id, text, extra = {}) =>
  tg('sendMessage', { chat_id: id, text, parse_mode: 'HTML', ...extra });

// ─── Helpers ───────────────────────────────────────────────────────────────
const f2     = n  => (+n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cap    = s  => s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : '';
const today  = () => new Date().toISOString().slice(0, 10);
const monthOf = d => (d || today()).slice(0, 7);
const nowMonth = () => monthOf(today());

const MN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ml = m  => { const [y, mo] = m.split('-'); return `${MN[+mo - 1]} ${y}`; };
const fd = d  => { const [, m, day] = (d || today()).split('-'); return `${day} ${MN[+m - 1]}`; };

const ICONS = {
  food:'🍽️', coffee:'☕', cafe:'☕', restaurant:'🍽️', lunch:'🍽️', dinner:'🍽️', breakfast:'🍽️',
  rent:'🏠', housing:'🏠', apartment:'🏠',
  etisalat:'📱', du:'📱', telecom:'📱', phone:'📱', mobile:'📱',
  autoloan:'🚗', loan:'💳', car:'🚗',
  fuel:'⛽', petrol:'⛽', gas:'⛽',
  transport:'🚕', taxi:'🚕', uber:'🚕', careem:'🚕', metro:'🚇',
  shopping:'🛍️', clothes:'👗', fashion:'👗', amazon:'📦',
  health:'💊', pharmacy:'💊', doctor:'🏥', medical:'🏥',
  entertainment:'🎬', movies:'🎬', cinema:'🎬', netflix:'📺',
  travel:'✈️', holiday:'✈️', vacation:'✈️', hotel:'🏨',
  gym:'💪', sport:'💪', fitness:'💪',
  grocery:'🛒', groceries:'🛒', supermarket:'🛒', carrefour:'🛒',
  salary:'💰', income:'💰', freelance:'💰', bonus:'💰',
  savings:'🏦', saving:'🏦',
  utilities:'⚡', electricity:'⚡', water:'💧', internet:'🌐',
  subscription:'📺', spotify:'🎵',
};
const icon = cat => ICONS[(cat || '').toLowerCase().replace(/[\s-]/g, '')] || '💳';

const progressBar = pct => {
  const n = Math.round(Math.min(pct, 100) / 10);
  return '█'.repeat(n) + '░'.repeat(10 - n);
};

// ─── Monthly calculation ───────────────────────────────────────────────────
function calc(month) {
  const { transactions = [], fixedCosts = [] } = load();
  const rows = transactions.filter(t => monthOf(t.date) === month);

  let income = 0, fixed = 0, variable = 0;
  const cats = {};

  fixedCosts.forEach(({ category, amount }) => {
    fixed += +amount;
    cats[category] = (cats[category] || 0) + +amount;
  });

  rows.forEach(({ type, amount, category }) => {
    if (type === 'credit') {
      income += +amount;
    } else {
      variable += +amount;
      cats[category] = (cats[category] || 0) + +amount;
    }
  });

  const total = fixed + variable;
  const left  = income - total;
  const pct   = income > 0 ? Math.min(100, total / income * 100) : 0;
  const txN   = rows.filter(t => t.type === 'debit').length;

  return { income, fixed, variable, total, left, pct, cats, txN };
}

// ─── Inline keyboard shortcuts ─────────────────────────────────────────────
const KB_MAIN = { reply_markup: { inline_keyboard: [[
  { text: '📊 Balance',    callback_data: 'balance' },
  { text: '📂 Categories', callback_data: 'categories' },
  { text: '↩️ Undo',      callback_data: 'undo' }
]] } };

// ─── Message handler ───────────────────────────────────────────────────────
async function handleMsg(msg) {
  const cid  = msg.chat.id;
  const text = (msg.text || '').trim().replace(/@\w+$/, '');
  if (!text) return;

  const month = nowMonth();

  // /start  /help
  if (text === '/start' || text === '/help') {
    return say(cid,
`<b>💰 Expense Tracker Bot</b>

<b>Log an expense:</b>
<code>50 food lunch</code>
<code>120 shopping new shoes</code>
<code>35.5 transport uber home</code>

<b>Log income:</b>
<code>+10000</code>  or  <code>+10000 salary</code>

<b>Commands:</b>
  /balance — this month's summary
  /report — full category breakdown
  /categories — spending by category
  /last — last 10 transactions
  /undo — remove last entry
  /fixed — manage recurring monthly costs
  /help — show this message`
    );
  }

  // /balance  /summary
  if (['/balance', '/summary', '/b'].includes(text)) {
    const c = calc(month);
    const status = c.pct >= 100 ? '🔴 OVER BUDGET' : c.pct >= 80 ? '🟡 NEAR LIMIT' : '🟢 ON TRACK';
    return say(cid,
`<b>📊 ${ml(month)} — Summary</b>

💰 Income:    <b>${f2(c.income)} AED</b>
🏠 Fixed:     <b>${f2(c.fixed)} AED</b>
💳 Variable:  <b>${f2(c.variable)} AED</b>
<code>────────────────────</code>
💵 Remaining: <b>${f2(c.left)} AED</b>

<code>${progressBar(c.pct)}</code> ${c.pct.toFixed(1)}%
${status}  ·  ${c.txN} transactions`,
      { reply_markup: { inline_keyboard: [[
        { text: '📋 Report',      callback_data: 'report' },
        { text: '📂 Categories',  callback_data: 'categories' },
        { text: '🕐 History',     callback_data: 'last' }
      ]] } }
    );
  }

  // /report
  if (['/report', '/r'].includes(text)) {
    const c = calc(month);
    const sorted = Object.entries(c.cats).sort((a, b) => b[1] - a[1]);
    if (!sorted.length) return say(cid, `No expenses in ${ml(month)} yet.`);
    const lines = sorted.map(([cat, amt]) => {
      const pct = c.total > 0 ? (amt / c.total * 100).toFixed(0) : 0;
      return `${icon(cat)} <b>${cat}</b>: ${f2(amt)} AED (${pct}%)`;
    }).join('\n');
    return say(cid,
`<b>📋 ${ml(month)} — Full Report</b>

${lines}
<code>────────────────────</code>
<b>Total spent: ${f2(c.total)} AED</b>
Remaining:   ${f2(c.left)} AED`
    );
  }

  // /categories
  if (['/categories', '/cats', '/c'].includes(text)) {
    const c = calc(month);
    const sorted = Object.entries(c.cats).sort((a, b) => b[1] - a[1]);
    if (!sorted.length) return say(cid, `No expenses in ${ml(month)} yet.`);
    const lines = sorted.map(([cat, amt]) => {
      const pct = c.total > 0 ? (amt / c.total * 100).toFixed(0) : 0;
      return `${icon(cat)} <b>${cat}</b>: ${f2(amt)} AED (${pct}%)`;
    }).join('\n');
    return say(cid, `<b>📂 ${ml(month)} — Categories</b>\n\n${lines}\n\n<b>Total: ${f2(c.total)} AED</b>`);
  }

  // /last [n]
  if (text.startsWith('/last') || text === '/history' || text === '/l') {
    const n = parseInt(text.split(' ')[1] || '10');
    const { transactions = [] } = load();
    const recent = transactions.slice(-Math.min(n, 20)).reverse();
    if (!recent.length) return say(cid, 'No transactions logged yet.');
    const lines = recent.map(t => {
      const sign = t.type === 'credit' ? '+' : '-';
      const desc = t.description ? ` — ${t.description}` : '';
      return `${icon(t.category)} <b>${sign}${f2(t.amount)} AED</b> ${t.category}${desc}\n   📅 ${fd(t.date)} · <code>${t.id}</code>`;
    }).join('\n\n');
    return say(cid, `<b>🕐 Last ${recent.length} Transactions</b>\n\n${lines}`);
  }

  // /undo  /delete
  if (text === '/undo' || text === '/delete') {
    const data = load();
    if (!data.transactions.length) return say(cid, 'Nothing to undo.');
    const t = data.transactions.pop();
    save(data);
    const sign = t.type === 'credit' ? '+' : '-';
    return say(cid,
`↩️ <b>Removed:</b> ${icon(t.category)} ${sign}${f2(t.amount)} AED — ${t.category}${t.description ? ` (${t.description})` : ''}
📅 ${fd(t.date)}`
    );
  }

  // /fixed
  if (text.startsWith('/fixed')) {
    const parts = text.split(/\s+/);
    const data  = load();
    data.fixedCosts = data.fixedCosts || [];

    if (parts.length === 1) {
      if (!data.fixedCosts.length) {
        return say(cid,
`<b>🏠 Fixed Monthly Costs</b>

None set up yet. These auto-apply every month.

Add one:
<code>/fixed add 3000 Rent</code>
<code>/fixed add 350 Etisalat</code>
<code>/fixed add 1200 Auto-loan</code>`
        );
      }
      const total = data.fixedCosts.reduce((s, f) => s + (+f.amount || 0), 0);
      const lines = data.fixedCosts.map(f => `• <b>${f.name}</b>: ${f2(f.amount)} AED`).join('\n');
      return say(cid,
`<b>🏠 Fixed Monthly Costs</b>

${lines}

<b>Total: ${f2(total)} AED/month</b>

Add:    <code>/fixed add 3000 Rent</code>
Remove: <code>/fixed remove Rent</code>`
      );
    }

    const sub = parts[1].toLowerCase();

    if (sub === 'add' && parts.length >= 4) {
      const amount = parseFloat(parts[2]);
      if (isNaN(amount) || amount <= 0)
        return say(cid, '❌ Invalid amount. Try: <code>/fixed add 3000 Rent</code>');
      const name     = parts.slice(3).join(' ');
      const category = cap(parts[3]);
      data.fixedCosts.push({ id: Date.now().toString(), name, category, amount });
      save(data);
      return say(cid, `✅ Added fixed cost: <b>${name}</b> — ${f2(amount)} AED/month`);
    }

    if (sub === 'remove' && parts.length >= 3) {
      const name   = parts.slice(2).join(' ').toLowerCase();
      const before = data.fixedCosts.length;
      data.fixedCosts = data.fixedCosts.filter(
        f => f.name.toLowerCase() !== name && f.category.toLowerCase() !== name
      );
      if (data.fixedCosts.length < before) {
        save(data);
        return say(cid, `✅ Removed: <b>${parts.slice(2).join(' ')}</b>`);
      }
      return say(cid, `❌ Not found: <b>${parts.slice(2).join(' ')}</b>`);
    }

    return say(cid,
`<b>Fixed cost commands:</b>
/fixed — list all
<code>/fixed add 3000 Rent</code>
<code>/fixed remove Rent</code>`
    );
  }

  // Parse as a transaction
  const tx = parseTx(text);
  if (!tx) {
    return say(cid,
`❓ <b>Can't understand that.</b>

Expense: <code>50 food lunch</code>
Income:  <code>+10000 salary</code>

Type /help for all commands.`
    );
  }

  const data = load();
  const baseId = Date.now();
  data.transactions.push({
    id: String(baseId),
    date: today(),
    amount: tx.amount,
    category: tx.category,
    description: tx.description,
    type: tx.type,
    card: 'Telegram'
  });

  // Auto-deduct configured fixed costs the moment income is received
  let autoFixed = [];
  if (tx.type === 'credit' && (data.fixedCosts||[]).length > 0) {
    const alreadyDone = data.transactions.some(t =>
      monthOf(t.date) === month && t.card === 'Auto-Fixed'
    );
    if (!alreadyDone) {
      data.fixedCosts.forEach((f, i) => {
        data.transactions.push({
          id: String(baseId + i + 1),
          date: today(),
          amount: f.amount,
          category: f.category,
          description: f.name,
          type: 'debit',
          card: 'Auto-Fixed'
        });
        autoFixed.push(f);
      });
    }
  }

  save(data);

  const c = calc(month);

  if (tx.type === 'credit') {
    const fixedBlock = autoFixed.length
      ? '\n\n🏠 <b>Fixed costs auto-deducted:</b>\n' +
        autoFixed.map(f => `  • ${f.name}: −${f2(f.amount)} AED`).join('\n') +
        `\n  ──────────────────\n  Total fixed: −${f2(autoFixed.reduce((s,f)=>s+(+f.amount),0))} AED`
      : '';
    return say(cid,
`✅ <b>Salary logged:</b> +${f2(tx.amount)} AED${tx.description ? ` — ${tx.description}` : ''}${fixedBlock}

💰 Income: ${f2(c.income)} AED
💵 Remaining: <b>${f2(c.left)} AED</b>
<code>${progressBar(c.pct)}</code> ${c.pct.toFixed(1)}%`,
      KB_MAIN
    );
  }

  return say(cid,
`${icon(tx.category)} <b>${tx.category}</b> — ${f2(tx.amount)} AED${tx.description ? `\n📝 ${tx.description}` : ''}
📅 ${fd(today())}

💳 Spent: ${f2(c.total)} AED  ·  💵 Left: <b>${f2(c.left)} AED</b>
<code>${progressBar(c.pct)}</code> ${c.pct.toFixed(1)}%`,
    KB_MAIN
  );
}

function parseTx(text) {
  if (text.startsWith('+')) {
    const parts  = text.slice(1).trim().split(/\s+/);
    const amount = parseFloat(parts[0]);
    if (isNaN(amount) || amount <= 0) return null;
    return { type: 'credit', amount, category: 'Income', description: parts.slice(1).join(' ') };
  }
  const parts  = text.split(/\s+/);
  const amount = parseFloat(parts[0]);
  if (isNaN(amount) || amount <= 0 || !parts[1]) return null;
  return { type: 'debit', amount, category: cap(parts[1]), description: parts.slice(2).join(' ') };
}

// ─── Callback query handler ────────────────────────────────────────────────
async function handleCB(q) {
  await tg('answerCallbackQuery', { callback_query_id: q.id });
  await handleMsg({ chat: q.message.chat, text: '/' + q.data });
}

// ─── HTTP server (API + dashboard) ────────────────────────────────────────
const server = http.createServer((req, res) => {
  const { pathname } = url.parse(req.url, true);

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  // GET /health — Render.com uptime check
  if (pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('ok');
    return;
  }

  // GET /api/events  — Server-Sent Events for instant dashboard updates
  if (pathname === '/api/events' && req.method === 'GET') {
    res.writeHead(200, {
      'Content-Type':  'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection':    'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });
    res.write('data: connected\n\n');
    sseClients.add(res);
    const ping = setInterval(() => { try { res.write('data: ping\n\n'); } catch { clearInterval(ping); } }, 25000);
    req.on('close', () => { sseClients.delete(res); clearInterval(ping); });
    return;
  }

  // GET /api/data
  if (pathname === '/api/data' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(load()));
    return;
  }

  // POST /api/transaction
  if (pathname === '/api/transaction' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const tx   = JSON.parse(body);
        const data = load();
        data.transactions.push({
          id: Date.now().toString(),
          date: tx.date || today(),
          amount: +tx.amount,
          category: tx.category || 'Other',
          description: tx.description || '',
          type: tx.type || 'debit',
          card: tx.card || 'Manual'
        });
        save(data);
        res.writeHead(201, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: 'invalid json' }));
      }
    });
    return;
  }

  // DELETE /api/transaction/last
  if (pathname === '/api/transaction/last' && req.method === 'DELETE') {
    const data = load();
    if (data.transactions.length) { data.transactions.pop(); save(data); }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  // GET /  — serve dashboard
  if ((pathname === '/' || pathname === '/index.html') && req.method === 'GET') {
    try {
      const html = fs.readFileSync(HTML, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch {
      res.writeHead(500);
      res.end('finance_dashboard.html not found in the same folder as bot.js');
    }
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found' }));
});

function getLocalIP() {
  for (const nets of Object.values(os.networkInterfaces())) {
    for (const n of nets) {
      if (n.family === 'IPv4' && !n.internal) return n.address;
    }
  }
  return null;
}

server.listen(PORT, '0.0.0.0', () => {
  const ip = getLocalIP();
  console.log(`  Dashboard:  http://localhost:${PORT}`);
  if (ip) console.log(`  On phone:   http://${ip}:${PORT}   ← open this on your phone`);
});

// ─── Render.com free-tier keepalive — ping self every 4 min so the dyno stays awake
function startKeepalive() {
  const extUrl = process.env.RENDER_EXTERNAL_URL;
  if (!extUrl) return;
  const pingUrl = extUrl.replace(/\/$/, '') + '/health';
  setInterval(() => {
    try {
      const u = new URL(pingUrl);
      https.get({ hostname: u.hostname, path: u.pathname, headers: { 'User-Agent': 'keepalive' } },
        r => r.resume()
      ).on('error', () => {});
    } catch {}
  }, 4 * 60 * 1000);
  console.log('  Keepalive:  pinging ' + pingUrl + ' every 4 min');
}

// ─── Telegram long-polling ─────────────────────────────────────────────────
let offset = 0;

async function poll() {
  try {
    const res = await tg('getUpdates', {
      offset: offset + 1,
      timeout: 25,
      allowed_updates: ['message', 'callback_query']
    });

    if (res.ok && res.result.length) {
      for (const u of res.result) {
        offset = u.update_id;
        try {
          if (u.message)        await handleMsg(u.message);
          if (u.callback_query) await handleCB(u.callback_query);
        } catch (e) { console.error('Handler error:', e.message); }
      }
    }

    if (!res.ok && res.error_code === 401) {
      console.error('\n  Invalid BOT_TOKEN — check your .env file.\n');
      process.exit(1);
    }
  } catch (e) {
    console.error('Poll error:', e.message);
    await new Promise(r => setTimeout(r, 5000));
  }
  setTimeout(poll, 500);
}

// ─── Boot ──────────────────────────────────────────────────────────────────
console.log('\n  Expense Tracker Bot');
console.log('  ═══════════════════');
initUpstash().then(() => {
  tg('getMe').then(r => {
    if (r.ok) {
      console.log(`  Bot:        @${r.result.username}`);
      console.log(`  Chat:       https://t.me/${r.result.username}`);
    }
  }).catch(() => {});
  startKeepalive();
  poll();
});
