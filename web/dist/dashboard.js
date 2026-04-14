'use strict';

// ─── 0. Ticker Name Lookup ────────────────────────────────────────────────
var TICKER_NAMES = {
  // Broad Market ETFs
  SPY:'S&P 500 ETF', QQQ:'Nasdaq 100 ETF', IWM:'Russell 2000 ETF', DIA:'Dow Jones ETF',
  VTI:'Total Stock Market ETF', VOO:'Vanguard S&P 500 ETF', RSP:'Equal Weight S&P 500',
  MDY:'S&P MidCap 400 ETF',
  // Sector ETFs
  XLF:'Financials Select ETF', XLE:'Energy Select ETF', XLK:'Technology Select ETF',
  XLV:'Health Care Select ETF', XLI:'Industrials Select ETF', XLP:'Consumer Staples ETF',
  XLU:'Utilities Select ETF', XLY:'Consumer Discretionary ETF', XLC:'Communication Services ETF',
  XLB:'Materials Select ETF', XLRE:'Real Estate Select ETF',
  // Thematic / Factor ETFs
  ARKK:'ARK Innovation ETF', SOXX:'iShares Semiconductor ETF', SMH:'VanEck Semiconductor ETF',
  TAN:'Invesco Solar ETF', LIT:'Global X Lithium & Battery Tech ETF', HACK:'ETFMG Cybersecurity ETF',
  IBB:'iShares Biotech ETF', XBI:'SPDR Biotech ETF', KWEB:'KraneShares China Internet ETF',
  CQQQ:'Invesco China Technology ETF', ICLN:'iShares Global Clean Energy ETF',
  QCLN:'First Trust Clean Energy ETF', BOTZ:'Global X Robotics & AI ETF',
  ROBO:'ROBO Global Robotics & AI ETF',
  // International ETFs
  EFA:'iShares MSCI EAFE ETF', EEM:'iShares MSCI Emerging Markets ETF',
  VGK:'Vanguard European ETF', EWJ:'iShares MSCI Japan ETF', FXI:'iShares China Large-Cap ETF',
  EWZ:'iShares MSCI Brazil ETF', INDA:'iShares MSCI India ETF', EWT:'iShares MSCI Taiwan ETF',
  EWY:'iShares MSCI South Korea ETF', VWO:'Vanguard Emerging Markets ETF',
  IEMG:'iShares Core MSCI Emerging Markets ETF', MCHI:'iShares MSCI China ETF',
  EWG:'iShares MSCI Germany ETF', EWU:'iShares MSCI United Kingdom ETF',
  EWQ:'iShares MSCI France ETF', EWP:'iShares MSCI Spain ETF', EWI:'iShares MSCI Italy ETF',
  EWN:'iShares MSCI Netherlands ETF', EWL:'iShares MSCI Switzerland ETF',
  EWA:'iShares MSCI Australia ETF', EWC:'iShares MSCI Canada ETF',
  EWS:'iShares MSCI Singapore ETF', EWM:'iShares MSCI Malaysia ETF',
  EWW:'iShares MSCI Mexico ETF', EWH:'iShares MSCI Hong Kong ETF',
  THD:'iShares MSCI Thailand ETF', VNM:'VanEck Vietnam ETF',
  EIDO:'iShares MSCI Indonesia ETF', EPHE:'iShares MSCI Philippines ETF', FM:'iShares Frontier & Select EM ETF',
  // Bond / Fixed Income ETFs
  TLT:'iShares 20+ Year Treasury Bond ETF', IEF:'iShares 7-10 Year Treasury ETF',
  SHY:'iShares 1-3 Year Treasury ETF', HYG:'iShares High Yield Corporate Bond ETF',
  LQD:'iShares Investment Grade Corporate Bond ETF', AGG:'iShares Core US Aggregate Bond ETF',
  BND:'Vanguard Total Bond Market ETF', TIP:'iShares TIPS Bond ETF',
  EMB:'iShares JP Morgan USD Emerging Markets Bond ETF', JNK:'SPDR Bloomberg High Yield Bond ETF',
  BWX:'SPDR Bloomberg International Treasury Bond ETF', IGOV:'iShares Intl Treasury Bond ETF',
  LEMB:'iShares EM Local Currency Bond ETF', EMLC:'VanEck EM Local Currency Bond ETF',
  // Currency ETFs
  FXE:'Invesco CurrencyShares Euro ETF', FXY:'Invesco CurrencyShares Japanese Yen ETF',
  FXB:'Invesco CurrencyShares British Pound ETF', FXA:'Invesco CurrencyShares Australian Dollar ETF',
  FXC:'Invesco CurrencyShares Canadian Dollar ETF', FXF:'Invesco CurrencyShares Swiss Franc ETF',
  UUP:'Invesco DB US Dollar Bullish ETF', UDN:'Invesco DB US Dollar Bearish ETF',
  CEW:'WisdomTree Emerging Currency Strategy ETF', USDU:'WisdomTree Bloomberg US Dollar Bullish ETF',
  // Commodities ETFs
  GLD:'SPDR Gold Shares ETF', IAU:'iShares Gold Trust', GDX:'VanEck Gold Miners ETF',
  GDXJ:'VanEck Junior Gold Miners ETF', SGOL:'Aberdeen Physical Gold ETF',
  SLV:'iShares Silver Trust', PSLV:'Sprott Physical Silver Trust', SIL:'Global X Silver Miners ETF',
  USO:'United States Oil Fund', XOP:'SPDR S&P Oil & Gas E&P ETF', OIH:'VanEck Oil Services ETF',
  UNG:'United States Natural Gas Fund', AMLP:'Alerian MLP ETF',
  DBA:'Invesco Agriculture ETF', CORN:'Teucrium Corn ETF', WEAT:'Teucrium Wheat ETF',
  SOYB:'Teucrium Soybean ETF', MOO:'VanEck Agribusiness ETF', COW:'iPath Bloomberg Livestock ETN',
  GSG:'iShares S&P GSCI Commodity ETF', PDBC:'Invesco Optimum Yield Diversified Commodity ETF',
  COM:'Direxion Auspice Broad Commodity ETF', DJP:'iPath Bloomberg Commodity Index ETN',
  COMT:'iShares MSCI Global Commodity Producers ETF',
  CPER:'United States Copper Index ETF', COPX:'Global X Copper Miners ETF',
  DBB:'Invesco DB Base Metals ETF', PICK:'iShares MSCI Global Metals & Mining ETF',
  URA:'Global X Uranium ETF', URNM:'Sprott Uranium Miners ETF',
  BATT:'Amplify Lithium & Battery Technology ETF',
  XME:'SPDR S&P Metals & Mining ETF', REMX:'VanEck Rare Earth/Strategic Metals ETF',
  // Individual Commodities / Miners
  FCX:'Freeport-McMoRan Inc', NEM:'Newmont Corporation', GOLD:'Barrick Gold Corporation',
  BHP:'BHP Group', RIO:'Rio Tinto', AA:'Alcoa Corporation', CLF:'Cleveland-Cliffs Inc',
  VALE:'Vale S.A.', MOS:'The Mosaic Company', NTR:'Nutrien Ltd',
  // Mega-cap Tech & Growth
  AAPL:'Apple Inc', MSFT:'Microsoft Corporation', NVDA:'NVIDIA Corporation',
  AMZN:'Amazon.com Inc', GOOGL:'Alphabet Inc', META:'Meta Platforms Inc',
  TSLA:'Tesla Inc', 'BRK.B':'Berkshire Hathaway B',
  // Financials
  JPM:'JPMorgan Chase & Co', V:'Visa Inc', MA:'Mastercard Inc',
  GS:'Goldman Sachs Group', MS:'Morgan Stanley', C:'Citigroup Inc',
  BAC:'Bank of America', WFC:'Wells Fargo & Co', SCHW:'Charles Schwab Corp',
  // Healthcare & Pharma
  JNJ:'Johnson & Johnson', UNH:'UnitedHealth Group', LLY:'Eli Lilly and Company',
  ABBV:'AbbVie Inc', MRK:'Merck & Co', TMO:'Thermo Fisher Scientific',
  // Consumer
  WMT:'Walmart Inc', PG:'Procter & Gamble', PEP:'PepsiCo Inc', KO:'The Coca-Cola Company',
  COST:'Costco Wholesale', MCD:"McDonald's Corporation", NKE:'Nike Inc',
  // Industrial & Energy
  XOM:'Exxon Mobil Corporation', CVX:'Chevron Corporation', HD:'Home Depot Inc',
  BA:'Boeing Company', CAT:'Caterpillar Inc', DE:'Deere & Company',
  GE:'GE Aerospace', UPS:'United Parcel Service', RTX:'RTX Corporation', LMT:'Lockheed Martin',
  // Tech
  AVGO:'Broadcom Inc', ADBE:'Adobe Inc', CRM:'Salesforce Inc', ACN:'Accenture PLC',
  CSCO:'Cisco Systems', AMD:'Advanced Micro Devices', INTC:'Intel Corporation',
  QCOM:'Qualcomm Inc', TXN:'Texas Instruments', NFLX:'Netflix Inc',
  ORCL:'Oracle Corporation', PLTR:'Palantir Technologies', SNOW:'Snowflake Inc',
  // Growth / New Tech
  UBER:'Uber Technologies', ABNB:'Airbnb Inc', SQ:'Block Inc',
  SHOP:'Shopify Inc', COIN:'Coinbase Global', MSTR:'Strategy Inc',
  RIVN:'Rivian Automotive', LCID:'Lucid Group',
  // Financials & Insurance
  MET:'MetLife Inc', AIG:'American International Group', PRU:'Prudential Financial',
  // Transport
  DAL:'Delta Air Lines', UAL:'United Airlines Holdings', AAL:'American Airlines Group',
  // Energy / Utilities
  DVN:'Devon Energy', OXY:'Occidental Petroleum', MPC:'Marathon Petroleum',
  VST:'Vistra Corp', NEE:'NextEra Energy', DUK:'Duke Energy',
  // Crypto (Alpaca format)
  'BTC/USD':'Bitcoin', 'ETH/USD':'Ethereum', 'SOL/USD':'Solana', 'ADA/USD':'Cardano',
  'XRP/USD':'XRP', 'DOT/USD':'Polkadot', 'LTC/USD':'Litecoin', 'AVAX/USD':'Avalanche',
  'AAVE/USD':'Aave', 'UNI/USD':'Uniswap', 'SUSHI/USD':'SushiSwap', 'CRV/USD':'Curve DAO',
  'LDO/USD':'Lido DAO', 'LINK/USD':'Chainlink', 'GRT/USD':'The Graph',
  'DOGE/USD':'Dogecoin', 'SHIB/USD':'Shiba Inu', 'PEPE/USD':'Pepe',
  'BONK/USD':'Bonk', 'WIF/USD':'dogwifhat', 'TRUMP/USD':'Official Trump',
  'FIL/USD':'Filecoin', 'RENDER/USD':'Render', 'ARB/USD':'Arbitrum',
  'ONDO/USD':'Ondo Finance', 'POL/USD':'Polygon', 'BAT/USD':'Basic Attention Token',
  'BCH/USD':'Bitcoin Cash', 'HYPE/USD':'Hyperliquid', 'PAXG/USD':'PAX Gold',
  'SKY/USD':'Sky', 'XTZ/USD':'Tezos', 'YFI/USD':'Yearn Finance',
};

/** Return "TICKER (Full Name)" or just "TICKER" if unknown */
function tickerDisplay(symbol) {
  if (!symbol) return '';
  var name = TICKER_NAMES[symbol];
  return name ? symbol + ' <span class="ticker-name">(' + escapeHtml(name) + ')</span>' : escapeHtml(symbol);
}

/**
 * Strip raw TradeProposal JSON blob from thesis/reasoning strings.
 * If the text is a JSON blob like {"trades":[{"symbol":"X","reasoning":"..."}]},
 * extract the human-readable reasoning for the given symbol (or the first trade).
 */
function cleanThesis(text, symbol) {
  if (!text) return '';
  text = String(text).trim();
  if (text.charAt(0) !== '{') return text; // fast path — not JSON
  try {
    var proposal = JSON.parse(text);
    var trades = proposal.trades || [];
    // prefer matching symbol, fall back to first trade
    var match = null;
    for (var i = 0; i < trades.length; i++) {
      if (!symbol || trades[i].symbol === symbol) { match = trades[i]; break; }
    }
    if (!match && trades.length) match = trades[0];
    return match ? (match.reasoning || match.thesis || text) : text;
  } catch(e) { return text; }
}

// ─── 1. Clock ─────────────────────────────────────────────────────────────
function tick() {
  document.getElementById('clock').textContent =
    new Date().toISOString().replace('T',' ').slice(0,19) + ' UTC';
}
tick(); setInterval(tick, 1000);

// ─── 2. Signal History Persistence (localStorage, 7-day rolling) ────────────
const HISTORY_STORAGE_KEY = 'aghf_signal_history';
const HISTORY_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function loadSignalHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const cutoff = new Date(Date.now() - HISTORY_MAX_AGE_MS).toISOString();
    return parsed.filter(e => e && e.ts && Array.isArray(e.signals) && e.ts >= cutoff);
  } catch(e) { return []; }
}

function saveSignalHistory() {
  try {
    const cutoff = new Date(Date.now() - HISTORY_MAX_AGE_MS).toISOString();
    const trimmed = signalHistory.filter(e => e.ts >= cutoff);
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
  } catch(e) {}
}

var signalHistory = loadSignalHistory();

// ─── 2b. Session Status ──────────────────────────────────────────────────
var sessionActive = false;

function updateSessionStatus(active) {
  sessionActive = active;
  var dot = document.getElementById('session-dot');
  var lbl = document.getElementById('session-label');
  var btn = document.getElementById('session-btn');
  if (!dot || !lbl || !btn) return;
  dot.classList.toggle('on', active);
  lbl.classList.toggle('on', active);
  lbl.textContent = active ? 'ACTIVE' : 'IDLE';
  btn.textContent = active ? 'STOP' : 'START';
  btn.className = active ? 'sb-btn sb-btn-stop' : 'sb-btn sb-btn-start';
}

function toggleSession() {
  if (sessionActive) {
    if (!confirm('Stop the trading session? All pods will be halted.')) return;
    fetch('/api/session/stop', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(d) { if (d.ok) updateSessionStatus(false); })
      .catch(function(e) { console.error('stop failed', e); });
  } else {
    fetch('/api/session/start', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(d) { if (d.ok) updateSessionStatus(true); })
      .catch(function(e) { console.error('start failed', e); });
  }
}

(function pollSessionStatus() {
  fetch('/api/session/status')
    .then(function(r) { return r.json(); })
    .then(function(d) { updateSessionStatus(!!d.active); })
    .catch(function() {});
})();

// ─── Reports Dropdown ────────────────────────────────────────────────────
function toggleReportsDropdown() {
  var dd = document.getElementById('reports-dropdown');
  if (!dd) return;
  var isOpen = dd.classList.contains('open');
  if (isOpen) {
    dd.classList.remove('open');
  } else {
    dd.classList.add('open');
    fetchReports();
  }
}

document.addEventListener('click', function(e) {
  var wrap = document.querySelector('.sb-reports-wrap');
  var dd = document.getElementById('reports-dropdown');
  if (wrap && dd && !wrap.contains(e.target)) {
    dd.classList.remove('open');
  }
});

function fetchReports() {
  var list = document.getElementById('reports-list');
  if (!list) return;
  fetch('/api/reports')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var reports = data.reports || [];
      if (reports.length === 0) {
        list.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim)">No reports generated yet</div>';
        return;
      }
      list.innerHTML = reports.map(function(r) {
        return '<div class="report-item" onclick="window.open(\'/api/reports/' + r.filename + '\')">' +
          '<div><span class="report-item-date">' + r.date + '</span>' +
          '<span class="report-item-size">' + r.size_kb + ' KB</span></div>' +
          '<a class="report-item-dl" href="/api/reports/' + r.filename + '" target="_blank" onclick="event.stopPropagation()">DOWNLOAD</a>' +
          '</div>';
      }).join('');
    })
    .catch(function() {
      list.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim)">Failed to load reports</div>';
    });
}

function onNewReport(filename) {
  var btn = document.getElementById('reports-btn');
  if (btn) {
    btn.classList.add('has-new');
    setTimeout(function() { btn.classList.remove('has-new'); }, 5000);
  }
  var dd = document.getElementById('reports-dropdown');
  if (dd && dd.classList.contains('open')) {
    fetchReports();
  }
}

// ─── 3. Tab Switching ─────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'execution') fetchClosedTrades();
    if (btn.dataset.tab === 'closed') loadClosedPositions();
  });
});

function switchResearchSubTab(name) {
  document.querySelectorAll('.sub-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.subtab === name);
  });
  document.querySelectorAll('.sub-tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'subtab-' + name);
  });
  if (name === 'historical' && researchHistoryChart) {
    researchHistoryChart.resize();
  }
}
document.querySelectorAll('.sub-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchResearchSubTab(btn.dataset.subtab));
});

// ─── 4. WebSocket ────────────────────────────────────────────────────────
const WS_URL = `ws://${window.location.host}/ws`;
var ws = null;

function setConn(on) {
  const dot = document.getElementById('conn-dot');
  const lbl = document.getElementById('conn-label');
  dot.classList.toggle('on', on);
  lbl.classList.toggle('on', on);
  lbl.textContent = on ? 'CONNECTED' : 'DISCONNECTED';
}

function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => setConn(true);
  ws.onclose = () => { setConn(false); setTimeout(connect, 3000); };
  ws.onerror = () => ws.close();
  ws.onmessage = ev => { try { handleMessage(JSON.parse(ev.data)); } catch(e) { console.error(e); } };
}
connect();

// ─── 5. Research Tab Helpers ──────────────────────────────────────────────
function formatPct(v) {
  if (v == null) return '—';
  return (v * 100).toFixed(1) + '%';
}

function formatVol(v) {
  if (v == null || v === 0) return '—';
  return '$' + (v / 1_000_000).toFixed(1) + 'M';
}

function formatTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleTimeString('en-GB', { hour12: false });
}

function truncate(str, n) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function formatEndDate(d) {
  if (!d) return '—';
  const dt = typeof d === 'string' ? new Date(d) : d;
  return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatDelta(curr, prev) {
  if (curr == null || prev == null) return '—';
  const d = (curr - prev) * 100;
  const s = d >= 0 ? '+' : '';
  return s + d.toFixed(1) + 'pp';
}

function statusBadge(status) {
  if (!status) return '<span class="status-pill active">Active</span>';
  const s = String(status).toUpperCase();
  const cls = s === 'ACTIVE' ? 'active' : s === 'HALTED' ? 'halted' : s === 'CLOSED' ? 'closed' : 'idle';
  return '<span class="status-pill ' + cls + '">' + escapeHtml(s) + '</span>';
}

// escapeHtml defined below (line 2547 declaration wins due to hoisting)

function updateRegimeBadge(regimeLabel) {
  var badge = document.getElementById('regime-badge');
  if (!badge) return;
  // Map label to CSS class suffix: "Risk-On" -> "risk-on", "Risk-Off" -> "risk-off", "Neutral" -> "neutral", "Crisis" -> "crisis"
  var cls = regimeLabel.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z-]/g, '');
  badge.className = 'regime-badge regime-' + cls;
  badge.textContent = regimeLabel.toUpperCase();
  badge.title = 'Market regime: ' + regimeLabel + ' — updates each cycle';
}

function renderCurrentMarkets(signals) {
  const tbody = document.getElementById('current-markets-body');
  const countEl = document.getElementById('market-count');
  const timeEl = document.getElementById('last-fetch-time');
  if (!tbody) return;

  const now = new Date();
  signals = signals.filter(function(s) {
    if (s.status && String(s.status).toLowerCase() === 'resolved') return false;
    if (s.end_date) {
      var end = typeof s.end_date === 'string' ? new Date(s.end_date) : s.end_date;
      if (end < now) return false;
    }
    return true;
  });

  document.getElementById('kpi-market-count').textContent = signals.length || '—';
  const avgProb = signals.length
    ? (signals.reduce((s, x) => s + (x.implied_prob || 0), 0) / signals.length)
    : null;
  document.getElementById('kpi-avg-prob').textContent = formatPct(avgProb);

  if (countEl) countEl.textContent = signals.length;
  if (timeEl && signals.length) {
    const ts = signals[0].timestamp;
    timeEl.textContent = typeof ts === 'string' ? formatTime(ts) : formatTime(ts && ts.toISOString ? ts.toISOString() : ts);
  }

  if (!signals.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="8">No Polymarket data — check POLYMARKET_API_KEY in .env</td></tr>';
    return;
  }

  const prevByMarket = {};
  if (signalHistory.length) {
    const last = signalHistory[signalHistory.length - 1].signals || [];
    last.forEach(s => { prevByMarket[s.market_id || s.question] = s.implied_prob; });
  }

  tbody.innerHTML = signals.map(s => {
    const q = s.question || s.market || JSON.stringify(s);
    const prevProb = prevByMarket[s.market_id || q];
    const delta = formatDelta(s.implied_prob, prevProb);
    return '<tr title="' + escapeHtml(q).replace(/"/g, '&quot;') + '">' +
      '<td>' + truncate(q, 40) + '</td>' +
      '<td class="num">' + statusBadge(s.status || 'Active') + '</td>' +
      '<td class="num">' + (s.yes_price != null ? s.yes_price.toFixed(2) : '—') + '</td>' +
      '<td class="num">' + (s.no_price != null ? s.no_price.toFixed(2) : '—') + '</td>' +
      '<td class="num accent">' + formatPct(s.implied_prob) + '</td>' +
      '<td class="num">' + delta + '</td>' +
      '<td class="num">' + formatVol(s.volume_24h) + '</td>' +
      '<td class="num">' + formatEndDate(s.end_date) + '</td>' +
      '</tr>';
  }).join('');
}

const COLORS = ['#00cfe8', '#f0a030', '#00c888', '#7c5cfc', '#e84040'];
const MAX_MARKETS = 5;
const BUCKET_MS = 4 * 60 * 60 * 1000;
const WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

function initResearchHistoryChart() {
  const ctx = document.getElementById('research-history-chart');
  if (!ctx || researchHistoryChart) return;

  researchHistoryChart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          labels: {
            color: '#6a90aa',
            font: { family: 'IBM Plex Mono', size: 9 },
            boxWidth: 12,
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#3a556a', font: { size: 9 } },
          grid: { color: '#1c2c3c' }
        },
        y: {
          min: 0, max: 100,
          ticks: {
            color: '#3a556a',
            font: { size: 9 },
            callback: v => v + '%'
          },
          grid: { color: '#1c2c3c' }
        }
      }
    }
  });
}

function updateHistoricalChart() {
  if (!researchHistoryChart) initResearchHistoryChart();
  if (!researchHistoryChart) return;

  const cutoff = Date.now() - WINDOW_MS;
  const bucketed = {};
  signalHistory.forEach(e => {
    const ts = new Date(e.ts).getTime();
    if (ts < cutoff) return;
    const bucket = Math.floor(ts / BUCKET_MS) * BUCKET_MS;
    if (!bucketed[bucket]) bucketed[bucket] = { ts: bucket, signals: [] };
    bucketed[bucket].signals = e.signals || [];
  });

  const buckets = Object.keys(bucketed).map(Number).sort((a, b) => a - b);
  const latestSignals = buckets.length
    ? [...(bucketed[buckets[buckets.length - 1]].signals || [])]
        .sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0))
        .slice(0, MAX_MARKETS)
    : [];

  const topIds = latestSignals.map(s => s.market_id || s.question || JSON.stringify(s));
  const labels = buckets.map(b => new Date(b).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }));

  const datasets = topIds.map((id, i) => {
    const market = latestSignals[i];
    const data = buckets.map(b => {
      const entry = bucketed[b];
      const sig = (entry && entry.signals) ? entry.signals.find(s => (s.market_id || s.question) === id) : null;
      return sig ? parseFloat((sig.implied_prob * 100).toFixed(1)) : null;
    });
    return {
      label: truncate(market && market.question, 25),
      data,
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 2,
      tension: 0.3,
      spanGaps: true,
    };
  });

  researchHistoryChart.data.labels = labels;
  researchHistoryChart.data.datasets = datasets;
  researchHistoryChart.update();

  const countEl = document.getElementById('history-data-count');
  if (countEl) countEl.textContent = signalHistory.length;
}

function renderHistoryTable() {
  const tbody = document.getElementById('history-body');
  if (!tbody) return;

  if (!signalHistory.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="3">No history yet — waiting for first cycle</td></tr>';
    return;
  }

  const rows = [];
  const recent = signalHistory.slice(-10).reverse();
  recent.forEach(entry => {
    const top5 = [...(entry.signals || [])]
      .sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0))
      .slice(0, 5);
    top5.forEach((sig, i) => {
      rows.push('<tr>' +
        '<td class="num">' + (i === 0 ? formatTime(entry.ts) : '') + '</td>' +
        '<td>' + truncate(sig.question, 35) + '</td>' +
        '<td class="num accent">' + formatPct(sig.implied_prob) + '</td>' +
        '</tr>');
    });
    rows.push('<tr style="height:4px"><td colspan="3" style="border-bottom:1px solid var(--border-dim)"></td></tr>');
  });

  tbody.innerHTML = rows.join('');
}

function renderContributors(signals, confidence, macroScore, momentum) {
  const confEl = document.getElementById('kpi-macro-conf');
  const scoreEl = document.getElementById('kpi-macro-score');
  if (confEl) confEl.textContent = formatPct(confidence);
  if (scoreEl) scoreEl.textContent = macroScore != null ? macroScore.toFixed(3) : '—';

  const scPoly = document.getElementById('sc-poly-val');
  const scFred = document.getElementById('sc-fred-val');
  const scSocial = document.getElementById('sc-social-val');
  const scBlend = document.getElementById('sc-blend-val');
  if (scPoly) scPoly.textContent = (researchPolySentiment != null ? researchPolySentiment.toFixed(3) : '—');
  if (scFred) scFred.textContent = (researchFredScore != null ? researchFredScore.toFixed(3) : '—');
  if (scSocial) scSocial.textContent = (researchSocialScore != null ? researchSocialScore.toFixed(3) : '—');
  if (scBlend) scBlend.textContent = macroScore != null ? macroScore.toFixed(3) : '—';

  const confValEl = document.getElementById('calc-confidence');
  const resultEl = document.getElementById('calc-result');
  const marketCtEl = document.getElementById('calc-market-ct');
  const totalVolEl = document.getElementById('calc-total-vol');
  if (confValEl) confValEl.textContent = formatPct(confidence);
  if (resultEl) resultEl.textContent = macroScore != null ? macroScore.toFixed(3) : '—';
  if (marketCtEl) marketCtEl.textContent = signals.length;
  const totalVol = signals.reduce((s, x) => s + (x.volume_24h || 0), 0);
  if (totalVolEl) totalVolEl.textContent = formatVol(totalVol);

  const countEl = document.getElementById('contrib-count');
  const avgEl = document.getElementById('contrib-avg');
  const sentEl = document.getElementById('contrib-sentiment');
  if (countEl) countEl.textContent = signals.length;
  if (avgEl) avgEl.textContent = formatPct(confidence);
  if (sentEl) sentEl.textContent = researchPolySentiment != null ? researchPolySentiment.toFixed(3) : '—';

  const tbody = document.getElementById('contributors-body');
  if (!tbody) return;

  if (!signals.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No Polymarket signals this cycle — macro_confidence defaulted to 0.50</td></tr>';
    return;
  }

  const totalV = signals.reduce((s, x) => s + (x.volume_24h || 0), 0) || 1;
  const sorted = [...signals].sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0));

  tbody.innerHTML = sorted.map((sig, i) => {
    const prob = sig.implied_prob || 0;
    const barPct = (prob * 100).toFixed(1);
    const vol = sig.volume_24h || 0;
    const weight = totalV > 0 ? (vol / totalV * 100).toFixed(1) + '%' : '—';
    const contrib = (prob * (vol / totalV) * 100).toFixed(2) + '%';
    const isTop = i < 3;
    return '<tr class="' + (isTop ? 'top-contributor' : '') + '">' +
      '<td title="' + escapeHtml(sig.question || '').replace(/"/g, '&quot;') + '">' + truncate(sig.question, 42) + '</td>' +
      '<td class="num accent">' + formatPct(prob) + '</td>' +
      '<td class="num">' + formatVol(vol) + '</td>' +
      '<td>' +
      '<div class="contrib-bar-wrap"><div class="contrib-bar" style="width:' + barPct + '%"></div></div>' +
      '</td>' +
      '<td class="num">' + contrib + '</td>' +
      '</tr>';
  }).join('');
}

const FRED_INDICATORS = [
  { key: 'DFF', label: 'FED FUNDS RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'DGS2', label: '2Y TREASURY', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'DGS10', label: '10Y TREASURY', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'DGS30', label: '30Y TREASURY', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'T10Y2Y', label: 'YIELD CURVE 10Y-2Y', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: v => v != null && v < 0 ? 'bearish' : 'neutral' },
  { key: 'T10Y3M', label: 'YIELD CURVE 10Y-3M', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: v => v != null && v < 0 ? 'bearish' : 'neutral' },
  { key: 'MORTGAGE30US', label: '30Y MORTGAGE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'T5YIE', label: '5Y BREAKEVEN', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'T10YIE', label: '10Y BREAKEVEN', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'CPIAUCSL', label: 'CPI', fmt: v => v != null ? v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'PCEPILFE', label: 'CORE PCE', fmt: v => v != null ? v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'VIXCLS', label: 'CBOE VIX', fmt: v => v != null ? v.toFixed(1) : '—', status: v => v != null && v > 25 ? 'bearish' : v != null && v < 15 ? 'bullish' : 'neutral' },
  { key: 'BAMLH0A0HYM2', label: 'HY CREDIT SPREAD', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: v => v != null && v > 5 ? 'bearish' : 'neutral' },
  { key: 'NFCI', label: 'NFCI', fmt: v => v != null ? v.toFixed(2) : '—', status: v => v != null && v > 0 ? 'bearish' : 'neutral' },
  { key: 'UNRATE', label: 'UNEMPLOYMENT', fmt: v => v != null ? v.toFixed(1) + '%' : '—', status: () => 'neutral' },
  { key: 'ICSA', label: 'INITIAL CLAIMS', fmt: v => v != null ? (v / 1000).toFixed(1) + 'K' : '—', status: () => 'neutral' },
  { key: 'INDPRO', label: 'INDUSTRIAL PROD', fmt: v => v != null ? v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'RSAFS', label: 'RETAIL SALES', fmt: v => v != null ? '$' + (v / 1000).toFixed(0) + 'B' : '—', status: () => 'neutral' },
  { key: 'UMCSENT', label: 'CONSUMER SENTIMENT', fmt: v => v != null ? v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'DCOILWTICO', label: 'WTI CRUDE OIL', fmt: v => v != null ? '$' + v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'DTWEXBGS', label: 'USD INDEX', fmt: v => v != null ? v.toFixed(1) : '—', status: () => 'neutral' },
  { key: 'M2SL', label: 'M2 MONEY SUPPLY', fmt: v => v != null ? '$' + (v / 1000).toFixed(0) + 'T' : '—', status: () => 'neutral' },
  { key: 'WALCL', label: 'FED BALANCE SHEET', fmt: v => v != null ? '$' + (v / 1e6).toFixed(0) + 'T' : '—', status: () => 'neutral' },
  { key: 'ECBMRRFR', label: 'ECB MAIN REFI', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'ECBDFR', label: 'ECB DEPOSIT', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'IRSTCI01GBM156N', label: 'BOE RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'IRSTCB01JPM156N', label: 'BOJ RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'IRSTCI01AUM156N', label: 'RBA RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'IRSTCB01CAM156N', label: 'BOC RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
  { key: 'IRSTCI01CHM156N', label: 'SNB RATE', fmt: v => v != null ? v.toFixed(2) + '%' : '—', status: () => 'neutral' },
];

function renderMacroIndicators() {
  const snap = researchFredSnapshot || {};
  let lastTs = null;
  FRED_INDICATORS.forEach(ind => {
    const valEl = document.getElementById('val-' + ind.key);
    const dotEl = document.getElementById('dot-' + ind.key);
    const v = snap[ind.key];
    if (valEl) valEl.textContent = ind.fmt(v);
    if (dotEl) {
      dotEl.className = 'ic-dot ' + (typeof ind.status === 'function' ? ind.status(v) : 'neutral');
    }
  });
  const updateEl = document.getElementById('fred-update-time');
  if (updateEl) updateEl.textContent = lastTs ? formatTime(lastTs) : (Object.keys(snap).length ? 'Just now' : '—');

  const scoreEl = document.getElementById('fc-score-val');
  if (scoreEl) scoreEl.textContent = researchFredScore != null ? researchFredScore.toFixed(3) : '—';

  const gaugeFill = document.getElementById('gauge-fill');
  const gaugeMarker = document.getElementById('gauge-marker');
  if (gaugeFill && gaugeMarker && researchFredScore != null) {
    const pct = Math.max(0, Math.min(100, (researchFredScore + 1) * 50));
    gaugeFill.style.left = '0%';
    gaugeFill.style.width = pct + '%';
    gaugeMarker.style.left = pct + '%';
  }
}

function updateVixKpi() {
  const vix = researchFredSnapshot && researchFredSnapshot.VIXCLS;
  const el = document.getElementById('kpi-vix');
  if (el) el.textContent = vix != null ? vix.toFixed(1) : '—';
}

function formatRelativeTime(ts) {
  if (!ts) return '—';
  const d = typeof ts === 'string' ? new Date(ts) : ts;
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
  return Math.floor(diff / 86400000) + 'd ago';
}

function createNewsCard(item) {
  const text = item.text || item.title || item.headline || '';
  const url = item.url || '#';
  const source = item.handle || item.username || item.source || 'news';
  const ts = item.timestamp || item.published;
  const sent = item.sentiment;
  const cat = item.category || 'Markets';
  const sentClass = sent != null && sent > 0.1 ? 'bullish' : sent != null && sent < -0.1 ? 'bearish' : 'neutral';
  return '<div class="news-card">' +
    '<div class="nc-meta">' +
    '<span class="nc-cat">' + escapeHtml(cat) + '</span>' +
    '<span class="nc-dot ' + sentClass + '"></span>' +
    '<span class="nc-time">' + formatRelativeTime(ts) + '</span>' +
    '</div>' +
    '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener" class="nc-title">' + escapeHtml(truncate(text, 80)) + '</a>' +
    '<div class="nc-source">' + escapeHtml(source) + '</div>' +
    '</div>';
}

function renderNewsFeed() {
  const container = document.getElementById('social-feed-container');
  const emptyEl = document.getElementById('social-empty-state');
  const sentimentEl = document.getElementById('social-sentiment-val');
  const countEl = document.getElementById('social-tweet-count');
  const sourcesEl = document.getElementById('social-sources-count');
  const refreshEl = document.getElementById('social-last-refresh');
  const badgeEl = document.getElementById('social-badge');

  const feed = researchXFeed || [];
  const count = researchXTweetCount != null ? researchXTweetCount : feed.length;
  const sentiment = researchSocialScore != null ? researchSocialScore.toFixed(3) : '—';

  if (sentimentEl) sentimentEl.textContent = sentiment;
  if (countEl) countEl.textContent = count;
  if (sourcesEl) sourcesEl.textContent = feed.length ? feed.length + '/25' : '0/25';
  if (refreshEl) refreshEl.textContent = newsLastRefresh ? formatRelativeTime(newsLastRefresh) : '—';
  if (badgeEl) badgeEl.textContent = count > 0 ? count : '';

  if (!container) return;

  if (!feed.length) {
    if (emptyEl) emptyEl.style.display = 'block';
    const wrap = container.querySelector('.news-feed-wrap');
    if (wrap) wrap.innerHTML = '';
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';
  let wrap = container.querySelector('.news-feed-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.className = 'news-feed-wrap';
    container.appendChild(wrap);
  }
  wrap.innerHTML = feed.slice(0, 100).map(createNewsCard).join('');
}

function updateResearchTab(signals, confidence, macroScore) {
  researchSignals = signals || [];
  researchPolyConf = confidence != null ? confidence : 0.5;
  researchMacroScore = macroScore;

  if (researchSignals.length > 0) {
    signalHistory.push({ ts: new Date().toISOString(), signals: researchSignals });
    const cutoff = new Date(Date.now() - HISTORY_MAX_AGE_MS).toISOString();
    signalHistory = signalHistory.filter(e => e.ts >= cutoff);
    if (signalHistory.length > MAX_HISTORY) signalHistory = signalHistory.slice(-MAX_HISTORY);
    saveSignalHistory();
  }

  renderCurrentMarkets(researchSignals);
  updateHistoricalChart();
  renderHistoryTable();
  renderContributors(researchSignals, researchPolyConf, researchMacroScore, researchMomentum);
  renderMacroIndicators();
  updateVixKpi();
  renderNewsFeed();
}

// ─── 6. Message Handler ───────────────────────────────────────────────────
function handleMessage(msg) {
  if (msg.type === 'session_snapshot') {
    var snap = msg.data || {};
    if (snap.iteration) iterCount = snap.iteration;
    document.getElementById('iter-ctr').textContent = iterCount || '—';
    if (snap.session_active !== undefined) updateSessionStatus(!!snap.session_active);
    var podSums = snap.pod_summaries || {};
    for (var pid in podSums) {
      var m = podSums[pid];
      if (m && m.data) {
        pods[m.pod_id || pid] = Object.assign(pods[m.pod_id || pid] || {}, m.data);
      }
      var pData = (m && m.data) ? m.data : m;
      if (pData) {
        if (pData.fred_snapshot) {
          researchFredSnapshot = Object.assign(researchFredSnapshot || {}, pData.fred_snapshot);
        }
        if (pData.fred_score !== undefined) researchFredScore = pData.fred_score || 0;
        if (pData.poly_sentiment !== undefined) researchPolySentiment = pData.poly_sentiment || 0;
        if (pData.social_score !== undefined) researchSocialScore = pData.social_score || 0;
        if (pData.macro_score !== undefined) researchMacroScore = pData.macro_score;
        if (pData.polymarket_signals && pData.polymarket_signals.length > 0) {
          if (!window._allPolySignals) window._allPolySignals = {};
          window._allPolySignals[pid] = pData.polymarket_signals;
        }
        if (pData.x_feed && pData.x_feed.length > 0) {
          researchXFeed = (researchXFeed || []).concat(pData.x_feed);
        }
      }
    }
    // Seed sparklines from snapshot so trend column isn't empty on connect
    for (var spid in pods) {
      var spNav = getPodNav(pods[spid]);
      if (spNav > 0) {
        if (!podNavSpark[spid]) podNavSpark[spid] = [];
        if (podNavSpark[spid].length === 0) podNavSpark[spid].push(spNav, spNav);
      }
    }
    (snap.recent_trades || []).forEach(function(t) {
      if (t.data && t.data.symbol && t.data.side && t.data.qty) {
        var oid = t.data.order_id || t.data.id || null;
        addTrade(t.data.pod_id || 'unknown', t.data.symbol, t.data.side, t.data.qty, t.data.fill_price || 0, 'FILLED', oid);
      }
    });
    (snap.recent_governance || []).forEach(function(g) {
      if (g.data && g.data.agent && g.data.decision) {
        recordGov(g.data.agent, g.data.decision, g.data.reasoning || '', g.data.weights || null);
      }
    });
    (snap.recent_activity || []).forEach(function(a) {
      if (a.data) {
        var act = a.data;
        if (!agentActivity[act.agent_id]) agentActivity[act.agent_id] = [];
        agentActivity[act.agent_id].unshift(act);
        if (agentActivity[act.agent_id].length > 5) agentActivity[act.agent_id].pop();
        activityFeed.unshift({ agent_id: act.agent_id, agent_role: act.agent_role, pod_id: act.pod_id, action: act.action, summary: act.summary, detail: act.detail, urls: act.urls, ts: a.timestamp });
      }
    });
    if (activityFeed.length > 50) activityFeed = activityFeed.slice(0, 50);
    (snap.recent_orders || []).forEach(function(o) {
      if (o.data && o.data.order_id) orderBook[o.data.order_id] = o.data;
    });
    (snap.position_reviews || []).forEach(function(rv) {
      addReviewEvent(rv);
    });
    updateExecTable();
    updatePodsTable();
    updateFirmMetrics();
    updatePerfTable();
    calculateRisk();
    updateRiskTable();
    fetchPositionsFromApi();
    updateTopHoldings();
    updateActivityFeed();
    updateDecisionTimeline();
    updateGovHub();
    renderMacroIndicators();
    updateVixKpi();
    var mergedPoly = [];
    if (window._allPolySignals) {
      var seenQ = {};
      for (var pkey in window._allPolySignals) {
        (window._allPolySignals[pkey] || []).forEach(function(s) {
          var q = s.question || s.market || JSON.stringify(s);
          if (!seenQ[q]) { seenQ[q] = true; mergedPoly.push(s); }
        });
      }
    }
    updateResearchTab(mergedPoly, researchPolyConf, researchMacroScore);
    return;
  }
  if (msg.type === 'session_status') {
    var sd = msg.data || {};
    updateSessionStatus(!!sd.active);
    if (sd.iteration != null) {
      iterCount = sd.iteration;
      document.getElementById('iter-ctr').textContent = iterCount;
    }
    return;
  }
  if (msg.type === 'pod_summary' || msg.type === 'pod_enrichment') {
    const data = msg.data;
    const pod_id = msg.pod_id || data.pod_id;
    if (pod_id) {
      if (msg.type === 'pod_summary') {
      pods[pod_id] = Object.assign(pods[pod_id] || {}, data);
        if (data.performance_metrics && Object.keys(data.performance_metrics).length > 0) {
          pods[pod_id].performance_metrics = data.performance_metrics;
        }
        if (data.trade_outcome_stats && data.trade_outcome_stats.total_trades > 0) {
          pods[pod_id].trade_outcome_stats = data.trade_outcome_stats;
          renderOutcomeStats();
        }
        var ptsEl = document.getElementById('price-ts');
        if (ptsEl) ptsEl.textContent = new Date().toLocaleTimeString();
        if (data.macro_regime) updateRegimeBadge(data.macro_regime);
      } else {
        // Enrichment: only merge research keys, never clobber core metrics
        if (!pods[pod_id]) pods[pod_id] = {};
        // Handle headline_alert events routed through pod gateway
        if (data.type === 'headline_alert') {
          var alertSym = data.symbol;
          if (alertSym) {
            if (!_symbolAlerts[alertSym]) _symbolAlerts[alertSym] = [];
            _symbolAlerts[alertSym].unshift({
              headline: data.headline || '',
              sentiment: data.sentiment || 0,
              ts: new Date().toISOString(),
              pod_id: data.pod_id || pod_id || ''
            });
            if (_symbolAlerts[alertSym].length > 3) _symbolAlerts[alertSym] = _symbolAlerts[alertSym].slice(0, 3);
            updateTopHoldings();
            addFeedEntry({
              type: 'headline_alert',
              pod_id: data.pod_id || pod_id,
              detail: data.detail || data.headline,
              summary: data.summary || ('Alert: ' + alertSym),
              ts: new Date().toISOString()
            });
          }
          return;
        }
        var enrichKeys = ['polymarket_signals','polymarket_confidence','macro_score','fred_snapshot','fred_score','poly_sentiment','social_score','x_feed','x_tweet_count','news_last_refresh','features','pod_id'];
        for (var ek = 0; ek < enrichKeys.length; ek++) {
          if (data[enrichKeys[ek]] !== undefined) pods[pod_id][enrichKeys[ek]] = data[enrichKeys[ek]];
        }
      }

      if (data.polymarket_signals !== undefined || data.fred_snapshot !== undefined || data.x_feed !== undefined) {
        if (data.fred_snapshot !== undefined) {
          researchFredSnapshot = Object.assign(researchFredSnapshot || {}, data.fred_snapshot || {});
        }
        if (data.fred_score !== undefined) researchFredScore = data.fred_score || 0;
        if (data.poly_sentiment !== undefined) researchPolySentiment = data.poly_sentiment || 0;
        if (data.social_score !== undefined) researchSocialScore = data.social_score || 0;
        if (data.x_feed !== undefined) {
          researchXFeed = (researchXFeed || []).concat(data.x_feed || []);
          const seen = new Set();
          researchXFeed = researchXFeed.filter(t => {
            const key = (t.handle || t.username || '') + '|' + (t.text || t.title || '');
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          }).slice(-200);
        }
        if (data.x_tweet_count !== undefined) researchXTweetCount = (researchXFeed || []).length;
        if (data.news_last_refresh) newsLastRefresh = data.news_last_refresh;
        if (data.polymarket_signals && data.polymarket_signals.length > 0) {
          if (!window._allPolySignals) window._allPolySignals = {};
          window._allPolySignals[pod_id] = data.polymarket_signals;
          const merged = [];
          const seenQ = new Set();
          for (const podSignals of Object.values(window._allPolySignals)) {
            for (const s of podSignals) {
              const q = s.question || s.market || JSON.stringify(s);
              if (!seenQ.has(q)) { seenQ.add(q); merged.push(s); }
            }
          }
          updateResearchTab(merged, data.polymarket_confidence, data.macro_score);
        } else {
          updateResearchTab([], data.polymarket_confidence, data.macro_score);
        }
        if (msg.type === 'pod_enrichment' || !data.status) return;
      }

      // Iteration counter is set from session_snapshot/session_status only
      // (price ticker pod_summary messages are NOT iterations)
      // Track per-pod NAV for sparklines
      if (!podNavSpark[pod_id]) podNavSpark[pod_id] = [];
      podNavSpark[pod_id].push(data.nav || 0);
      if (podNavSpark[pod_id].length > 20) podNavSpark[pod_id].shift();
      updatePodsTable();
      updateFirmMetrics();
      recordNavHistory();
      calculateMetrics();
      updatePerfTable();
      calculateRisk();
      updateRiskTable();
      fetchPositionsFromApi();
      updateTopHoldings();
      refreshOpenModal();
      if (document.getElementById('tab-execution') && document.getElementById('tab-execution').classList.contains('active')) fetchClosedTrades();
      if (data.status) {
        if (typeof updatePodSilhouetteColor === 'function') updatePodSilhouetteColor(pod_id, data.status);
      }
    }
  } else if (msg.type === 'trade') {
    const t = msg.data;
    if (t.symbol && t.side && t.qty)
      addTrade(t.pod_id || 'unknown', t.symbol, t.side, t.qty, t.fill_price || 0, 'FILLED', t.order_id || t.id || null);
    if (typeof triggerTradePulse === 'function') triggerTradePulse(podFloorMap[t.pod_id] ?? 0);
    if (t.pod_id && typeof triggerPodHeartbeat === 'function') {
      triggerPodHeartbeat(t.pod_id);
    }
    const srcFloor = podFloorMap[t.pod_id] ?? 0;
    if (typeof createDataRoute === 'function') createDataRoute(srcFloor, 4, 0x00cfe8);
  } else if (msg.type === 'governance') {
    const gv = msg.data;
    if (gv.agent && gv.decision) {
      recordGov(gv.agent, gv.decision, gv.reasoning || '', gv.weights || null);
      if (typeof triggerGovernanceLightFlow === 'function') triggerGovernanceLightFlow(gv.agent);
    }
  } else if (msg.type === 'risk_alert') {
    const ra = msg.data;
    riskAlerts.unshift(ra);
    if (riskAlerts.length > 50) riskAlerts.pop();
    updateRiskAlertBanner();
    if (typeof triggerRiskAlert === 'function') triggerRiskAlert(ra);
  } else if (msg.type === 'agent_activity') {
    var act = msg.data;
    if (!agentActivity[act.agent_id]) agentActivity[act.agent_id] = [];
    agentActivity[act.agent_id].unshift(act);
    if (agentActivity[act.agent_id].length > 5) agentActivity[act.agent_id].pop();
    activityFeed.unshift({ agent_id: act.agent_id, agent_role: act.agent_role, pod_id: act.pod_id, action: act.action, summary: act.summary, detail: act.detail, urls: act.urls, ts: msg.timestamp });
    if (activityFeed.length > 50) activityFeed.pop();
    updateActivityFeed();
    updateDecisionTimeline();
    if (typeof triggerAgentActivity === 'function') triggerAgentActivity(act.pod_id, act.agent_role);
    if (act.action === 'new_report' && act.filename) {
      onNewReport(act.filename);
    }
  } else if (msg.type === 'order_update') {
    var od = msg.data;
    if (od.order_id) {
      orderBook[od.order_id] = od;
      if (od.status === 'FILLED' || od.status === 'PARTIAL') {
        addTrade(od.pod_id || 'unknown', od.symbol, od.side, od.fill_qty || od.qty, od.fill_price || 0, od.status, od.order_id);
      }
      updateExecTable();
    }
  } else if (msg.type === 'position_review') {
    addReviewEvent(msg);
    if (msg.data && msg.data.action === 'new_report' && msg.data.filename) {
      loadSavedReports();
    }
  }
}

// ─── 7. Operations ───────────────────────────────────────────────────────
function makeSparkline(vals) {
  if (!vals || vals.length < 2) return '';
  var w = 60, h = 16, len = vals.length;
  var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
  var range = max - min || 1;
  var pts = vals.map(function(v, i) {
    return (i / (len - 1) * w).toFixed(1) + ',' + (h - (v - min) / range * h).toFixed(1);
  }).join(' ');
  var col = vals[len - 1] >= vals[0] ? '#00d68f' : '#e84040';
  return '<svg width="' + w + '" height="' + h + '" style="vertical-align:middle"><polyline points="' + pts + '" fill="none" stroke="' + col + '" stroke-width="1.2"/></svg>';
}

function updatePodsTable() {
  const ids = Object.keys(pods).sort();
  document.getElementById('pod-badge').textContent = ids.length + ' pod' + (ids.length !== 1 ? 's' : '');
  const tbody = document.getElementById('pods-table');
  if (ids.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty"><div class="empty-txt">Awaiting data…</div><div class="empty-hint">Start a trading session to see live metrics</div></td></tr>';
    return;
  }
  tbody.innerHTML = ids.map(id => {
    const d   = pods[id];
    const rm  = d.risk_metrics || {};
    let nav = d.nav ?? rm.nav ?? 0;
    const invested = d.invested ?? rm.invested ?? 0;
    const startCap = d.starting_capital ?? rm.starting_capital;
    // Fallback: nav=0 but pod has allocated capital (idle pod) — show starting_capital
    if (nav === 0 && startCap > 0 && invested === 0) nav = startCap;
    const cash = d.cash ?? rm.cash ?? 0;
    const pnl = d.daily_pnl ?? rm.daily_pnl ?? 0;
    const st  = (d.status || 'UNKNOWN').toUpperCase();
    const stCls = st === 'ACTIVE' ? 'b-active' : st === 'HALTED' ? 'b-halted' : 'b-idle';
    const pc  = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : 'neu';
    const spark = makeSparkline(podNavSpark[id]);
    const navTitle = `Invested: $${invested.toFixed(2)} | Cash: $${cash.toFixed(2)}`;
    var pm = pods[id] ? (pods[id].performance_metrics || {}) : {};
    var sharpeStr = (pm.sharpe != null && pm.sharpe !== 0) ? Number(pm.sharpe).toFixed(2) : '—';
    return `<tr onclick="openDrilldown('${id}')" style="cursor:pointer" title="${navTitle}">
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r"><span title="${navTitle}">$${nav.toFixed(2)}</span></td>
      <td class="r">${spark}</td>
      <td class="r ${pc}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
      <td class="r">${sharpeStr}</td>
      <td class="r"><span class="badge ${stCls}">${st}</span></td>
    </tr>`;
  }).join('');
}

function getPodNav(d) { return d.nav ?? (d.risk_metrics && d.risk_metrics.nav) ?? 0; }
function getPodPnl(d) { return d.daily_pnl ?? (d.risk_metrics && d.risk_metrics.daily_pnl) ?? 0; }
function getPodPositions(d) {
  if (!d || typeof d !== 'object') return [];
  var raw = d.current_positions || d.positions || (d.risk_metrics && d.risk_metrics.positions) || [];
  return Array.isArray(raw) ? raw : (raw && typeof raw === 'object' ? Object.values(raw) : []);
}
function getPodInvested(d) { return d.invested ?? (d.risk_metrics && d.risk_metrics.invested) ?? 0; }
function getPodCash(d) { return d.cash ?? (d.risk_metrics && d.risk_metrics.cash) ?? 0; }
function getPodStartCap(d) { return d.starting_capital ?? (d.risk_metrics && d.risk_metrics.starting_capital) ?? 0; }

// Positions from /api/positions — single source for Top Holdings, drilldown, and KPI
var _positionsFromApi = [];
var _positionsFetchInFlight = false;
function fetchPositionsFromApi() {
  if (_positionsFetchInFlight) return;
  _positionsFetchInFlight = true;
  fetch('/api/positions').then(function(r) { return r.json(); })
    .then(function(res) {
      _positionsFromApi = res.positions || [];
      _positionsFetchInFlight = false;
      // Merge into pods so position detail modal (buildPositionFromLocal) can find data
      var byPod = {};
      _positionsFromApi.forEach(function(p) {
        var pid = p._pod || 'unknown';
        if (!byPod[pid]) byPod[pid] = [];
        byPod[pid].push(p);
      });
      Object.keys(byPod).forEach(function(pid) {
        pods[pid] = pods[pid] || {};
        pods[pid].current_positions = byPod[pid];
        pods[pid].positions = byPod[pid];
      });
      updateTopHoldings();
      updateFirmMetrics();
    })
    .catch(function() { _positionsFetchInFlight = false; });
}

function updateFirmMetrics() {
  const ids = Object.keys(pods);
  const nav = ids.reduce((s,id) => s + getPodNav(pods[id]), 0);
  const pnl = ids.reduce((s,id) => s + getPodPnl(pods[id]), 0);
  const act = ids.filter(id => (pods[id].status || '').toUpperCase() === 'ACTIVE').length;
  const pos = _positionsFromApi.length > 0 ? _positionsFromApi.length : ids.reduce((s,id) => {
    const p = getPodPositions(pods[id]);
    return s + (Array.isArray(p) ? p.length : (p && typeof p === 'object' ? Object.keys(p).length : 0));
  }, 0);

  if (initialCapital === 0 && ids.length > 0) {
    initialCapital = ids.reduce(function(s, id) {
      return s + (getPodStartCap(pods[id]) || getPodNav(pods[id]));
    }, 0);
  }

  const firmInvested = ids.reduce((s,id) => s + getPodInvested(pods[id]), 0);
  const firmCash = ids.reduce((s,id) => s + getPodCash(pods[id]), 0);

  document.getElementById('kpi-nav').textContent    = nav > 0 ? `$${nav.toFixed(0)}` : '—';
  if (nav > 0) document.getElementById('kpi-nav').title = `Invested: $${firmInvested.toFixed(0)} | Cash: $${firmCash.toFixed(0)}`;
  document.getElementById('kpi-active').textContent = act > 0 ? act : '—';
  document.getElementById('kpi-pos').textContent    = pos > 0 ? pos : '—';

  const pnlEl = document.getElementById('kpi-pnl');
  if (nav > 0) {
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} today`;
    pnlEl.className   = 'kpi-sub ' + (pnl >= 0 ? 'pos' : 'neg');
  } else {
    pnlEl.textContent = '—';
    pnlEl.className   = 'kpi-sub';
  }

  var cpnlEl = document.getElementById('kpi-cpnl');
  var cretEl = document.getElementById('kpi-cret');
  if (cpnlEl && initialCapital > 0) {
    var cpnl = nav - initialCapital;
    var cret = (cpnl / initialCapital) * 100;
    cpnlEl.textContent = (cpnl >= 0 ? '+' : '') + '$' + cpnl.toFixed(2);
    cpnlEl.className = 'kpi-val ' + (cpnl >= 0 ? 'pos' : 'neg');
    if (cretEl) {
      cretEl.textContent = (cret >= 0 ? '+' : '') + cret.toFixed(2) + '%';
      cretEl.className = 'kpi-sub ' + (cret >= 0 ? 'pos' : 'neg');
    }
  }
  updateAttribution();
}

// ─── 8. Performance ──────────────────────────────────────────────────────
const POD_COLORS = { commodities: '#f5a623', crypto: '#8b6cff', equities: '#00d4f0', fx: '#00d68f' };

function recordNavHistory() {
  const ids = Object.keys(pods);
  if (ids.length === 0) return;
  const firmNav = ids.reduce((s,id) => s + (pods[id].nav || 0), 0);
  const podNavs = {};
  ids.forEach(id => { podNavs[id] = pods[id].nav || 0; });
  // Track drawdown from high-water mark
  var hwm = 0;
  navHistory.forEach(function(h) { if (h.firmNav > hwm) hwm = h.firmNav; });
  if (firmNav > hwm) hwm = firmNav;
  var dd = hwm > 0 ? (firmNav - hwm) / hwm : 0;
  navHistory.push({ t: new Date().toLocaleTimeString(), ts: Date.now(), firmNav, pods: podNavs, drawdown: dd });
  if (navHistory.length > MAX_HISTORY) navHistory.shift();
  updateNavChart();
  updateDrawdownChart();
}

function getFilteredNavHistory() {
  if (!chartTimeframeMinutes || chartTimeframeMinutes <= 0) return navHistory;
  var cutoff = Date.now() - chartTimeframeMinutes * 60 * 1000;
  return navHistory.filter(function(h) { return h.ts && h.ts >= cutoff; });
}

function updateNavChart() {
  var filtered = getFilteredNavHistory();
  const ctx    = document.getElementById('navChart').getContext('2d');
  const labels = filtered.map(h => h.t);
  const ids    = Object.keys(pods).sort();
  const FALLBACK_COLORS = ['#00d4f0','#00d68f','#8b6cff','#f5a623'];

  const datasets = [
    { label:'FIRM NAV', data: filtered.map(h => h.firmNav),
      borderColor:'#ffffff', backgroundColor:'rgba(255,255,255,0.03)',
      borderWidth:2, pointRadius:0, tension:0.3, fill:false },
    ...ids.map((id, i) => ({
      label: id.toUpperCase(), data: filtered.map(h => h.pods[id] || 0),
      borderColor: POD_COLORS[id] || FALLBACK_COLORS[i % FALLBACK_COLORS.length], borderWidth:1,
      pointRadius:0, tension:0.3, fill:false,
    })),
  ];

  if (navChart) {
    navChart.data.labels   = labels;
    navChart.data.datasets = datasets;
    navChart.update('none');
    return;
  }
  navChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { display:true, position:'top',
          labels:{ color:'#a0b8d0', font:{size:9, family:"'IBM Plex Mono', monospace"}, padding:8, usePointStyle:true, pointStyle:'line' } },
        tooltip: { backgroundColor:'#243050', titleColor:'#00d4f0',
          bodyColor:'#f0f4fa', borderColor:'#4a5e80', borderWidth:1, padding:8 },
      },
      scales: {
        x: { grid:{color:'#384a68'}, ticks:{color:'#6a82a0', font:{size:9, family:'IBM Plex Mono'}, maxRotation:0, maxTicksLimit:6} },
        y: { grid:{color:'#384a68'}, ticks:{color:'#6a82a0', font:{size:9, family:'IBM Plex Mono'}, callback: v => '$'+v.toFixed(0)} },
      },
    },
  });
}

function getRealPerfMetrics() {
  var sharpes = [], sortinos = [], dds = [], vols = [];
  Object.values(pods).forEach(function(p) {
    var pm = p.performance_metrics || {};
    if (pm.sharpe != null && pm.sharpe !== 0) sharpes.push(pm.sharpe);
    if (pm.sortino != null && pm.sortino !== 0) sortinos.push(pm.sortino);
    if (pm.max_drawdown != null && pm.max_drawdown !== 0) dds.push(pm.max_drawdown);
    if (pm.current_vol != null && pm.current_vol !== 0) vols.push(pm.current_vol);
  });
  if (sharpes.length === 0) return null;
  var avg = function(arr) { return arr.reduce(function(a,b){return a+b;},0)/arr.length; };
  return {
    sharpe: avg(sharpes).toFixed(2),
    sortino: sortinos.length > 0 ? avg(sortinos).toFixed(2) : null,
    max_drawdown: dds.length > 0 ? Math.min.apply(null, dds) : null,
    current_vol: vols.length > 0 ? avg(vols) : null,
  };
}

function calculateMetrics() {
  if (navHistory.length < 2) return;
  const navs   = navHistory.map(h => h.firmNav);
  const rets   = navs.slice(1).map((v,i) => (v - navs[i]) / (navs[i] || 1));
  const mean   = rets.reduce((s,r) => s+r, 0) / rets.length;
  const std    = Math.sqrt(rets.reduce((s,r) => s+(r-mean)**2, 0) / rets.length) || 1e-9;
  const sharpe = mean / std * Math.sqrt(252);
  const maxNav = Math.max(...navs);
  const dd     = maxNav > 0 ? (navs[navs.length-1] - maxNav) / maxNav : 0;
  const wr     = rets.length > 0 ? rets.filter(r => r>0).length / rets.length : 0;

  document.getElementById('m-sharpe').textContent = isFinite(sharpe) ? sharpe.toFixed(2) : '—';
  document.getElementById('m-vol').textContent    = (std * Math.sqrt(252) * 100).toFixed(1) + '%';
  const ddEl = document.getElementById('m-dd');
  ddEl.textContent = (dd * 100).toFixed(1) + '%';
  ddEl.className   = 'kpi-val ' + (dd < -0.05 ? 'neg' : '');
  document.getElementById('m-wr').textContent     = (wr * 100).toFixed(0) + '%';

  // Override with real backend metrics when available (more accurate than frontend approximations)
  var realM = getRealPerfMetrics();
  if (realM) {
    var sharpeEl = document.getElementById('m-sharpe');
    if (sharpeEl) sharpeEl.textContent = realM.sharpe;
    if (realM.sortino !== null) {
      var sortEl = document.getElementById('m-sortino');
      if (sortEl) sortEl.textContent = realM.sortino;
    }
    if (realM.max_drawdown !== null) {
      var ddEl2 = document.getElementById('m-dd');
      if (ddEl2) ddEl2.textContent = (realM.max_drawdown * 100).toFixed(1) + '%';
    }
    if (realM.current_vol !== null) {
      var volEl = document.getElementById('m-vol');
      if (volEl) volEl.textContent = (realM.current_vol * 100).toFixed(1) + '%';
    }
  }
}

function updatePerfTable() {
  const ids = Object.keys(pods).sort();
  if (ids.length === 0) return;
  document.getElementById('perf-table').innerHTML = ids.map(id => {
    const d   = pods[id];
    const nav = d.nav || 0;
    const sc  = d.starting_capital || (initialCapital / Math.max(Object.keys(pods).length, 1)) || 100;
    const ret = sc > 0 ? ((nav - sc) / sc * 100) : 0;
    const pnl = d.daily_pnl || 0;
    var pm = d.performance_metrics || {};
    var sharpeStr = (pm.sharpe != null && pm.sharpe !== 0) ? Number(pm.sharpe).toFixed(2) : '—';
    return `<tr>
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r">$${nav.toFixed(2)}</td>
      <td class="r ${ret >= 0 ? 'pos' : 'neg'}">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
      <td class="r ${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
      <td class="r">${sharpeStr}</td>
    </tr>`;
  }).join('');
}

// ─── 9. Risk ──────────────────────────────────────────────────────────────
function calculateRisk() {
  const ids = Object.keys(pods);
  if (ids.length === 0) return;

  // Use real backend risk_metrics when available
  var totalVar = 0, totalLev = 0, totalVol = 0, totalDD = 0, count = 0;
  ids.forEach(function(id) {
    var d = pods[id];
    if (d.var_95 != null) totalVar += d.var_95;
    if (d.gross_leverage != null) totalLev += d.gross_leverage;
    if (d.vol_ann != null) totalVol += d.vol_ann;
    if (d.drawdown != null) totalDD = Math.min(totalDD, d.drawdown);
    count++;
  });

  var nav = ids.reduce(function(s, id) { return s + (pods[id].nav || 0); }, 0);
  var hasRealData = ids.some(function(id) { return pods[id].var_95 != null && pods[id].var_95 !== 0; });

  if (hasRealData) {
    document.getElementById('kpi-var').textContent = '$' + Math.abs(totalVar).toFixed(0);
    document.getElementById('kpi-lev').textContent = (totalLev / (count || 1)).toFixed(2) + 'x';
  } else {
    var approxVar = nav * 0.025;
    document.getElementById('kpi-var').textContent = nav > 0 ? '$' + approxVar.toFixed(0) : '—';
    document.getElementById('kpi-lev').textContent = '—';
  }

  // Drawdown: use backend value if nonzero, otherwise compute from navHistory
  var ddVal = totalDD;
  if (ddVal === 0 && navHistory.length >= 2) {
    var navs = navHistory.map(function(h) { return h.firmNav; });
    var hwm = Math.max.apply(null, navs);
    if (hwm > 0) ddVal = (navs[navs.length - 1] - hwm) / hwm;
  }
  var ddEl = document.getElementById('kpi-dd');
  if (ddEl) {
    ddEl.textContent = ddVal !== 0 ? (ddVal * 100).toFixed(1) + '%' : '0.0%';
    ddEl.className = 'kpi-val' + (ddVal < -0.05 ? ' neg' : '');
  }

  // Volatility: use backend value if nonzero, otherwise compute from navHistory
  var volVal = totalVol > 0 ? (totalVol / (count || 1)) : 0;
  if (volVal === 0 && navHistory.length >= 3) {
    var navs2 = navHistory.map(function(h) { return h.firmNav; });
    var rets = [];
    for (var ri = 1; ri < navs2.length; ri++) {
      if (navs2[ri - 1] > 0) rets.push((navs2[ri] - navs2[ri - 1]) / navs2[ri - 1]);
    }
    if (rets.length >= 2) {
      var rmean = rets.reduce(function(s, r) { return s + r; }, 0) / rets.length;
      var rvar = rets.reduce(function(s, r) { return s + (r - rmean) * (r - rmean); }, 0) / rets.length;
      volVal = Math.sqrt(rvar) * Math.sqrt(252);
    }
  }
  var volEl = document.getElementById('kpi-vol');
  if (volEl) volEl.textContent = volVal > 0 ? (volVal * 100).toFixed(1) + '%' : '—';

  document.getElementById('kpi-alerts').textContent = riskAlerts.length;
  updateRiskTable();
  renderCorrelationHeatmap();
}

function updateRiskAlertBanner(severity, message) {
  const el = document.getElementById('risk-banner');
  el.className   = 'risk-banner ' + severity;
  el.textContent = message;
  riskAlerts.push({ severity, message, ts: new Date().toISOString() });
  document.getElementById('kpi-alerts').textContent = riskAlerts.length;
  if (severity === 'critical') triggerRiskAlert();
}

function updateRiskTable() {
  const ids = Object.keys(pods).sort();
  if (ids.length === 0) return;
  document.getElementById('risk-table').innerHTML = ids.map(id => {
    const d     = pods[id];
    const nav   = d.nav || 0;
    const p     = d.current_positions;
    const pos   = Array.isArray(p) ? p.length : p ? Object.keys(p).length : 0;
    const st    = (d.status || 'UNKNOWN').toUpperCase();
    const sc    = st === 'ACTIVE' ? 'b-active' : st === 'HALTED' ? 'b-halted' : 'b-idle';
    const var95 = d.var_95 != null && d.var_95 !== 0 ? '$' + Math.abs(d.var_95).toFixed(0) : '$' + (nav * 0.025).toFixed(0);
    const lev   = d.gross_leverage != null && d.gross_leverage !== 0 ? d.gross_leverage.toFixed(2) + 'x' : '—';
    const dd    = d.drawdown != null && d.drawdown !== 0 ? (d.drawdown * 100).toFixed(1) + '%' : '0.0%';
    const ddCls = d.drawdown != null && d.drawdown < -0.05 ? 'neg' : '';
    return `<tr>
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r">${var95}</td>
      <td class="r">${lev}</td>
      <td class="r ${ddCls}">${dd}</td>
      <td class="r">${pos}</td>
      <td class="r"><span class="badge ${sc}">${st}</span></td>
    </tr>`;
  }).join('');
}

// ─── 10. Execution ─────────────────────────────────────────────────────────
function addTrade(podId, symbol, side, qty, price, status, orderId) {
  status = status || 'FILLED';
  orderId = orderId || null;
  if (orderId) {
    var exists = executedTrades.some(function(t) { return t.orderId === orderId; });
    if (exists) return;
  }
  executedTrades.unshift({ podId: podId, symbol: symbol, side: (side || '').toUpperCase(), qty: qty, price: price, status: status, ts: new Date().toISOString(), orderId: orderId });
  if (executedTrades.length > 50) executedTrades.pop();
  updateExecTable();
}

function setExecFilter(filter) {
  execFilter = filter;
  document.querySelectorAll('.ef-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.ef === filter);
  });
  updateExecTable();
}

function updateExecTable() {
  var allItems = executedTrades.slice();
  var obKeys = Object.keys(orderBook);
  var filledIds = new Set(allItems.map(function(t) { return t.orderId; }).filter(Boolean));
  obKeys.forEach(function(oid) {
    var o = orderBook[oid];
    if (!filledIds.has(oid) && (o.status === 'PENDING' || o.status === 'REJECTED' || o.status === 'PARTIAL')) {
      allItems.push({
        podId: o.pod_id || 'unknown', symbol: o.symbol, side: (o.side || '').toUpperCase(),
        qty: o.qty || 0, price: o.fill_price || 0, status: o.status,
        ts: o.timestamp || '', orderId: oid
      });
    }
  });
  allItems.sort(function(a, b) { return (b.ts || '').localeCompare(a.ts || ''); });

  if (execFilter !== 'all') {
    allItems = allItems.filter(function(t) { return t.status === execFilter.toUpperCase(); });
  }

  var pendingRejectCount = obKeys.filter(function(oid) {
    var o = orderBook[oid];
    return o && o.status !== 'FILLED' && o.status !== 'PARTIAL' && !filledIds.has(oid);
  }).length;
  document.getElementById('kpi-trades').textContent = executedTrades.length + pendingRejectCount;
  document.getElementById('kpi-filled').textContent = executedTrades.filter(function(t) { return t.status === 'FILLED'; }).length;
  if (allItems.length === 0) {
    document.getElementById('exec-table').innerHTML = '<tr><td colspan="6" class="empty"><div class="empty-txt">No trades yet</div></td></tr>';
    return;
  }
  document.getElementById('exec-table').innerHTML = allItems.slice(0, 30).map(function(t) {
    var sc = t.side === 'BUY' ? 'b-buy' : 'b-sell';
    var ss = t.status === 'FILLED' ? 'b-filled' : t.status === 'PENDING' ? 'b-pending' : t.status === 'PARTIAL' ? 'b-partial' : t.status === 'REJECTED' ? 'b-rejected' : 'b-pending';
    return '<tr>' +
      '<td>' + (t.podId || 'unknown').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(t.symbol || '') + '</td>' +
      '<td><span class="badge ' + sc + '">' + (t.side || '') + '</span></td>' +
      '<td class="r">' + (t.qty || 0) + '</td>' +
      '<td class="r">$' + (t.price || 0).toFixed(2) + '</td>' +
      '<td class="r"><span class="badge ' + ss + '">' + (t.status || '') + '</span></td>' +
      '</tr>';
  }).join('');
}

// ─── 11. Governance ───────────────────────────────────────────────────────
function recordGov(agent, decision, reasoning, weights) {
  governanceDecisions.unshift({
    agent,
    decision,
    reasoning,
    weights,
    ts: new Date().toISOString(),
  });
  if (governanceDecisions.length > 50) governanceDecisions.pop();
  if (weights && typeof weights === 'object' && Object.keys(weights).length > 0) {
    latestAllocWeights = weights;
  }
  updateGovHub();
}

var latestAllocWeights = {};

function updateGovHub() {
  const ids = Object.keys(pods).sort();
  const names = ids.length > 0 ? ids : ['equities','fx','crypto','commodities'];
  const firmNav = ids.reduce(function(s, id) { return s + (pods[id] ? pods[id].nav || 0 : 0); }, 0);
  document.getElementById('alloc-grid').innerHTML = names.map(id => {
    const nav = pods[id] ? pods[id].nav || 0 : 0;
    const pct = latestAllocWeights[id] != null ? (latestAllocWeights[id] * 100).toFixed(0) + '%'
              : firmNav > 0 ? (nav / firmNav * 100).toFixed(0) + '%' : '—';
    return `<div class="alloc-tile">
      <div class="alloc-pod">${id.toUpperCase()}</div>
      <div class="alloc-val">$${nav > 0 ? nav.toFixed(0) : '—'}</div>
      <div class="alloc-pct">${pct}</div>
    </div>`;
  }).join('');

  document.getElementById('gov-badge').textContent = governanceDecisions.length + ' decisions';
  const list = document.getElementById('gov-list');
  if (governanceDecisions.length === 0) return;
  list.innerHTML = governanceDecisions.slice(0, 10).map(d => {
    const ac = d.agent ? 'b-' + d.agent.toLowerCase() : 'b-idle';
    const tm = new Date(d.ts).toLocaleTimeString();
    return `<div class="gov-card">
      <div class="gov-card-hdr">
        <span class="badge ${ac}">${d.agent}</span>
        <span class="gov-time">${tm}</span>
      </div>
      <div class="gov-card-body">${d.decision}</div>
      ${d.reasoning ? `<div class="gov-card-sub">${d.reasoning.slice(0,120)}${d.reasoning.length>120?'…':''}</div>` : ''}
    </div>`;
  }).join('');
}

// ─── 12. Top Holdings ──────────────────────────────────────────────────────
// Uses _positionsFromApi (fetched from /api/positions) — same as drilldown and KPI
function updateTopHoldings() {
  var tbody = document.getElementById('holdings-table');
  var badge = document.getElementById('holdings-badge');
  if (!tbody) return;
  var allPos;
  if (_positionsFromApi.length > 0) {
    allPos = _positionsFromApi.slice();
  } else {
    allPos = [];
    Object.keys(pods).forEach(function(id) {
      var positions = getPodPositions(pods[id]);
      var arr = Array.isArray(positions) ? positions : (positions && typeof positions === 'object' ? Object.values(positions) : []);
      arr.forEach(function(p) {
        if (p && (p.symbol || p.qty != null)) allPos.push(Object.assign({ _pod: id }, p));
      });
    });
  }
  if (badge) badge.textContent = allPos.length + ' position' + (allPos.length !== 1 ? 's' : '');
  if (allPos.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty"><div class="empty-txt">No positions yet</div></td></tr>';
    return;
  }
  applySortHoldings(allPos);
  tbody.innerHTML = allPos.map(function(p) {
    var pnl = p.unrealized_pnl || p.unrealised_pnl || 0;
    var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
    var entry = p.cost_basis || p.avg_entry || 0;
    var notional = p.notional || (p.qty || 0) * (p.current_price || entry);
    var podEsc = escapeHtml(p._pod || '');
    var symEsc = escapeHtml(p.symbol || '');
    var entryDate = escapeHtml(p.entry_date || '—');
    var thesis = p.entry_thesis ? escapeHtml(p.entry_thesis.slice(0, 300)) : '';
    var symTitle = thesis ? 'Entry thesis: ' + thesis : 'No entry thesis recorded';
    var alertInfo = _symbolAlerts[p.symbol || ''];
    var alertBadge = (alertInfo && alertInfo.length > 0)
      ? '<span class="alert-badge" title="' + escapeHtml(alertInfo[0].headline) + '">!</span>'
      : '';
    return '<tr class="holdings-row" onclick="showPositionDetail(\'' + podEsc + '\',\'' + symEsc + '\')" title="Click for details">' +
      '<td class="pod-name">' + podEsc.toUpperCase() + '</td>' +
      '<td style="font-weight:600" title="' + symTitle + '">' + tickerDisplay(p.symbol || '') + alertBadge + (thesis ? ' <span style="color:var(--text-dim);font-size:9px">✦</span>' : '') + '</td>' +
      '<td class="r">' + (p.qty || 0).toFixed(4) + '</td>' +
      '<td class="r">$' + entry.toFixed(2) + '</td>' +
      '<td class="r">$' + (p.current_price || entry).toFixed(2) + '</td>' +
      '<td class="r ' + pc + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) + '</td>' +
      '<td class="r">$' + Math.abs(notional).toFixed(0) + '</td>' +
      '<td class="r">' + entryDate + '</td>' +
      '</tr>';
  }).join('');
}

// ─── Holdings sort state ─────────────────────────────────────────────────────
var _holdingsSortCol = 'notional';
var _holdingsSortAsc = false;

function sortHoldings(col) {
  if (_holdingsSortCol === col) {
    _holdingsSortAsc = !_holdingsSortAsc;
  } else {
    _holdingsSortCol = col;
    _holdingsSortAsc = col === 'pod' || col === 'symbol' || col === 'entry_date';
  }
  updateSortIcons();
  updateTopHoldings();
}

function applySortHoldings(arr) {
  var col = _holdingsSortCol;
  var asc = _holdingsSortAsc;
  arr.sort(function(a, b) {
    var av, bv;
    if (col === 'pod')        { av = (a._pod || '').toLowerCase(); bv = (b._pod || '').toLowerCase(); }
    else if (col === 'symbol')     { av = (a.symbol || '').toLowerCase(); bv = (b.symbol || '').toLowerCase(); }
    else if (col === 'qty')        { av = Math.abs(a.qty || 0); bv = Math.abs(b.qty || 0); }
    else if (col === 'entry')      { av = a.cost_basis || a.avg_entry || 0; bv = b.cost_basis || b.avg_entry || 0; }
    else if (col === 'price')      { av = a.current_price || 0; bv = b.current_price || 0; }
    else if (col === 'pnl')        { av = a.unrealized_pnl || a.unrealised_pnl || 0; bv = b.unrealized_pnl || b.unrealised_pnl || 0; }
    else if (col === 'entry_date') { av = a.entry_date || ''; bv = b.entry_date || ''; }
    else /* notional */            { av = Math.abs(a.notional || (a.qty || 0) * (a.current_price || 0)); bv = Math.abs(b.notional || (b.qty || 0) * (b.current_price || 0)); }
    if (av < bv) return asc ? -1 : 1;
    if (av > bv) return asc ? 1 : -1;
    return 0;
  });
}

function updateSortIcons() {
  var cols = ['pod','symbol','qty','entry','price','pnl','notional','entry_date'];
  cols.forEach(function(c) {
    var el = document.getElementById('sh-' + c);
    if (!el) return;
    if (c === _holdingsSortCol) el.textContent = _holdingsSortAsc ? '▲' : '▼';
    else el.textContent = '';
  });
}

// ─── 12b. Position Detail Modal ─────────────────────────────────────────────
var _openModalPodId = null;
var _openModalSymbol = null;

function showPositionDetail(podId, symbol) {
  var overlay = document.getElementById('pos-modal-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'pos-modal-overlay';
    overlay.className = 'pos-modal-overlay';
    overlay.onclick = function(e) { if (e.target === overlay) closePositionModal(); };
    document.body.appendChild(overlay);
  }
  overlay.classList.add('open');
  _openModalPodId = podId;
  _openModalSymbol = symbol;

  // Build modal immediately from data already on the frontend
  var localData = buildPositionFromLocal(podId, symbol);
  if (localData) {
    renderPositionModal(localData, overlay);
  } else {
    overlay.innerHTML = '<div class="pos-modal"><div class="pos-modal-loading">Loading ' + escapeHtml(symbol) + '...</div></div>';
  }

  // Try API for enriched data (fills, partial exits) with a timeout
  var controller = new AbortController();
  var timeout = setTimeout(function() { controller.abort(); }, 4000);
  fetch('/api/position/' + encodeURIComponent(podId) + '/' + encodeURIComponent(symbol), { signal: controller.signal })
    .then(function(r) { clearTimeout(timeout); if (!r.ok) throw new Error(r.statusText); return r.json(); })
    .then(function(d) { renderPositionModal(d, overlay); })
    .catch(function() {
      clearTimeout(timeout);
      if (!localData) {
        overlay.innerHTML = '<div class="pos-modal"><div class="pos-modal-err">Position data unavailable. Try again between iterations.</div><button class="pos-modal-close" onclick="closePositionModal()">Close</button></div>';
      }
    });
}

function refreshOpenModal() {
  if (!_openModalPodId || !_openModalSymbol) return;
  var overlay = document.getElementById('pos-modal-overlay');
  if (!overlay || !overlay.classList.contains('open')) return;
  var localData = buildPositionFromLocal(_openModalPodId, _openModalSymbol);
  if (localData) renderPositionModal(localData, overlay);
}

function buildPositionFromLocal(podId, symbol) {
  var pod = pods[podId];
  if (!pod) return null;
  var positions = pod.current_positions || pod.positions || [];
  if (!Array.isArray(positions)) return null;
  var pos = null;
  for (var i = 0; i < positions.length; i++) {
    if (positions[i].symbol === symbol) { pos = positions[i]; break; }
  }
  if (!pos) return null;
  var pnl = pos.unrealized_pnl || pos.unrealised_pnl || 0;
  var costBasis = pos.cost_basis || pos.avg_entry || 0;
  var pnlPct = costBasis > 0 ? (pos.current_price - costBasis) / costBasis * 100 : 0;
  var daysHeld = 0;
  if (pos.entry_date) {
    try {
      var entryMs = new Date(pos.entry_date).getTime();
      daysHeld = Math.max(0, Math.floor((Date.now() - entryMs) / 86400000));
    } catch(e) {}
  }
  return {
    symbol: pos.symbol,
    pod_id: podId,
    qty: pos.qty || 0,
    cost_basis: costBasis,
    current_price: pos.current_price || 0,
    unrealized_pnl: pnl,
    pnl_pct: pnlPct,
    entry_date: pos.entry_date || '',
    entry_thesis: pos.entry_thesis || '',
    stop_loss_pct: pos.stop_loss_pct || 0.05,
    take_profit_pct: pos.take_profit_pct || 0.15,
    max_hold_days: pos.max_hold_days || 0,
    conviction: pos.conviction || 0,
    days_held: daysHeld,
    fills: pos.fills || [],
    partial_exits: pos.partial_exits || []
  };
}

function closePositionModal() {
  var o = document.getElementById('pos-modal-overlay');
  if (o) o.classList.remove('open');
  _openModalPodId = null;
  _openModalSymbol = null;
}

function renderPositionModal(d, overlay) {
  var pnl = d.unrealized_pnl || 0;
  var pnlCls = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
  var pnlPct = d.pnl_pct || 0;
  var totalRetCls = pnlPct >= 0 ? 'pos' : 'neg';

  // SL / TP progress bar
  var slPct = ((d.stop_loss_pct || 0.05) * 100).toFixed(1);
  var tpPct = ((d.take_profit_pct || 0.15) * 100).toFixed(1);
  var currentPnlPct = pnlPct;
  var barMin = -(d.stop_loss_pct || 0.05) * 100;
  var barMax = (d.take_profit_pct || 0.15) * 100;
  var barRange = barMax - barMin;
  var markerPos = barRange > 0 ? Math.max(0, Math.min(100, (currentPnlPct - barMin) / barRange * 100)) : 50;

  // Fill timeline — synthesise an entry fill from metadata when no live fills recorded
  var fills = (d.fills && d.fills.length > 0) ? d.fills : [];
  if (fills.length === 0 && d.cost_basis > 0 && d.qty > 0) {
    fills = [{
      timestamp: d.entry_date || '',
      qty: d.qty,
      fill_price: d.cost_basis,
      side: 'BUY',
      reasoning: d.entry_thesis ? 'Entry: ' + cleanThesis(d.entry_thesis, d.symbol).slice(0, 150) : 'Position opened (fill data predates this session)',
      _synthetic: true
    }];
  }
  var fillsHtml = '';
  if (fills.length > 0) {
    fillsHtml = fills.map(function(f) {
      var isBuy = f.side === 'BUY';
      var cls = (isBuy ? 'fill-buy' : 'fill-sell') + (f._synthetic ? ' fill-synthetic' : '');
      var icon = isBuy ? '+' : '-';
      var ts = f.timestamp ? new Date(f.timestamp).toLocaleDateString() : '—';
      return '<div class="fill-entry ' + cls + '">' +
        '<span class="fill-icon">' + icon + '</span>' +
        '<div class="fill-info">' +
          '<span class="fill-side">' + f.side + '</span> ' +
          '<span class="fill-qty">' + f.qty + '</span> @ ' +
          '<span class="fill-px">$' + (f.fill_price || 0).toFixed(2) + '</span>' +
          '<span class="fill-date">' + ts + '</span>' +
        '</div>' +
        (f.reasoning ? '<div class="fill-reason">' + escapeHtml(cleanThesis(f.reasoning, d.symbol)) + '</div>' : '') +
      '</div>';
    }).join('');
  } else {
    fillsHtml = '<div class="pos-empty">No fill history available</div>';
  }

  // Update fills count in section title to use resolved fills array
  var fillsCount = fills.length;

  // Partial exits
  var exitsHtml = '';
  if (d.partial_exits && d.partial_exits.length > 0) {
    exitsHtml = '<div class="pos-section"><div class="pos-section-title">Partial Exits</div>' +
      d.partial_exits.map(function(e) {
        var rpnl = e.realized_pnl || 0;
        var rpCls = rpnl >= 0 ? 'pos' : 'neg';
        return '<div class="exit-entry">' +
          '<span class="exit-date">' + (e.date || '—') + '</span>' +
          '<span class="exit-qty">Sold ' + e.qty_sold + ' (' + e.pct_of_original + '% of original)</span>' +
          '<span class="exit-px">@ $' + (e.exit_price || 0).toFixed(2) + '</span>' +
          '<span class="exit-pnl ' + rpCls + '">P&L: ' + (rpnl >= 0 ? '+' : '') + '$' + rpnl.toFixed(4) + '</span>' +
        '</div>';
      }).join('') + '</div>';
  }

  var convPct = ((d.conviction || 0) * 100).toFixed(0);

  var avgEntry = d.cost_basis || 0;
  var thesis = cleanThesis(d.entry_thesis || '', d.symbol);

  overlay.innerHTML = '<div class="pos-modal">' +
    '<button class="pos-modal-close" onclick="closePositionModal()">&times;</button>' +
    // Header
    '<div class="pos-hdr">' +
      '<div class="pos-hdr-left">' +
        '<span class="pos-symbol">' + tickerDisplay(d.symbol) + '</span>' +
        '<span class="badge b-' + escapeHtml(d.pod_id) + '">' + escapeHtml(d.pod_id).toUpperCase() + '</span>' +
      '</div>' +
      '<div class="pos-hdr-right">' +
        '<div class="pos-hdr-pnl ' + pnlCls + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(4) + ' <span class="pos-hdr-pct">(' + (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%)</span></div>' +
      '</div>' +
    '</div>' +
    // Summary grid
    '<div class="pos-grid">' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Entry Date</div><div class="pos-cell-val">' + (d.entry_date || '—') + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Days Held</div><div class="pos-cell-val">' + (d.days_held > 0 ? d.days_held : (d.entry_date ? '< 1' : '—')) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Avg Entry</div><div class="pos-cell-val">$' + (d.cost_basis || 0).toFixed(2) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Current Price</div><div class="pos-cell-val">$' + (d.current_price || 0).toFixed(2) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Quantity</div><div class="pos-cell-val">' + (d.qty || 0) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Total Return</div><div class="pos-cell-val ' + totalRetCls + '">' + (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%</div></div>' +
    '</div>' +
    // Exit conditions bar
    '<div class="pos-section">' +
      '<div class="pos-section-title">Exit Conditions</div>' +
      '<div class="pos-exit-bar">' +
        '<div class="pos-bar-track">' +
          '<div class="pos-bar-sl" style="width:' + (((d.stop_loss_pct || 0.05) * 100) / barRange * 100) + '%"></div>' +
          '<div class="pos-bar-tp" style="width:' + (((d.take_profit_pct || 0.15) * 100) / barRange * 100) + '%;right:0"></div>' +
          '<div class="pos-bar-marker" style="left:' + markerPos + '%"></div>' +
        '</div>' +
        '<div class="pos-bar-labels">' +
          '<span class="pos-bar-sl-lbl">SL -' + slPct + '%</span>' +
          '<span class="pos-bar-now">Now ' + (currentPnlPct >= 0 ? '+' : '') + currentPnlPct.toFixed(1) + '%</span>' +
          '<span class="pos-bar-tp-lbl">TP +' + tpPct + '%</span>' +
        '</div>' +
      '</div>' +
      '<div class="pos-exit-meta">Max hold: ' + (d.max_hold_days > 0 ? d.max_hold_days + ' days' : 'No limit (thesis-driven)') + '</div>' +
    '</div>' +
    // Fill timeline
    '<div class="pos-section">' +
      '<div class="pos-section-title">Fill Timeline (' + fillsCount + (fills.length > 0 && fills[0]._synthetic ? ' — entry reconstructed' : ' fills') + ')</div>' +
      '<div class="pos-fills">' + fillsHtml + '</div>' +
    '</div>' +
    // Partial exits
    exitsHtml +
    // Entry thesis
    (thesis ? '<div class="pos-section"><div class="pos-section-title">Entry Thesis</div><div class="pos-thesis">' + escapeHtml(thesis) + '</div></div>' : '') +
    // PM Reasoning History
    (function() {
      var rh = d.reasoning_history;
      if (!rh || !rh.length) return '';
      var items = rh.slice(0, 10).map(function(r) {
        var actionCls = r.action === 'HOLD' ? 'rh-hold' : r.action === 'BUY' ? 'rh-buy' : 'rh-sell';
        var ts = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';
        var conv = r.conviction > 0 ? ' (' + (r.conviction * 100).toFixed(0) + '% conviction)' : '';
        return '<div class="rh-entry ' + actionCls + '">' +
          '<div class="rh-header"><span class="rh-badge">' + escapeHtml(r.action) + '</span><span class="rh-ts">' + ts + conv + '</span></div>' +
          '<div class="rh-text">' + escapeHtml(r.reasoning || '') + '</div>' +
        '</div>';
      }).join('');
      return '<div class="pos-section"><div class="pos-section-title">PM Reasoning History (' + rh.length + ' entries)</div>' +
        '<div class="rh-list">' + items + '</div></div>';
    })() +
  '</div>';
}

// ─── 13. Drawdown Chart ───────────────────────────────────────────────────
function updateDrawdownChart() {
  var canvas = document.getElementById('ddChart');
  if (!canvas) return;
  var filtered = getFilteredNavHistory();
  if (filtered.length < 2) return;
  var labels = filtered.map(function(h) { return h.t; });
  var ddData = filtered.map(function(h) { return (h.drawdown || 0) * 100; });
  var datasets = [{
    label: 'DRAWDOWN %',
    data: ddData,
    borderColor: '#e84040',
    backgroundColor: 'rgba(232,64,64,0.08)',
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0.3,
    fill: true,
  }];
  if (ddChart) {
    ddChart.data.labels = labels;
    ddChart.data.datasets = datasets;
    ddChart.update('none');
    return;
  }
  ddChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { display: true, position: 'top',
          labels: { color: '#a0b8d0', font: { size: 9, family: "'IBM Plex Mono', monospace" }, padding: 8, usePointStyle: true, pointStyle: 'line' } },
        tooltip: { backgroundColor: '#243050', titleColor: '#e84040', bodyColor: '#f0f4fa', borderColor: '#4a5e80', borderWidth: 1, padding: 8 },
      },
      scales: {
        x: { grid: { color: '#384a68' }, ticks: { color: '#6a82a0', font: { size: 9, family: 'IBM Plex Mono' }, maxRotation: 0, maxTicksLimit: 6 } },
        y: { grid: { color: '#384a68' }, ticks: { color: '#6a82a0', font: { size: 9, family: 'IBM Plex Mono' }, callback: function(v) { return v.toFixed(1) + '%'; } },
          suggestedMax: 0 },
      },
    },
  });
}

// ─── 14. Decision Timeline ─────────────────────────────────────────────────
function updateDecisionTimeline() {
  var container = document.getElementById('decision-timeline');
  var badge = document.getElementById('timeline-badge');
  if (!container) return;
  var events = activityFeed.filter(function(a) {
    return a.action === 'trade_decision' || a.action === 'mandate_update' || a.action === 'allocation' || a.action === 'order_executed' || a.action === 'position_review' || a.action === 'position_review_decision' || a.action === 'new_report';
  });
  if (badge) badge.textContent = events.length + ' event' + (events.length !== 1 ? 's' : '');
  if (events.length === 0) {
    container.innerHTML = '<div class="empty"><div class="empty-txt">Waiting for agent decisions…</div></div>';
    return;
  }
  container.innerHTML = events.slice(0, 20).map(function(ev) {
    var roleColor = ROLE_COLORS[ev.agent_role] || '#6a90aa';
    var ts = ev.ts ? new Date(ev.ts).toLocaleTimeString('en-GB', { hour12: false }) : '';
    var detailText = ev.detail || '';
    var fullSummary = ev.summary || '';
    var shortSummary = fullSummary.length > 120 ? fullSummary.substring(0, 120) + '…' : fullSummary;
    var hasExpandable = detailText.length > 0 || fullSummary.length > 120;
    var expandContent = detailText.length > 0
      ? (fullSummary.length > 120 ? escapeHtml(fullSummary) + '\n\n───\n\n' + escapeHtml(detailText) : escapeHtml(detailText))
      : escapeHtml(fullSummary);
    var cardId = 'tl-' + (ev.ts || '') + '-' + (ev.agent_role || '');
    return '<div class="tl-card" id="' + cardId + '">' +
      '<div class="tl-header">' +
        '<span class="tl-time">' + ts + '</span>' +
        '<span class="feed-badge" style="background:' + roleColor + '">' + escapeHtml(ev.agent_role || '?') + '</span>' +
        '<span class="tl-pod">' + escapeHtml((ev.pod_id || '').toUpperCase()) + '</span>' +
        '<span class="tl-action">' + escapeHtml((ev.action || '').replace(/_/g, ' ')) + '</span>' +
        (hasExpandable ? '<span class="tl-expand" onclick="toggleTlDetail(\'' + cardId + '\')">&#9660;</span>' : '') +
      '</div>' +
      '<div class="tl-summary">' + escapeHtml(shortSummary) + '</div>' +
      (hasExpandable ? '<div class="tl-detail" style="display:none">' + expandContent + '</div>' : '') +
      '</div>';
  }).join('');
}

function toggleTlDetail(cardId) {
  var card = document.getElementById(cardId);
  if (!card) return;
  var detail = card.querySelector('.tl-detail');
  if (!detail) return;
  var isHidden = detail.style.display === 'none';
  detail.style.display = isHidden ? 'block' : 'none';
  var arrow = card.querySelector('.tl-expand');
  if (arrow) arrow.innerHTML = isHidden ? '&#9650;' : '&#9660;';
}

// ─── 14b. Feed Entry Helper ─────────────────────────────────────────────────
function addFeedEntry(entry) {
  // entry: {type, pod_id, detail, summary, ts}
  var feedItem = {
    agent_id: (entry.pod_id || 'system') + '_researcher',
    agent_role: entry.type === 'headline_alert' ? 'Researcher' : 'System',
    pod_id: entry.pod_id || '',
    action: entry.type || 'alert',
    summary: entry.summary || '',
    detail: entry.detail || '',
    ts: entry.ts || new Date().toISOString()
  };
  activityFeed.unshift(feedItem);
  if (activityFeed.length > 50) activityFeed.pop();
  updateActivityFeed();
}

// ─── 15. Activity Feed ─────────────────────────────────────────────────────
var ROLE_COLORS = { CEO: '#f5a623', CIO: '#00d4f0', CRO: '#e84040', PM: '#00d68f', Trader: '#8b6cff', Researcher: '#6a90aa', Risk: '#ff6b35' };

function toggleIntelFeed() {
  var el = document.getElementById('activity-feed');
  if (el) el.classList.toggle('collapsed');
}

function updateActivityFeed() {
  var list = document.getElementById('feed-list');
  if (!list) return;
  var countEl = document.getElementById('intel-count');
  if (countEl) countEl.textContent = activityFeed.length > 0 ? '(' + activityFeed.length + ')' : '';
  if (activityFeed.length === 0) {
    list.innerHTML = '<div class="feed-empty">Waiting for agent activity&hellip;</div>';
    return;
  }
  list.innerHTML = activityFeed.slice(0, 30).map(function(item, idx) {
    var roleColor = ROLE_COLORS[item.agent_role] || '#6a90aa';
    var ts = item.ts ? new Date(item.ts).toLocaleTimeString('en-GB', { hour12: false }) : '';
    var actionLabel = (item.action || '').replace(/_/g, ' ');
    var fullSummary = item.summary || '';
    var detail = item.detail || '';
    var hasExpandable = fullSummary.length > 80 || detail.length > 0;
    var shortSummary;
    if (item.action === 'article_deep_dive' && item.urls) {
      shortSummary = escapeHtml(fullSummary) + ' ' +
        (item.urls || []).map(function(u) {
          return '<a href="' + escapeHtml(u) + '" target="_blank" rel="noopener" style="color:var(--cyan);font-size:9px" onclick="event.stopPropagation()">[source]</a>';
        }).join(' ');
    } else {
      shortSummary = escapeHtml(truncate(fullSummary, 80));
    }
    var expandIcon = hasExpandable ? '<span class="feed-expand-icon">&#9654;</span>' : '';
    var detailHtml = '';
    if (hasExpandable) {
      var detailParts = [];
      if (fullSummary.length > 80) detailParts.push('<div class="feed-detail-summary">' + escapeHtml(fullSummary) + '</div>');
      if (detail) detailParts.push('<div class="feed-detail-text">' + escapeHtml(detail) + '</div>');
      detailHtml = '<div class="feed-detail" id="feed-detail-' + idx + '" style="display:none">' + detailParts.join('') + '</div>';
    }
    return '<div class="feed-item-wrap' + (hasExpandable ? ' feed-expandable' : '') + '" onclick="toggleFeedDetail(' + idx + ')">' +
      '<div class="feed-item">' +
      expandIcon +
      '<span class="feed-badge" style="background:' + roleColor + '">' + escapeHtml(item.agent_role || '?') + '</span>' +
      '<span class="feed-pod">' + escapeHtml((item.pod_id || '').toUpperCase()) + '</span>' +
      '<span class="feed-action">' + escapeHtml(actionLabel) + '</span>' +
      '<span class="feed-summary">' + shortSummary + '</span>' +
      '<span class="feed-ts">' + ts + '</span>' +
      '</div>' +
      detailHtml +
      '</div>';
  }).join('');
}

function toggleFeedDetail(idx) {
  var el = document.getElementById('feed-detail-' + idx);
  if (!el) return;
  var wrap = el.parentElement;
  var isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
  if (wrap) wrap.classList.toggle('feed-expanded', isHidden);
  var icon = wrap ? wrap.querySelector('.feed-expand-icon') : null;
  if (icon) icon.innerHTML = isHidden ? '&#9660;' : '&#9654;';
}

// ─── 16. CSV Export ─────────────────────────────────────────────────────────
function downloadCsv(filename, headers, rows) {
  var csv = headers.join(',') + '\n' +
    rows.map(function(r) { return r.map(function(c) {
      return '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"';
    }).join(','); }).join('\n');
  var blob = new Blob([csv], { type: 'text/csv' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

function exportPods() {
  var ids = Object.keys(pods).sort();
  var headers = ['Pod','NAV','Daily P&L','VaR 95%','Leverage','Drawdown','Status'];
  var rows = ids.map(function(id) {
    var d = pods[id];
    return [
      id.toUpperCase(),
      (d.nav || 0).toFixed(2),
      (d.daily_pnl || 0).toFixed(2),
      d.var_95 != null ? d.var_95.toFixed(2) : '',
      d.gross_leverage != null ? d.gross_leverage.toFixed(2) : '',
      d.drawdown != null ? (d.drawdown * 100).toFixed(1) + '%' : '',
      d.status || 'UNKNOWN'
    ];
  });
  downloadCsv('pods_' + new Date().toISOString().slice(0,10) + '.csv', headers, rows);
}

function exportTrades() {
  var headers = ['Timestamp','Pod','Symbol','Side','Qty','Price','Status'];
  var rows = executedTrades.map(function(t) {
    return [t.ts || '', (t.podId || '').toUpperCase(), t.symbol, t.side, t.qty, (t.price || 0).toFixed(2), t.status];
  });
  downloadCsv('trades_' + new Date().toISOString().slice(0,10) + '.csv', headers, rows);
}

function exportNavHistory() {
  var podIds = Object.keys(pods).sort();
  var headers = ['Time','Firm NAV','Drawdown %'].concat(podIds.map(function(id) { return id.toUpperCase(); }));
  var rows = navHistory.map(function(h) {
    var row = [h.t, h.firmNav.toFixed(2), ((h.drawdown || 0) * 100).toFixed(1) + '%'];
    podIds.forEach(function(id) { row.push(((h.pods && h.pods[id]) || 0).toFixed(2)); });
    return row;
  });
  downloadCsv('nav_history_' + new Date().toISOString().slice(0,10) + '.csv', headers, rows);
}

// ─── 16b. Closed Trades ─────────────────────────────────────────────────────
var _ctLastFetch = 0;
var _ctData = [];

function fetchClosedTrades() {
  var now = Date.now();
  if (now - _ctLastFetch < 15000) return;
  _ctLastFetch = now;
  var controller = new AbortController();
  var timeout = setTimeout(function() { controller.abort(); }, 4000);
  fetch('/api/trades/closed', { signal: controller.signal })
    .then(function(r) { clearTimeout(timeout); if (!r.ok) throw new Error(r.statusText); return r.json(); })
    .then(function(data) {
      _ctData = data;
      renderClosedTrades();
    })
    .catch(function() { clearTimeout(timeout); });
}

function renderClosedTrades() {
  var tbody = document.getElementById('ct-table');
  var badge = document.getElementById('ct-badge');
  if (!tbody) return;
  if (badge) badge.textContent = _ctData.length + ' trade' + (_ctData.length !== 1 ? 's' : '');
  if (_ctData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty"><div class="empty-txt">No closed trades yet</div></td></tr>';
    return;
  }
  var totalPnl = 0;
  tbody.innerHTML = _ctData.slice(0, 30).map(function(t) {
    var pnl = t.realized_pnl || 0;
    totalPnl += pnl;
    var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
    var thesis = (t.entry_reasoning || '').substring(0, 60);
    if (t.entry_reasoning && t.entry_reasoning.length > 60) thesis += '...';
    return '<tr>' +
      '<td class="pod-name">' + escapeHtml(t.pod_id || '').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(t.symbol || '') + '</td>' +
      '<td class="r">$' + (t.entry_price || 0).toFixed(2) + '</td>' +
      '<td class="r">$' + (t.exit_price || 0).toFixed(2) + '</td>' +
      '<td class="r">' + (t.qty || 0) + '</td>' +
      '<td class="r ct-pnl ' + pc + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(4) + '</td>' +
      '<td class="r">' + (t.holding_days || '—') + '</td>' +
      '<td class="ct-thesis" title="' + escapeHtml(t.entry_reasoning || '') + '">' + escapeHtml(thesis) + '</td>' +
      '</tr>';
  }).join('');
}

// ─── 17. Chart Timeframe Toggle ────────────────────────────────────────────
function setChartTimeframe(minutes) {
  chartTimeframeMinutes = minutes;
  document.querySelectorAll('.tf-btn').forEach(function(b) {
    b.classList.toggle('active', parseInt(b.dataset.tf) === minutes);
  });
  updateNavChart();
  updateDrawdownChart();
}

// ─── 18. Pod Drill-Down ────────────────────────────────────────────────────
function openDrilldown(podId) {
  var panel = document.getElementById('pod-drilldown');
  if (!panel) return;
  var d = pods[podId];
  if (!d) return;
  panel.style.display = 'block';
  document.getElementById('dd-pod-name').textContent = podId.toUpperCase();

  var kpis = document.getElementById('dd-kpis');
  var nav = d.nav || 0;
  var pnl = d.daily_pnl || 0;
  var sc = d.starting_capital || 0;
  var cpnl = sc > 0 ? nav - sc : pnl;
  var cret = sc > 0 ? ((nav - sc) / sc * 100).toFixed(2) + '%' : '—';
  var inv = d.invested || 0;
  var csh = d.cash || 0;
  kpis.innerHTML = [
    { lbl: 'NAV', val: '$' + nav.toFixed(2) },
    { lbl: 'Invested', val: '$' + inv.toFixed(2) },
    { lbl: 'Cash', val: '$' + csh.toFixed(2) },
    { lbl: 'Daily P&L', val: (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) },
    { lbl: 'Cum. P&L', val: (cpnl >= 0 ? '+' : '') + '$' + cpnl.toFixed(2) },
    { lbl: 'Return', val: cret },
    { lbl: 'Leverage', val: d.gross_leverage != null ? d.gross_leverage.toFixed(2) + 'x' : '—' },
    { lbl: 'Drawdown', val: d.drawdown != null ? (d.drawdown * 100).toFixed(1) + '%' : '—' },
  ].map(function(k) {
    return '<div class="kpi"><div class="kpi-lbl">' + k.lbl + '</div><div class="kpi-val">' + k.val + '</div></div>';
  }).join('');

  var posTbody = document.getElementById('dd-positions');
  var posArr = _positionsFromApi.filter(function(p) { return (p._pod || '').toLowerCase() === podId.toLowerCase(); });
  if (posArr.length > 0) {
    posTbody.innerHTML = posArr.map(function(p) {
      var pnl = p.unrealized_pnl || p.unrealised_pnl || 0;
      var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
      var entry = p.cost_basis || p.avg_entry || 0;
      var notional = p.notional || (p.qty || 0) * (p.current_price || entry);
      var entryDate = escapeHtml(p.entry_date || '—');
      var podEsc = escapeHtml(podId);
      var symEsc = escapeHtml(p.symbol || '');
      var thesis = p.entry_thesis ? escapeHtml(p.entry_thesis.slice(0, 300)) : '';
      var symTitle = thesis ? 'Entry thesis: ' + thesis : 'No entry thesis recorded';
      return '<tr class="holdings-row" onclick="showPositionDetail(\'' + podEsc + '\',\'' + symEsc + '\')" title="Click for full detail" style="cursor:pointer">' +
        '<td style="font-weight:600" title="' + symTitle + '">' + tickerDisplay(p.symbol || '') + (thesis ? ' <span style="color:var(--text-dim);font-size:9px">✦</span>' : '') + '</td>' +
        '<td class="r">' + (p.qty || 0).toFixed(4) + '</td>' +
        '<td class="r">$' + entry.toFixed(2) + '</td>' +
        '<td class="r">$' + (p.current_price || entry).toFixed(2) + '</td>' +
        '<td class="r ' + pc + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) + '</td>' +
        '<td class="r">$' + Math.abs(notional).toFixed(0) + '</td>' +
        '<td class="r">' + entryDate + '</td>' +
        '</tr>';
    }).join('');
  } else {
    posTbody.innerHTML = '<tr><td colspan="7" class="empty"><div class="empty-txt">No open positions</div></td></tr>';
  }

  var tradeTbody = document.getElementById('dd-trades');
  var podTrades = executedTrades.filter(function(t) { return (t.podId || '').toLowerCase() === podId.toLowerCase(); });
  if (podTrades.length > 0) {
    tradeTbody.innerHTML = podTrades.slice(0, 10).map(function(t) {
      var sc = t.side === 'BUY' ? 'b-buy' : 'b-sell';
      var ss = t.status === 'FILLED' ? 'b-filled' : 'b-pending';
      return '<tr>' +
        '<td style="font-weight:600">' + tickerDisplay(t.symbol || '') + '</td>' +
        '<td><span class="badge ' + sc + '">' + t.side + '</span></td>' +
        '<td class="r">' + t.qty + '</td>' +
        '<td class="r">$' + (t.price || 0).toFixed(2) + '</td>' +
        '<td class="r"><span class="badge ' + ss + '">' + t.status + '</span></td>' +
        '</tr>';
    }).join('');
  } else {
    tradeTbody.innerHTML = '<tr><td colspan="5" class="empty"><div class="empty-txt">No trades for this pod</div></td></tr>';
  }

  var reasonEl = document.getElementById('dd-reasoning');
  var pmActivity = agentActivity[podId + '_pm'] || agentActivity[podId + '_PM'] || [];
  if (pmActivity.length === 0) {
    var allKeys = Object.keys(agentActivity);
    for (var i = 0; i < allKeys.length; i++) {
      if (allKeys[i].toLowerCase().indexOf(podId.toLowerCase()) >= 0 &&
          allKeys[i].toLowerCase().indexOf('pm') >= 0) {
        pmActivity = agentActivity[allKeys[i]];
        break;
      }
    }
  }
  if (pmActivity.length > 0) {
    var latest = pmActivity[0];
    reasonEl.textContent = (latest.summary || '') + (latest.detail ? '\n\n' + latest.detail : '');
  } else {
    reasonEl.textContent = 'No PM reasoning available yet.';
  }

  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeDrilldown() {
  var panel = document.getElementById('pod-drilldown');
  if (panel) panel.style.display = 'none';
}

// ─── 19. Correlation Heatmap ────────────────────────────────────────────────
function pearson(a, b) {
  if (a.length < 3 || a.length !== b.length) return 0;
  var n = a.length;
  var sumA = 0, sumB = 0, sumAB = 0, sumA2 = 0, sumB2 = 0;
  for (var i = 0; i < n; i++) {
    sumA += a[i]; sumB += b[i]; sumAB += a[i]*b[i];
    sumA2 += a[i]*a[i]; sumB2 += b[i]*b[i];
  }
  var denom = Math.sqrt((n*sumA2 - sumA*sumA) * (n*sumB2 - sumB*sumB));
  return denom === 0 ? 0 : (n*sumAB - sumA*sumB) / denom;
}

function computeCorrelationMatrix() {
  var ids = Object.keys(pods).sort();
  if (ids.length < 2 || navHistory.length < 10) return null;
  var returns = {};
  ids.forEach(function(id) {
    var navs = navHistory.map(function(h) { return (h.pods && h.pods[id]) || 0; });
    var r = [];
    for (var i = 1; i < navs.length; i++) {
      r.push(navs[i-1] > 0 ? (navs[i] - navs[i-1]) / navs[i-1] : 0);
    }
    returns[id] = r;
  });
  var matrix = {};
  ids.forEach(function(a) {
    matrix[a] = {};
    ids.forEach(function(b) {
      matrix[a][b] = a === b ? 1.0 : pearson(returns[a], returns[b]);
    });
  });
  return { ids: ids, matrix: matrix };
}

function corrColor(v) {
  if (v >= 0) {
    var g = Math.round(180 + v * 75);
    return 'rgba(0,' + g + ',100,' + (0.15 + Math.abs(v) * 0.5) + ')';
  }
  var r = Math.round(180 + Math.abs(v) * 75);
  return 'rgba(' + r + ',50,50,' + (0.15 + Math.abs(v) * 0.5) + ')';
}

function renderCorrelationHeatmap() {
  var container = document.getElementById('correlation-heatmap');
  if (!container) return;
  var result = computeCorrelationMatrix();
  if (!result) {
    container.innerHTML = '<div class="empty"><div class="empty-txt">Need 10+ data points</div></div>';
    return;
  }
  var ids = result.ids, mx = result.matrix;
  var html = '<table class="corr-table"><thead><tr><th></th>';
  ids.forEach(function(id) { html += '<th>' + id.toUpperCase() + '</th>'; });
  html += '</tr></thead><tbody>';
  ids.forEach(function(a) {
    html += '<tr><td class="corr-label">' + a.toUpperCase() + '</td>';
    ids.forEach(function(b) {
      var v = mx[a][b];
      html += '<td class="corr-cell" style="background:' + corrColor(v) + '">' + v.toFixed(2) + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

// ─── 20. Pod Attribution ────────────────────────────────────────────────────
function updateAttribution() {
  var container = document.getElementById('attribution-panel');
  if (!container) return;
  var ids = Object.keys(pods).sort();
  if (ids.length === 0) {
    container.innerHTML = '<div class="empty"><div class="empty-txt">Awaiting data...</div></div>';
    return;
  }
  var firmPnl = 0;
  var podStats = ids.map(function(id) {
    var d = pods[id];
    var nav = d.nav || 0;
    var sc = d.starting_capital || nav;
    var pnl = nav - sc;
    firmPnl += pnl;
    var podTrades = executedTrades.filter(function(t) { return (t.podId || '').toLowerCase() === id.toLowerCase(); });
    var tradeCount = podTrades.length;
    var ret = sc > 0 ? (pnl / sc * 100) : 0;
    return { id: id, pnl: pnl, ret: ret, trades: tradeCount, nav: nav };
  });
  var maxAbsPnl = Math.max.apply(null, podStats.map(function(p) { return Math.abs(p.pnl); })) || 1;

  var html = '<div class="attr-bars">';
  podStats.forEach(function(p) {
    var pct = firmPnl !== 0 ? (p.pnl / Math.abs(firmPnl) * 100) : 0;
    var barW = Math.abs(p.pnl) / maxAbsPnl * 100;
    var col = p.pnl >= 0 ? '#00d68f' : '#e84040';
    var status = p.pnl > 0 ? 'Positive' : p.pnl < 0 ? 'Negative' : 'Flat';
    html += '<div class="attr-row">' +
      '<span class="attr-pod">' + p.id.toUpperCase() + '</span>' +
      '<div class="attr-bar-wrap"><div class="attr-bar" style="width:' + barW.toFixed(0) + '%;background:' + col + '"></div></div>' +
      '<span class="attr-val" style="color:' + col + '">' + (p.pnl >= 0 ? '+' : '') + '$' + p.pnl.toFixed(2) + '</span>' +
      '<span class="attr-pct">' + (pct >= 0 ? '+' : '') + pct.toFixed(0) + '%</span>' +
      '<span class="attr-stat">' + p.trades + ' trades · ' + (p.ret >= 0 ? '+' : '') + p.ret.toFixed(1) + '% return</span>' +
      '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
}

// ─── 21. Position Review / Reports Tab ──────────────────────────────────────
var reviewEvents = [];

// Review history — persisted to localStorage
var reviewHistory = (function() {
  try { return JSON.parse(localStorage.getItem('reviewHistory') || '[]'); } catch(e) { return []; }
})();
var _rhLastSaved = (function() {
  // Pre-populate from existing history so refreshing the page doesn't re-snapshot old reviews
  var map = {};
  reviewHistory.forEach(function(e) {
    if (!map[e.pod_id] || e.ts > map[e.pod_id]) map[e.pod_id] = e.ts;
  });
  return map;
})();

function _maybeSaveReviewSnapshot(podId, reviewData) {
  var ts = reviewData.ts || '';
  if (!ts || _rhLastSaved[podId] === ts) return;
  _rhLastSaved[podId] = ts;
  reviewHistory.push({ pod_id: podId, ts: ts, data: JSON.parse(JSON.stringify(reviewData)) });
  if (reviewHistory.length > 200) reviewHistory = reviewHistory.slice(-200);
  try { localStorage.setItem('reviewHistory', JSON.stringify(reviewHistory)); } catch(e) {}
  renderReviewHistory();
}

function addReviewEvent(ev) {
  reviewEvents.push(ev);
  renderReviews();
}

function renderReviews() {
  var container = document.getElementById('review-list');
  var badge = document.getElementById('review-badge');
  if (!container) return;

  // Group events by pod, preserving most recent timestamp per pod
  var pods = {};
  reviewEvents.forEach(function(ev) {
    var d = ev.data || {};
    var podId = d.pod_id || 'firm';
    var action = d.action || '';
    if (!pods[podId]) pods[podId] = { challenge: '', pm_defense: '', cio_decision: '', counter: '', final: '', summary: '', override: '', ts: '' };
    // Track most recent timestamp for this pod's review
    var evTs = ev.timestamp || (d && d.ts) || '';
    if (evTs && evTs > pods[podId].ts) pods[podId].ts = evTs;
    if (action === 'position_review' && d.agent_role !== 'PM') pods[podId].challenge = d.detail || d.summary || '';
    if (action === 'position_review' && d.agent_role === 'PM') pods[podId].pm_defense = d.detail || d.summary || '';
    if (action === 'position_review_decision') pods[podId].cio_decision = d.detail || d.summary || '';
    if (action === 'position_review_counter') pods[podId].counter = d.detail || d.summary || '';
    if (action === 'position_review_final') pods[podId].final = d.detail || d.summary || '';
    if (action === 'review_completed') pods[podId].summary = d.detail || d.summary || '';
    if (action === 'position_review_override') pods[podId].override = d.detail || d.summary || '';
  });

  var podIds = Object.keys(pods).filter(function(p) { return p !== 'firm'; }).sort();
  if (badge) badge.textContent = podIds.length + ' review' + (podIds.length !== 1 ? 's' : '');

  // Snapshot completed reviews into history
  podIds.forEach(function(pid) {
    if (pods[pid].summary) _maybeSaveReviewSnapshot(pid, pods[pid]);
  });

  if (podIds.length === 0) {
    container.innerHTML = '<div class="empty"><div class="empty-txt">No position reviews yet</div><div class="empty-hint">Reviews run daily when positions are held</div></div>';
    return;
  }

  container.innerHTML = podIds.map(function(pid) {
    var r = pods[pid];
    var sections = '';

    // Format review date
    var dateStr = '—';
    if (r.ts) {
      try { dateStr = new Date(r.ts).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch(e) { dateStr = r.ts.slice(0, 16).replace('T', ' '); }
    }

    if (r.challenge) {
      sections += '<div class="review-section"><div class="review-label">CIO REVIEW — ALL HOLDINGS</div><div class="review-text">' + escapeHtml(r.challenge) + '</div></div>';
    }
    if (r.pm_defense) {
      sections += '<div class="review-section"><div class="review-label">PM RECOMMENDATIONS</div><div class="review-text">' + escapeHtml(r.pm_defense) + '</div></div>';
    }
    if (r.cio_decision) {
      sections += '<div class="review-section"><div class="review-label">CIO DECISION</div><div class="review-text">' + escapeHtml(r.cio_decision) + '</div></div>';
    }
    if (r.override) {
      sections += '<div class="review-section"><div class="review-label">CIO OVERRIDE</div><div class="review-text review-override">' + escapeHtml(r.override) + '</div></div>';
    }
    if (r.counter) {
      sections += '<div class="review-section"><div class="review-label">PM COUNTER-ARGUMENT</div><div class="review-text">' + escapeHtml(r.counter) + '</div></div>';
    }
    if (r.final) {
      sections += '<div class="review-section"><div class="review-label">CIO FINAL RULING</div><div class="review-text">' + escapeHtml(r.final) + '</div></div>';
    }

    // Snapshot of current holdings for this pod (from live pods state)
    var podData = (typeof pods_state !== 'undefined' ? pods_state : (typeof pods !== 'undefined' ? pods : {}))[pid];
    var posSnap = '';
    if (podData) {
      var posArr2 = getPodPositions(podData);
      posArr2 = Array.isArray(posArr2) ? posArr2 : (posArr2 && typeof posArr2 === 'object' ? Object.values(posArr2) : []);
      if (posArr2.length > 0) {
        posSnap = '<div class="review-section"><div class="review-label">HOLDINGS REVIEWED (' + posArr2.length + ')</div>' +
          '<table class="dtbl" style="font-size:10px"><thead><tr><th>Symbol</th><th class="r">Qty</th><th class="r">Entry</th><th class="r">Price</th><th class="r">Unrl P&L</th><th>Thesis</th></tr></thead><tbody>' +
          posArr2.map(function(p) {
            var pnl = p.unrealized_pnl || p.unrealised_pnl || 0;
            var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
            var entry = p.cost_basis || p.avg_entry || 0;
            var thesis = p.entry_thesis ? p.entry_thesis.slice(0, 80) + (p.entry_thesis.length > 80 ? '…' : '') : '—';
            return '<tr><td><strong>' + tickerDisplay(p.symbol || '') + '</strong></td>' +
              '<td class="r">' + (p.qty || 0).toFixed(3) + '</td>' +
              '<td class="r">$' + entry.toFixed(2) + '</td>' +
              '<td class="r">$' + (p.current_price || entry).toFixed(2) + '</td>' +
              '<td class="r ' + pc + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) + '</td>' +
              '<td style="color:var(--text-dim);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escapeHtml(p.entry_thesis || '') + '">' + escapeHtml(thesis) + '</td></tr>';
          }).join('') +
          '</tbody></table></div>';
      }
    }

    return '<div class="review-card">' +
      '<div class="review-pod-header" style="display:flex;justify-content:space-between;align-items:center">' +
        '<span>' + pid.toUpperCase() + ' — Position Review</span>' +
        '<span style="font-size:10px;color:var(--text-dim);font-family:var(--font-mono)">' + dateStr + '</span>' +
      '</div>' +
      posSnap +
      sections +
    '</div>';
  }).join('');
}

var _reviewHistoryVisible = false;

function toggleReviewHistory() {
  _reviewHistoryVisible = !_reviewHistoryVisible;
  var list = document.getElementById('review-history-list');
  var toggle = document.getElementById('review-history-toggle');
  if (list) list.style.display = _reviewHistoryVisible ? 'flex' : 'none';
  if (toggle) toggle.textContent = _reviewHistoryVisible ? '▲ HIDE' : '▼ SHOW';
  if (_reviewHistoryVisible) renderReviewHistory();
}

function renderReviewHistory() {
  var container = document.getElementById('review-history-list');
  if (!container || !_reviewHistoryVisible) return;

  if (reviewHistory.length === 0) {
    container.innerHTML = '<div class="empty"><div class="empty-txt">No history yet</div><div class="empty-hint">Completed reviews are saved here automatically</div></div>';
    return;
  }

  // Sort newest first
  var sorted = reviewHistory.slice().sort(function(a, b) { return b.ts < a.ts ? -1 : 1; });

  container.innerHTML = sorted.map(function(entry, idx) {
    var r = entry.data;
    var podId = entry.pod_id;
    var dateStr = '—';
    if (entry.ts) {
      try { dateStr = new Date(entry.ts).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch(e) { dateStr = entry.ts.slice(0, 16).replace('T', ' '); }
    }
    var bodyId = 'rh-body-' + idx;
    var sections = '';
    if (r.challenge) sections += '<div class="review-section"><div class="review-label">CIO REVIEW</div><div class="review-text">' + escapeHtml(r.challenge) + '</div></div>';
    if (r.pm_defense) sections += '<div class="review-section"><div class="review-label">PM RECOMMENDATIONS</div><div class="review-text">' + escapeHtml(r.pm_defense) + '</div></div>';
    if (r.cio_decision) sections += '<div class="review-section"><div class="review-label">CIO DECISION</div><div class="review-text">' + escapeHtml(r.cio_decision) + '</div></div>';
    if (r.override) sections += '<div class="review-section"><div class="review-label">CIO OVERRIDE</div><div class="review-text review-override">' + escapeHtml(r.override) + '</div></div>';
    if (r.counter) sections += '<div class="review-section"><div class="review-label">PM COUNTER-ARGUMENT</div><div class="review-text">' + escapeHtml(r.counter) + '</div></div>';
    if (r.final) sections += '<div class="review-section"><div class="review-label">CIO FINAL RULING</div><div class="review-text">' + escapeHtml(r.final) + '</div></div>';
    if (r.summary) sections += '<div class="review-section"><div class="review-label">SUMMARY</div><div class="review-text">' + escapeHtml(r.summary) + '</div></div>';

    return '<div class="rh-entry">' +
      '<div class="rh-entry-header" onclick="toggleRhEntry(\'' + bodyId + '\')">' +
        '<span><span class="rh-entry-pod">' + podId.toUpperCase() + '</span></span>' +
        '<span>' + dateStr + '</span>' +
      '</div>' +
      '<div class="rh-entry-body" id="' + bodyId + '">' + (sections || '<em style="color:var(--text-dim);font-size:10px">No detail available</em>') + '</div>' +
    '</div>';
  }).join('');
}

function toggleRhEntry(bodyId) {
  var el = document.getElementById(bodyId);
  if (el) el.classList.toggle('open');
}

function renderOutcomeStats() {
  var container = document.getElementById('outcome-grid');
  var badge = document.getElementById('outcomes-total-badge');
  if (!container) return;

  var podIds = Object.keys(pods).filter(function(pid) {
    var s = pods[pid].trade_outcome_stats || {};
    return s.total_trades > 0;
  });

  var totalTrades = podIds.reduce(function(sum, pid) {
    return sum + ((pods[pid].trade_outcome_stats || {}).total_trades || 0);
  }, 0);
  if (badge) badge.textContent = totalTrades + ' trade' + (totalTrades !== 1 ? 's' : '');

  if (podIds.length === 0) {
    container.innerHTML = '<div class="outcome-pod-card"><div class="empty-txt">No closed trades yet</div></div>';
    return;
  }

  container.innerHTML = podIds.map(function(pid) {
    var s = pods[pid].trade_outcome_stats || {};
    var wrCls = s.win_rate >= 0.5 ? 'pos' : 'neg';
    var avgCls = s.avg_pnl >= 0 ? 'pos' : 'neg';
    var totCls = s.total_pnl >= 0 ? 'pos' : 'neg';

    function stat(lbl, val, cls) {
      return '<div class="outcome-stat">' +
        '<div class="outcome-stat-lbl">' + lbl + '</div>' +
        '<div class="outcome-stat-val ' + cls + '">' + val + '</div>' +
      '</div>';
    }

    return '<div class="outcome-pod-card">' +
      '<div class="outcome-pod-label">' + pid.toUpperCase() + '</div>' +
      '<div class="outcome-stats-row">' +
        stat('Trades', s.total_trades || 0, '') +
        stat('Win Rate', ((s.win_rate || 0) * 100).toFixed(0) + '%', wrCls) +
        stat('Avg P&amp;L', (s.avg_pnl >= 0 ? '+' : '') + '$' + (Math.abs(s.avg_pnl) || 0).toFixed(2), avgCls) +
        stat('Total P&amp;L', (s.total_pnl >= 0 ? '+' : '') + '$' + (Math.abs(s.total_pnl) || 0).toFixed(2), totCls) +
        stat('Avg Winner', '+$' + (s.avg_winner || 0).toFixed(2), 'pos') +
        stat('Avg Loser', '$' + (s.avg_loser || 0).toFixed(2), 'neg') +
      '</div>' +
    '</div>';
  }).join('');
}

function escapeHtml(text) {
  if (text == null) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/\n/g, '<br>');
}

function loadSavedReports() {
  var container = document.getElementById('saved-reports-list');
  if (!container) return;
  container.innerHTML = '<div class="empty"><div class="empty-txt">Loading…</div></div>';
  fetch('/api/reports')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var reports = data.reports || [];
      if (reports.length === 0) {
        container.innerHTML = '<div class="empty"><div class="empty-txt">No saved reports</div><div class="empty-hint">Reports are generated after daily position reviews</div></div>';
        return;
      }
      container.innerHTML = reports.map(function(r) {
        return '<div class="saved-report-item" onclick="window.open(\'/api/reports/' + r.filename + '\', \'_blank\')">' +
          '<div class="saved-report-icon">&#128196;</div>' +
          '<div class="saved-report-info"><div class="saved-report-date">' + r.date + '</div><div class="saved-report-size">' + r.size_kb + ' KB</div></div>' +
          '<a class="saved-report-dl" href="/api/reports/' + r.filename + '" target="_blank" onclick="event.stopPropagation()">OPEN</a>' +
          '</div>';
      }).join('');
    })
    .catch(function() {
      container.innerHTML = '<div class="empty"><div class="empty-txt">Failed to load reports</div></div>';
    });
}

// ─── Closed Positions Tab ─────────────────────────────────────────────────
var _closedPositions = [];

function loadClosedPositions() {
  fetch('/api/closed-positions')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _closedPositions = data.closed_positions || [];
      renderClosedPositions();
    })
    .catch(function() {
      var tbody = document.getElementById('closed-pos-tbody');
      if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="empty"><div class="empty-txt">Failed to load — try again</div></td></tr>';
    });
}

function renderClosedPositions() {
  var tbody = document.getElementById('closed-pos-tbody');
  var badge = document.getElementById('closed-badge');
  if (!tbody) return;
  if (badge) badge.textContent = _closedPositions.length + ' position' + (_closedPositions.length !== 1 ? 's' : '');

  if (_closedPositions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty"><div class="empty-txt">No closed positions yet</div><div class="empty-hint">Positions appear here after they are fully exited</div></td></tr>';
    return;
  }

  tbody.innerHTML = _closedPositions.map(function(p, idx) {
    var pnl = p.realized_pnl || 0;
    var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
    var entryP = p.entry_price || 0;
    var exitP = p.exit_price || 0;
    var retPct = entryP > 0 ? ((exitP - entryP) / entryP * 100) : 0;
    if (p.side === 'short') retPct = -retPct;
    var retCls = retPct >= 0 ? 'pos' : 'neg';
    var entryDate = (p.entry_time || '').slice(0, 10) || '—';
    var exitDate = (p.exit_time || '').slice(0, 10) || '—';
    var holdDays = '—';
    if (p.entry_time && p.exit_time) {
      try {
        holdDays = Math.round((new Date(p.exit_time) - new Date(p.entry_time)) / 86400000) + 'd';
      } catch(e) {}
    }
    return '<tr class="holdings-row" style="cursor:pointer" onclick="showClosedPositionDetail(' + idx + ')" title="Click for details">' +
      '<td class="pod-name">' + escapeHtml(p.pod_id || '').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(p.symbol || '') + '</td>' +
      '<td class="r">$' + entryP.toFixed(2) + '</td>' +
      '<td class="r">$' + exitP.toFixed(2) + '</td>' +
      '<td class="r">' + (p.qty || 0) + '</td>' +
      '<td class="r ' + pc + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(4) + '</td>' +
      '<td class="r ' + retCls + '">' + (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%</td>' +
      '<td class="r">' + holdDays + '</td>' +
      '<td>' + entryDate + '</td>' +
      '<td>' + exitDate + '</td>' +
    '</tr>';
  }).join('');
}

function showClosedPositionDetail(idx) {
  var p = _closedPositions[idx];
  if (!p) return;

  var overlay = document.getElementById('closed-modal-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'closed-modal-overlay';
    overlay.className = 'pos-modal-overlay';
    overlay.onclick = function(e) { if (e.target === overlay) overlay.classList.remove('open'); };
    document.body.appendChild(overlay);
  }
  overlay.classList.add('open');

  var pnl = p.realized_pnl || 0;
  var pnlCls = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
  var entryP = p.entry_price || 0;
  var exitP = p.exit_price || 0;
  var retPct = entryP > 0 ? ((exitP - entryP) / entryP * 100) : 0;
  if (p.side === 'short') retPct = -retPct;
  var retCls = retPct >= 0 ? 'pos' : 'neg';
  var entryDate = (p.entry_time || '').slice(0, 10) || '—';
  var exitDate = (p.exit_time || '').slice(0, 10) || '—';
  var holdDays = '—';
  if (p.entry_time && p.exit_time) {
    try { holdDays = Math.round((new Date(p.exit_time) - new Date(p.entry_time)) / 86400000); } catch(e) {}
  }

  var entryThesis = cleanThesis(p.entry_reasoning || p.entry_thesis || '', p.symbol);
  var exitWhen = p.exit_when || '';

  overlay.innerHTML = '<div class="pos-modal">' +
    '<button class="pos-modal-close" onclick="document.getElementById(\'closed-modal-overlay\').classList.remove(\'open\')">&times;</button>' +
    '<div class="pos-hdr">' +
      '<div class="pos-hdr-left">' +
        '<span class="pos-symbol">' + tickerDisplay(p.symbol) + '</span>' +
        '<span class="badge b-' + escapeHtml(p.pod_id || '') + '">' + escapeHtml(p.pod_id || '').toUpperCase() + '</span>' +
        '<span class="badge" style="background:rgba(255,255,255,0.08);color:var(--text-dim);font-size:9px">CLOSED</span>' +
      '</div>' +
      '<div class="pos-hdr-right">' +
        '<div class="pos-hdr-avg">' + (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%</div>' +
        '<div class="pos-hdr-pnl ' + pnlCls + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(4) + ' realized</div>' +
      '</div>' +
    '</div>' +
    '<div class="pos-grid">' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Entry Date</div><div class="pos-cell-val">' + entryDate + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Exit Date</div><div class="pos-cell-val">' + exitDate + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Days Held</div><div class="pos-cell-val">' + holdDays + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Entry Price</div><div class="pos-cell-val">$' + entryP.toFixed(2) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Exit Price</div><div class="pos-cell-val">$' + exitP.toFixed(2) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Quantity</div><div class="pos-cell-val">' + (p.qty || 0) + '</div></div>' +
    '</div>' +
    '<div class="pos-section">' +
      '<div class="pos-section-title">Performance</div>' +
      '<div style="display:flex;gap:16px;flex-wrap:wrap">' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Realized P&L</div><div class="pos-cell-val ' + pnlCls + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(4) + '</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Total Return</div><div class="pos-cell-val ' + retCls + '">' + (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Conviction</div><div class="pos-cell-val">' + (((p.conviction || 0) * 100).toFixed(0)) + '%</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Side</div><div class="pos-cell-val">' + (p.side || 'long').toUpperCase() + '</div></div>' +
      '</div>' +
    '</div>' +
    (entryThesis ? '<div class="pos-section"><div class="pos-section-title">Entry Thesis</div><div class="pos-thesis">' + escapeHtml(entryThesis) + '</div></div>' : '') +
    (exitWhen ? '<div class="pos-section"><div class="pos-section-title">Exit Condition</div><div class="pos-thesis closed-exit-when">' + escapeHtml(exitWhen) + '</div></div>' : '') +
    (p.strategy_tag ? '<div class="pos-section"><div class="pos-section-title">Strategy</div><div style="font-size:11px;color:var(--text-secondary);padding:6px 0">' + escapeHtml(p.strategy_tag) + '</div></div>' : '') +
  '</div>';
}

// ─── 22. Init ──────────────────────────────────────────────────────────────
initResearchHistoryChart();
updateGovHub();
loadSavedReports();
loadClosedPositions();
