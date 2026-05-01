'use strict';

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
} catch { /* no .env file */ }

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
  console.error('\n  ERROR: BOT_TOKEN is not set.\n');
  process.exit(1);
}

// ─── Upstash Redis ─────────────────────────────────────────────────────────
const UPSTASH_URL   = (process.env.UPSTASH_REST_URL   || '').replace(/\/$/, '');
const UPSTASH_TOKEN = process.env.UPSTASH_REST_TOKEN  || '';

function upstashReq(method, urlPath, body) {
  return new Promise((ok) => {
    if (!UPSTASH_URL || !UPSTASH_TOKEN) { ok(null); return; }
    const raw  = body !== undefined ? JSON.stringify(body) : null;
    const u    = new URL(UPSTASH_URL + urlPath);
    const opts = {
      hostname: u.hostname, path: u.pathname + u.search, method,
      headers: { 'Authorization': 'Bearer ' + UPSTASH_TOKEN }
    };
    if (raw) {
      opts.headers['Content-Type']   = 'application/json';
      opts.headers['Content-Length'] = Buffer.byteLength(raw);
    }
    const req = https.request(opts, res => {
      let d = ''; res.on('data', c => d += c);
      res.on('end', () => { try { ok(JSON.parse(d)); } catch { ok(null); } });
    });
    req.on('error', () => ok(null));
    if (raw) req.write(raw);
    req.end();
  });
}

async function upstashGet(key) {
  const r = await upstashReq('GET', '/get/' + encodeURIComponent(key));
  return r && r.result ? r.result : null;
}

async function upstashSet(key, value) {
  const v = typeof value === 'string' ? value : JSON.stringify(value);
  await upstashReq('POST', '/', ['SET', key, v]);
}

// ─── Boot: restore data + offset from Upstash ──────────────────────────────
let offset = 0;

async function initUpstash() {
  if (!UPSTASH_URL || !UPSTASH_TOKEN) return;
  try {
    // Restore tracker data
    const stored = await upstashGet('tracker-data');
    if (stored) {
      const parsed = typeof stored === 'string' ? JSON.parse(stored) : stored;
      fs.writeFileSync(DATA, JSON.stringify(parsed, null, 2), 'utf8');
      console.log(`  Redis:      ${(parsed.transactions||[]).length} transactions restored`);
    } else {
      const local = load();
      await upstashSet('tracker-data', JSON.stringify(local));
      console.log('  Redis:      initialised from local data.json');
    }
    // Restore Telegram offset — prevents re-processing old messages after restart
    const savedOffset = await upstashGet('tg-offset');
    if (savedOffset) {
      offset = parseInt(savedOffset) || 0;
      console.log(`  TG offset:  ${offset} (restored — bot won't replay old messages)`);
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

const sseClients = new Set();

const save = d => {
  fs.writeFileSync(DATA, JSON.stringify(d, null, 2), 'utf8');
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
const f2      = n  => (+n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cap     = s  => s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : '';
const today   = () => new Date().toISOString().slice(0, 10);
const monthOf = d  => (d || today()).slice(0, 7);
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
// FIX: Auto-Fixed transactions are the real fixed entries — don't also add
// the fixedCosts config array for the same month (that was causing double-count).
function calc(month) {
  const { transactions = [], fixedCosts = [] } = load();
  const rows = transactions.filter(t => monthOf(t.date) === month);

  const hasAutoFixed = rows.some(t => t.card === 'Auto-Fixed');

  let income = 0, fixed = 0, variable = 0;
  const cats = {};

  // Use configured fixed costs ONLY when no real Auto-Fixed txns exist yet this month
  if (!hasAutoFixed) {
    fixedCosts.forEach(({ category, amount }) => {
      fixed += +amount;
      cats[category] = (cats[category] || 0) + +amount;
    });
  }

  rows.forEach(({ type, amount, category, card }) => {
    if (type === 'credit') {
      income += +amount;
    } else if (card === 'Auto-Fixed') {
      fixed += +amount;
      cats[category] = (cats[category] || 0) + +amount;
    } else {
      variable += +amount;
      cats[category] = (cats[category] || 0) + +amount;
    }
  });

  const total = fixed + variable;
  const left  = income - total;
  const pct   = income > 0 ? Math.min(100, total / income * 100) : 0;
  // FIX: exclude Auto-Fixed from the user-facing transaction count
  const txN   = rows.filter(t => t.type === 'debit' && t.card !== 'Auto-Fixed').length;

  return { income, fixed, variable, total, left, pct, cats, txN };
}

// ─── Keyboards ─────────────────────────────────────────────────────────────
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

  if (text.startsWith('/fixed')) {
    const parts = text.split(/\s+/);
    const data  = load();
    data.fixedCosts = data.fixedCosts || [];

    // /fixed  (list only)
    if (parts.length === 1 || (parts.length === 2 && parts[1].toLowerCase() === 'costs')) {
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
`✅ <b>Income logged:</b> +${f2(tx.amount)} AED${tx.description ? ` — ${tx.description}` : ''}${fixedBlock}

💰 Income:    ${f2(c.income)} AED
🏠 Fixed:     ${f2(c.fixed)} AED
💳 Variable:  ${f2(c.variable)} AED
💵 Remaining: <b>${f2(c.left)} AED</b>
<code>${progressBar(c.pct)}</code> ${c.pct.toFixed(1)}%`,
      KB_MAIN
    );
  }

  return say(cid,
`${icon(tx.category)} <b>${tx.category}</b> — ${f2(tx.amount)} AED${tx.description ? `\n📝 ${tx.description}` : ''}
📅 ${fd(today())}

💳 Spent: ${f2(c.variable)} AED  ·  💵 Left: <b>${f2(c.left)} AED</b>
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

// ─── Callback query ────────────────────────────────────────────────────────
async function handleCB(q) {
  await tg('answerCallbackQuery', { callback_query_id: q.id });
  await handleMsg({ chat: q.message.chat, text: '/' + q.data });
}

// ─── JSON body parser ──────────────────────────────────────────────────────
function readBody(req) {
  return new Promise(ok => {
    let b = ''; req.on('data', c => b += c); req.on('end', () => ok(b));
  });
}

// ─── HTTP server ───────────────────────────────────────────────────────────
const server = http.createServer(async (req, res) => {
  const parsed   = url.parse(req.url, true);
  const pathname = parsed.pathname;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const json = (code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };

  // Health check
  if (pathname === '/health') { res.writeHead(200); res.end('ok'); return; }

  // SSE
  if (pathname === '/api/events' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Access-Control-Allow-Origin': '*' });
    res.write('data: connected\n\n');
    sseClients.add(res);
    const ping = setInterval(() => { try { res.write('data: ping\n\n'); } catch { clearInterval(ping); } }, 25000);
    req.on('close', () => { sseClients.delete(res); clearInterval(ping); });
    return;
  }

  // GET /api/data
  if (pathname === '/api/data' && req.method === 'GET') {
    json(200, load()); return;
  }

  // POST /api/transaction — add a transaction
  if (pathname === '/api/transaction' && req.method === 'POST') {
    try {
      const tx   = JSON.parse(await readBody(req));
      const data = load();
      data.transactions.push({
        id: Date.now().toString(), date: tx.date || today(),
        amount: +tx.amount, category: tx.category || 'Other',
        description: tx.description || '', type: tx.type || 'debit', card: tx.card || 'Manual'
      });
      save(data); json(201, { ok: true });
    } catch { json(400, { ok: false }); }
    return;
  }

  // DELETE /api/transaction/last
  if (pathname === '/api/transaction/last' && req.method === 'DELETE') {
    const data = load();
    if (data.transactions.length) { data.transactions.pop(); save(data); }
    json(200, { ok: true }); return;
  }

  // DELETE /api/transaction/:id — delete by ID
  const txDel = pathname.match(/^\/api\/transaction\/([^/]+)$/);
  if (txDel && req.method === 'DELETE') {
    const data = load();
    const before = data.transactions.length;
    data.transactions = data.transactions.filter(t => t.id !== txDel[1]);
    if (data.transactions.length < before) save(data);
    json(200, { ok: true }); return;
  }

  // PUT /api/transaction/:id — update a field
  const txUpd = pathname.match(/^\/api\/transaction\/([^/]+)$/);
  if (txUpd && req.method === 'PUT') {
    try {
      const patch = JSON.parse(await readBody(req));
      const data  = load();
      const t = data.transactions.find(tx => tx.id === txUpd[1]);
      if (t) { Object.assign(t, patch); save(data); }
      json(200, { ok: !!t });
    } catch { json(400, { ok: false }); }
    return;
  }

  // POST /api/fixed-cost — add fixed cost
  if (pathname === '/api/fixed-cost' && req.method === 'POST') {
    try {
      const f    = JSON.parse(await readBody(req));
      const data = load();
      data.fixedCosts = data.fixedCosts || [];
      data.fixedCosts.push({ id: Date.now().toString(), name: f.name, category: cap(f.category || f.name), amount: +f.amount });
      save(data); json(201, { ok: true });
    } catch { json(400, { ok: false }); }
    return;
  }

  // DELETE /api/fixed-cost/:id
  const fcDel = pathname.match(/^\/api\/fixed-cost\/([^/]+)$/);
  if (fcDel && req.method === 'DELETE') {
    const data = load();
    data.fixedCosts = (data.fixedCosts || []).filter(f => f.id !== fcDel[1]);
    save(data); json(200, { ok: true }); return;
  }

  // GET / — serve dashboard
  if ((pathname === '/' || pathname === '/index.html') && req.method === 'GET') {
    try {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(fs.readFileSync(HTML, 'utf8'));
    } catch { res.writeHead(500); res.end('finance_dashboard.html not found'); }
    return;
  }

  json(404, { error: 'not found' });
});

function getLocalIP() {
  for (const nets of Object.values(os.networkInterfaces()))
    for (const n of nets)
      if (n.family === 'IPv4' && !n.internal) return n.address;
  return null;
}

server.listen(PORT, '0.0.0.0', () => {
  const ip = getLocalIP();
  console.log(`  Dashboard:  http://localhost:${PORT}`);
  if (ip) console.log(`  On phone:   http://${ip}:${PORT}`);
});

// ─── Render.com keepalive ──────────────────────────────────────────────────
function startKeepalive() {
  const extUrl = process.env.RENDER_EXTERNAL_URL;
  if (!extUrl) return;
  const pingUrl = extUrl.replace(/\/$/, '') + '/health';
  setInterval(() => {
    try {
      const u = new URL(pingUrl);
      https.get({ hostname: u.hostname, path: u.pathname, headers: { 'User-Agent': 'keepalive' } }, r => r.resume()).on('error', () => {});
    } catch {}
  }, 4 * 60 * 1000);
  console.log('  Keepalive:  every 4 min → ' + pingUrl);
}

// ─── Telegram long-polling ─────────────────────────────────────────────────
async function poll() {
  try {
    const res = await tg('getUpdates', {
      offset: offset + 1, timeout: 25,
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
      // Persist offset so restarts don't replay old messages
      if (UPSTASH_URL && UPSTASH_TOKEN) {
        upstashSet('tg-offset', String(offset)).catch(() => {});
      }
    }

    if (!res.ok && res.error_code === 401) {
      console.error('\n  Invalid BOT_TOKEN.\n'); process.exit(1);
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
    if (r.ok) console.log(`  Bot:        @${r.result.username}\n  Chat:       https://t.me/${r.result.username}`);
  }).catch(() => {});
  startKeepalive();
  poll();
});
