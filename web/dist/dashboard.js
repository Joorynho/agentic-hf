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

var COMMODITY_FACTOR_LIMITS = {
  gold_beta: 0.35,
  precious_metals: 0.45,
  miners_equity: 0.35,
  silver_beta: 0.30,
  oil: 0.45,
  natural_gas: 0.35,
  energy_equities: 0.45,
  agriculture: 0.45,
  industrial_metals: 0.45,
  copper: 0.35,
  uranium: 0.30,
  battery_metals: 0.35,
  broad_commodities: 0.60,
  usd_inverse: 0.60,
  real_rates: 0.60,
  equity_beta: 0.45
};

var COMMODITY_FACTOR_PROFILES = {
  GLD:{gold_beta:1.0, precious_metals:1.0, real_rates:0.45, usd_inverse:0.30},
  IAU:{gold_beta:1.0, precious_metals:1.0, real_rates:0.45, usd_inverse:0.30},
  SGOL:{gold_beta:1.0, precious_metals:1.0, real_rates:0.45, usd_inverse:0.30},
  PAXG:{gold_beta:1.0, precious_metals:1.0, real_rates:0.45, usd_inverse:0.30},
  GDX:{gold_beta:0.85, precious_metals:0.90, miners_equity:1.0, equity_beta:0.35},
  GDXJ:{gold_beta:0.90, precious_metals:0.90, miners_equity:1.0, equity_beta:0.45},
  NEM:{gold_beta:0.80, precious_metals:0.80, miners_equity:1.0, equity_beta:0.35},
  GOLD:{gold_beta:0.80, precious_metals:0.80, miners_equity:1.0, equity_beta:0.35},
  SLV:{silver_beta:1.0, precious_metals:0.80, usd_inverse:0.25},
  PSLV:{silver_beta:1.0, precious_metals:0.80, usd_inverse:0.25},
  SIL:{silver_beta:0.85, precious_metals:0.75, miners_equity:0.75, equity_beta:0.35},
  USO:{oil:1.0, usd_inverse:0.20},
  BNO:{oil:1.0, usd_inverse:0.20},
  XLE:{oil:0.70, energy_equities:1.0, equity_beta:0.45},
  XOP:{oil:0.80, energy_equities:1.0, equity_beta:0.55},
  OIH:{oil:0.75, energy_equities:1.0, equity_beta:0.50},
  UNG:{natural_gas:1.0, usd_inverse:0.15},
  AMLP:{oil:0.45, natural_gas:0.35, energy_equities:0.85, equity_beta:0.35},
  DBA:{agriculture:1.0, usd_inverse:0.20},
  CORN:{agriculture:1.0, usd_inverse:0.20},
  WEAT:{agriculture:1.0, usd_inverse:0.20},
  SOYB:{agriculture:1.0, usd_inverse:0.20},
  MOO:{agriculture:0.70, equity_beta:0.50},
  COW:{agriculture:1.0},
  MOS:{agriculture:0.75, equity_beta:0.45},
  NTR:{agriculture:0.75, equity_beta:0.45},
  GSG:{broad_commodities:1.0, oil:0.50, agriculture:0.20, industrial_metals:0.20},
  PDBC:{broad_commodities:1.0, oil:0.35, agriculture:0.25, industrial_metals:0.20},
  COM:{broad_commodities:1.0},
  DJP:{broad_commodities:1.0},
  COMT:{broad_commodities:1.0},
  CPER:{copper:1.0, industrial_metals:0.85, usd_inverse:0.20},
  COPX:{copper:0.85, industrial_metals:0.80, miners_equity:0.70, equity_beta:0.45},
  DBB:{industrial_metals:1.0, copper:0.35, usd_inverse:0.20},
  PICK:{industrial_metals:0.75, miners_equity:0.80, equity_beta:0.45},
  XME:{industrial_metals:0.65, miners_equity:0.85, equity_beta:0.55},
  REMX:{battery_metals:0.80, industrial_metals:0.50, miners_equity:0.70, equity_beta:0.45},
  FCX:{copper:0.85, industrial_metals:0.75, miners_equity:0.55, equity_beta:0.45},
  BHP:{industrial_metals:0.70, miners_equity:0.75, equity_beta:0.45},
  RIO:{industrial_metals:0.70, miners_equity:0.75, equity_beta:0.45},
  VALE:{industrial_metals:0.70, miners_equity:0.75, equity_beta:0.50},
  AA:{industrial_metals:0.80, miners_equity:0.50, equity_beta:0.45},
  CLF:{industrial_metals:0.80, miners_equity:0.50, equity_beta:0.55},
  URA:{uranium:1.0, miners_equity:0.65, equity_beta:0.45},
  URNM:{uranium:1.0, miners_equity:0.65, equity_beta:0.45},
  LIT:{battery_metals:0.85, equity_beta:0.50},
  BATT:{battery_metals:0.85, equity_beta:0.50}
};

var lossReviewState = { active: {}, history: [], triggered_count: 0 };

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
const HISTORY_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const SIGNAL_HISTORY_MAX = 2000;

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

function marketHistoryKey(sig) {
  if (!sig) return '';
  return String(sig.market_id || sig.id || sig.slug || sig.question || '').trim();
}

function stripHistoryPayload(sig) {
  var copy = Object.assign({}, sig || {});
  delete copy.price_history;
  return copy;
}

function normalizeProbability(value) {
  var n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n > 1 && n <= 100) n = n / 100;
  return Math.max(0, Math.min(1, n));
}

function historyPointTimestamp(point, fallback) {
  return (point && (point.ts || point.timestamp || point.time || point.date)) || fallback;
}

function mergePolymarketHistory(signals) {
  if (!Array.isArray(signals) || !signals.length) return;

  var cutoffMs = Date.now() - HISTORY_MAX_AGE_MS;
  var byBucketMarket = {};

  function addPoint(sig, tsValue, probValue) {
    var id = marketHistoryKey(sig);
    if (!id) return;
    var tsMs = new Date(tsValue || new Date()).getTime();
    if (!Number.isFinite(tsMs) || tsMs < cutoffMs) return;
    var prob = normalizeProbability(probValue != null ? probValue : sig.implied_prob);
    if (prob == null) return;
    var bucket = Math.floor(tsMs / BUCKET_MS) * BUCKET_MS;
    var clean = stripHistoryPayload(sig);
    clean.implied_prob = prob;
    clean.timestamp = new Date(tsMs).toISOString();
    byBucketMarket[bucket + '|' + id] = {
      ts: new Date(bucket).toISOString(),
      signals: [clean],
    };
  }

  signalHistory.forEach(function(entry) {
    var signalsInEntry = Array.isArray(entry && entry.signals) ? entry.signals : [];
    signalsInEntry.forEach(function(sig) {
      addPoint(sig, entry.ts || sig.timestamp, sig.implied_prob);
    });
  });

  signals.forEach(function(sig) {
    var history = Array.isArray(sig.price_history) ? sig.price_history : [];
    if (history.length) {
      history.forEach(function(point) {
        addPoint(sig, historyPointTimestamp(point, sig.timestamp), point.implied_prob);
      });
    } else {
      addPoint(sig, sig.timestamp || new Date().toISOString(), sig.implied_prob);
    }
  });

  signalHistory = Object.keys(byBucketMarket)
    .map(function(k) { return byBucketMarket[k]; })
    .sort(function(a, b) { return new Date(a.ts) - new Date(b.ts); });
  if (signalHistory.length > SIGNAL_HISTORY_MAX) signalHistory = signalHistory.slice(-SIGNAL_HISTORY_MAX);
  saveSignalHistory();
}

function flattenedSignalHistory() {
  var rows = [];
  signalHistory.forEach(function(entry) {
    var ts = entry && entry.ts;
    (entry && entry.signals || []).forEach(function(sig) {
      rows.push({ ts: ts, id: marketHistoryKey(sig), signal: sig });
    });
  });
  return rows.filter(function(row) {
    return row.id && row.signal && normalizeProbability(row.signal.implied_prob) != null;
  }).sort(function(a, b) {
    return new Date(a.ts) - new Date(b.ts);
  });
}

function previousMarketProbability(marketId, beforeTs) {
  var beforeMs = new Date(beforeTs || new Date()).getTime();
  var best = null;
  flattenedSignalHistory().forEach(function(row) {
    if (row.id !== marketId) return;
    var rowMs = new Date(row.ts).getTime();
    if (!Number.isFinite(rowMs) || rowMs >= beforeMs - 1000) return;
    best = row.signal.implied_prob;
  });
  return best;
}

function ensurePolymarketHistoryLayout() {
  var header = document.querySelector('#subtab-historical .research-header');
  if (header) {
    header.innerHTML = 'IMPLIED PROBABILITY TRENDS - Rolling 30-Day View (4h intervals) - <span id="history-data-count" style="color:var(--cyan);">0</span> data points stored';
  }
  var headRow = document.querySelector('#history-table thead tr');
  if (headRow && headRow.children.length !== 7) {
    headRow.innerHTML = '<th>Time</th><th>Market</th><th class="num">Status</th><th class="num accent">Prob</th><th class="num">Delta</th><th class="num">24h Vol</th><th class="num">End Date</th>';
  }
}
const NEWS_SCORE_WINDOW = 25;
const NEWS_DISPLAY_LIMIT = 100;
const NEWS_CACHE_LIMIT = 200;
const NEWS_FRESH_MS = 15 * 60 * 1000;
var RESEARCH_FEED_REFRESH_MS = 60 * 1000;
var researchFeedAudit = null;
var researchFeedAuditLoading = false;
var researchFeedAuditLastFetchMs = 0;
var foresightLedger = null;
var foresightLedgerLoading = false;
var foresightLedgerLastFetchMs = 0;
var catalystThreads = null;
var reportCorpus = null;

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
      .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
      .then(function(d) {
        if (d.ok) updateSessionStatus(false);
        else if (d.detail) alert(d.detail);
      })
      .catch(function(e) { console.error('stop failed', e); });
  } else {
    fetch('/api/session/start', { method: 'POST' })
      .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
      .then(function(d) {
        if (d.ok) updateSessionStatus(true);
        else if (d.detail) alert(d.detail);
      })
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
    if (btn.dataset.tab === 'risk') {
      fetchPositionsFromApi();
      fetchCorrelationAndRender();
      renderFactorRiskTable();
      fetchLossReviews();
    }
    if (btn.dataset.tab === 'performance') {
      fetchClosedTrades(true);
      fetchPositionsFromApi();
      refreshPerformanceCharts();
      fetch('/api/benchmarks').then(function(r) { return r.json(); }).then(function(d) {
        benchmarkReturns = (d && d.benchmarks) ? d.benchmarks : {};
        refreshPerformanceCharts();
      }).catch(function() {});
    }
    if (btn.dataset.tab === 'operations' && typeof renderOpsOverview === 'function') renderOpsOverview();
  });
});

function setExecSubTab(name) {
  document.querySelectorAll('.exec-subtab-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.execsub === name);
  });
  var tl = document.getElementById('exec-subtab-tradelog');
  var q = document.getElementById('exec-subtab-quality');
  var mh = document.getElementById('exec-subtab-models');
  var br = document.getElementById('exec-subtab-broker');
  var au = document.getElementById('exec-subtab-audit');
  if (tl) tl.style.display = name === 'tradelog' ? 'block' : 'none';
  if (q) q.style.display = name === 'quality' ? 'block' : 'none';
  if (mh) mh.style.display = name === 'models' ? 'block' : 'none';
  if (br) br.style.display = name === 'broker' ? 'block' : 'none';
  if (au) au.style.display = name === 'audit' ? 'block' : 'none';
  if (name === 'quality' && typeof renderExecutionQuality === 'function') renderExecutionQuality();
  if (name === 'models' && typeof renderModelHealth === 'function') renderModelHealth();
  if (name === 'broker' && typeof renderBrokerReconciliation === 'function') renderBrokerReconciliation();
  if (name === 'audit' && typeof renderDecisionAudit === 'function') renderDecisionAudit();
}

function setOpsSubTab(name) {
  document.querySelectorAll('.ops-subtab-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.opssub === name);
  });
  var s = document.getElementById('ops-subtab-summary');
  var o = document.getElementById('ops-subtab-overview');
  var h = document.getElementById('ops-subtab-health');
  if (s) s.style.display = name === 'summary' ? 'block' : 'none';
  if (o) o.style.display = name === 'overview' ? 'block' : 'none';
  if (h) h.style.display = name === 'health' ? 'block' : 'none';
  if (name === 'overview' && typeof renderOpsOverview === 'function') renderOpsOverview();
  if (name === 'health' && typeof renderStateHealth === 'function') renderStateHealth();
}

function renderExecutionQuality() {
  var el = document.getElementById('exec-quality-panel');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="empty-txt">Loading…</div></div>';
  fetchJsonWithTimeout('/api/execution-quality', {}, 3500).then(function(data) {
    var podIds = Object.keys(data || {}).sort();
    if (podIds.length === 0) podIds = Object.keys(pods || {}).sort();
    if (podIds.length === 0) podIds = ['commodities', 'crypto', 'equities', 'fx'];
    if (podIds.length === 0) {
      el.innerHTML = '<div class="empty"><div class="empty-txt">No execution data</div></div>';
      return;
    }
    var html = '<div class="kpi-row">';
    podIds.forEach(function(pid) {
      var s = data[pid] || {};
      var nf = s.fills_with_slippage_data || 0;
      var totalFills = s.total_fills || executionFillCountForPod(pid);
      var missing = s.fills_missing_slippage_data != null ? s.fills_missing_slippage_data : Math.max(0, totalFills - nf);
      html += '<div class="kpi"><div class="kpi-lbl">' + pid.toUpperCase() + '</div>';
      if (nf === 0 && totalFills > 0) {
        html += '<div class="kpi-val">' + totalFills + '</div><div class="kpi-sub">' + missing + ' fill' + (missing === 1 ? '' : 's') + ' missing slippage capture</div>';
      } else if (nf === 0) {
        html += '<div class="kpi-val">—</div><div class="kpi-sub">No slippage data yet</div>';
      } else {
        html += '<div class="kpi-val">' + (s.avg_slippage_bps != null ? s.avg_slippage_bps + ' bps' : '—') + '</div>';
        html += '<div class="kpi-sub">max ' + (s.max_slippage_bps != null ? s.max_slippage_bps : '—') + ' bps · ' + (s.total_fills || 0) + ' fills</div>';
      }
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }).catch(function() {
    var podIds = Object.keys(pods || {}).sort();
    if (podIds.length === 0) podIds = ['commodities', 'crypto', 'equities', 'fx'];
    var html = '<div class="kpi-row">';
    podIds.forEach(function(pid) {
      var fills = executionFillCountForPod(pid);
      html += '<div class="kpi"><div class="kpi-lbl">' + pid.toUpperCase() + '</div>' +
        '<div class="kpi-val">' + (fills || '—') + '</div>' +
        '<div class="kpi-sub">' + (fills ? 'local fills; slippage endpoint unavailable' : 'No local fills yet') + '</div></div>';
    });
    html += '</div>';
    el.innerHTML = html;
  });
}

function modelStatusClass(status) {
  status = String(status || '').toLowerCase();
  if (status === 'success') return 'b-active';
  if (status === 'rate_limited' || status === 'unavailable') return 'b-pending';
  if (status === 'failed') return 'b-rejected';
  return 'b-pending';
}

function renderModelHealth() {
  var el = document.getElementById('model-health-panel');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="empty-txt">Loading model health...</div></div>';
  fetchJsonWithTimeout('/api/model-health?limit=120', {}, 3500).then(function(data) {
    data = data || {};
    var models = data.by_model || [];
    var tasks = data.by_task || [];
    var recent = data.recent || [];
    var budget = data.budget || {};
    var budgetToday = budget.today || {};
    var html = '<div class="broker-panel">';
    html += '<div class="sec-hdr"><span class="sec-title">Model Health</span>' +
      '<span class="sec-badge">' + recent.length + ' recent calls</span>' +
      '<button class="export-btn" onclick="renderModelHealth()">Refresh</button></div>';
    html += '<div class="kpi-row">' +
      '<div class="kpi"><div class="kpi-lbl">Provider Order</div><div class="kpi-val" style="font-size:15px">' + escapeHtml((data.provider_order || []).join(' -> ') || '—') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Default</div><div class="kpi-val" style="font-size:15px">' + escapeHtml(data.default_openai_model || '—') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Reasoning</div><div class="kpi-val" style="font-size:15px">' + escapeHtml(data.strong_openai_model || '—') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Deep Review</div><div class="kpi-val" style="font-size:15px">' + escapeHtml(data.frontier_openai_model || '—') + '</div></div>' +
      '</div>';

    html += '<div class="kpi-row">' +
      '<div class="kpi"><div class="kpi-lbl">Budget Mode</div><div class="kpi-val" style="font-size:15px">' + escapeHtml(budgetToday.degraded ? 'DEGRADED' : 'NORMAL') + '</div><div class="kpi-sub">' + escapeHtml(budgetToday.degraded_reason || 'hard controls active') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Calls Today</div><div class="kpi-val">' + (budgetToday.calls || 0) + '</div><div class="kpi-sub">' + (budgetToday.failures || 0) + ' failures</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Fallback Rate</div><div class="kpi-val">' + (((budgetToday.fallback_rate || 0) * 100).toFixed(0)) + '%</div><div class="kpi-sub">' + (budgetToday.fallback_calls || 0) + ' fallback calls</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Tokens</div><div class="kpi-val">' + (budgetToday.token_estimate || 0) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Est. Cost</div><div class="kpi-val">$' + Number(budgetToday.cost_estimate || 0).toFixed(4) + '</div></div>' +
      '</div>';
    html += '<div class="sec-hdr"><span class="sec-title">By Model</span><span class="sec-badge">' + models.length + ' models</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Model</th><th class="r">Calls</th><th class="r">Success</th><th class="r">Fail</th><th class="r">Avg Latency</th><th>Status</th><th>Last Error</th>' +
      '</tr></thead><tbody>';
    html += models.length ? models.map(function(m) {
      return '<tr>' +
        '<td class="mono">' + escapeHtml(m.key || '') + '</td>' +
        '<td class="r">' + (m.calls || 0) + '</td>' +
        '<td class="r pos">' + (m.successes || 0) + '</td>' +
        '<td class="r neg">' + (m.failures || 0) + '</td>' +
        '<td class="r">' + (m.avg_latency_ms != null ? m.avg_latency_ms + ' ms' : '—') + '</td>' +
        '<td><span class="badge ' + modelStatusClass(m.last_status) + '">' + escapeHtml(m.last_status || '—') + '</span></td>' +
        '<td style="max-width:320px;white-space:normal">' + escapeHtml(m.last_error || '—') + '</td>' +
        '</tr>';
    }).join('') : '<tr><td colspan="7" class="empty"><div class="empty-txt">No model calls recorded yet</div></td></tr>';
    html += '</tbody></table></div>';

    html += '<div class="sec-hdr"><span class="sec-title">By Task</span><span class="sec-badge">' + tasks.length + ' tasks</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Task</th><th class="r">Calls</th><th class="r">Success</th><th class="r">Fail</th><th class="r">Avg Latency</th><th>Status</th>' +
      '</tr></thead><tbody>';
    html += tasks.length ? tasks.map(function(t) {
      return '<tr><td class="mono">' + escapeHtml(t.key || '') + '</td>' +
        '<td class="r">' + (t.calls || 0) + '</td>' +
        '<td class="r pos">' + (t.successes || 0) + '</td>' +
        '<td class="r neg">' + (t.failures || 0) + '</td>' +
        '<td class="r">' + (t.avg_latency_ms != null ? t.avg_latency_ms + ' ms' : '—') + '</td>' +
        '<td><span class="badge ' + modelStatusClass(t.last_status) + '">' + escapeHtml(t.last_status || '—') + '</span></td></tr>';
    }).join('') : '<tr><td colspan="6" class="empty"><div class="empty-txt">No task telemetry yet</div></td></tr>';
    html += '</tbody></table></div>';

    html += '<div class="sec-hdr"><span class="sec-title">Recent Calls</span><span class="sec-badge">' + recent.length + ' attempts</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Time</th><th>Task</th><th>Provider</th><th>Model</th><th>Status</th><th class="r">Tokens</th><th class="r">Cost</th><th class="r">Latency</th><th>Error</th>' +
      '</tr></thead><tbody>';
    html += recent.length ? recent.slice(0, 40).map(function(r) {
      return '<tr><td class="mono">' + escapeHtml(formatRelativeTime(r.ts)) + '</td>' +
        '<td class="mono">' + escapeHtml(r.task || '') + '</td>' +
        '<td>' + escapeHtml(r.provider || '') + '</td>' +
        '<td class="mono">' + escapeHtml(r.model || '') + '</td>' +
        '<td><span class="badge ' + modelStatusClass(r.status) + '">' + escapeHtml(r.status || '') + '</span></td>' +
        '<td class="r">' + (r.total_tokens != null ? r.total_tokens : '—') + '</td>' +
        '<td class="r">' + (r.cost_estimate != null ? '$' + Number(r.cost_estimate || 0).toFixed(4) : '—') + '</td>' +
        '<td class="r">' + (r.latency_ms != null ? r.latency_ms + ' ms' : '—') + '</td>' +
        '<td style="max-width:320px;white-space:normal">' + escapeHtml(r.error || '—') + '</td></tr>';
    }).join('') : '<tr><td colspan="9" class="empty"><div class="empty-txt">No calls recorded yet</div></td></tr>';
    html += '</tbody></table></div></div>';
    el.innerHTML = html;
  }).catch(function(err) {
    el.innerHTML = '<div class="empty"><div class="empty-txt">Could not load model health</div><div class="empty-hint">' + escapeHtml(err && err.message ? err.message : '') + '</div></div>';
  });
}

function applyExecutionReconciliation(data) {
  var updates = (data && data.updates) || [];
  updates.forEach(function(u) {
    if (!u || !u.order_id) return;
    var key = u.local_order_id || u.order_id;
    var existing = Object.assign({}, orderBook[key] || {}, orderBook[u.order_id] || {});
    orderBook[key] = Object.assign(existing, u);
    if (key !== u.order_id && orderBook[u.order_id]) delete orderBook[u.order_id];
  });
  if (updates.length) updateExecTable();
}

function reconcileExecutionOrders() {
  return fetchJsonWithTimeout('/api/execution-reconciliation', { method: 'POST' }, 4500)
    .then(function(data) {
      applyExecutionReconciliation(data);
      return data || {};
    });
}

function moneyOrDash(v) {
  var n = Number(v);
  return Number.isFinite(n) ? '$' + n.toFixed(2) : '—';
}

function countText(count, singular, plural) {
  var n = Number(count || 0);
  return n + ' ' + (n === 1 ? singular : (plural || singular + 's'));
}

function fetchJsonWithTimeout(url, options, timeoutMs) {
  var ms = timeoutMs || 4000;
  if (typeof AbortController === 'undefined') {
    return fetch(url, options || {}).then(function(r) {
      if (!r.ok) throw new Error(url + ' returned HTTP ' + r.status);
      return r.json();
    });
  }
  var controller = new AbortController();
  var opts = Object.assign({}, options || {}, { signal: controller.signal });
  var timer = setTimeout(function() { controller.abort(); }, ms);
  return fetch(url, opts).then(function(r) {
    if (!r.ok) throw new Error(url + ' returned HTTP ' + r.status);
    return r.json();
  }).finally(function() {
    clearTimeout(timer);
  });
}

function executionFillCountForPod(pid) {
  var key = String(pid || '').toLowerCase();
  var count = 0;
  (executedTrades || []).forEach(function(t) {
    if (String(t.podId || t.pod_id || '').toLowerCase() === key &&
        String(t.status || '').toUpperCase() === 'FILLED') count += 1;
  });
  Object.keys(orderBook || {}).forEach(function(oid) {
    var o = orderBook[oid] || {};
    if (String(o.pod_id || o.podId || '').toLowerCase() === key &&
        String(o.status || '').toUpperCase() === 'FILLED') count += 1;
  });
  return count;
}

function orderDiagnosticAction(item) {
  var reason = String(item.reason || '').toLowerCase();
  var stage = String(item.stage || '').toLowerCase();
  var symbol = String(item.symbol || '');
  if (reason.indexOf('time_in_force') >= 0 || reason.indexOf('time in force') >= 0) {
    return 'Fix order format: crypto should use GTC/IOC, equities normally DAY/GTC.';
  }
  if (reason.indexOf('buying power') >= 0 || reason.indexOf('insufficient') >= 0) {
    return 'Reduce size or free capital before retrying.';
  }
  if (reason.indexOf('not tradable') >= 0 || reason.indexOf('inactive') >= 0 || reason.indexOf('unsupported') >= 0) {
    return 'Remove or replace the symbol in the pod universe.';
  }
  if (stage.indexOf('evidence_review') >= 0 || reason.indexOf('evidence') >= 0 || reason.indexOf('thesis review') >= 0) {
    return 'Refresh the thesis/evidence packet before adding risk; reductions remain allowed.';
  }
  if (symbol.indexOf('/') >= 0 && (!item.reason || reason === 'order rejected')) {
    return 'Crypto rejection is still generic; check Alpaca crypto/account permissions and restart if server code was updated.';
  }
  if (stage.indexOf('preflight') >= 0) {
    return 'Blocked before broker submit; PM/risk should adapt to the preflight reason.';
  }
  if (item.status === 'PENDING') {
    return 'Pending at broker/local layer; reconcile if stale.';
  }
  return reason ? 'Use this reason in the next PM/risk decision.' : 'No specific broker reason captured yet.';
}

function recentExecutionDiagnostics(limit) {
  var rows = Object.keys(orderBook || {}).map(function(k) {
    return orderBook[k] || {};
  }).concat(executedTrades || []);
  (activityFeed || []).forEach(function(item) {
    var action = String(item.action || '');
    if (['evidence_review_blocked', 'evidence_review_required', 'broker_guard_blocked', 'loss_review_gate_failed', 'data_quality_gate_failed'].indexOf(action) === -1) return;
    rows.push({
      ts: item.ts || item.timestamp || '',
      pod_id: item.pod_id || '',
      symbol: item.symbol || '',
      side: '',
      qty: 0,
      price: 0,
      status: action === 'evidence_review_required' ? 'PENDING' : 'BLOCKED',
      stage: action,
      reason: item.reason || item.detail || item.summary || '',
      order_id: action + '|' + (item.pod_id || '') + '|' + (item.symbol || '') + '|' + (item.ts || ''),
    });
  });
  var seen = {};
  var out = [];
  rows.forEach(function(item) {
    var key = item.order_id || item.orderId || [item.pod_id || item.podId, item.symbol, item.status, item.reason].join('|');
    if (seen[key]) return;
    seen[key] = true;
    var status = String(item.status || '').toUpperCase();
    if (status !== 'REJECTED' && status !== 'PENDING' && status !== 'PARTIAL' && status !== 'BLOCKED') return;
    out.push({
      ts: item.ts || item.timestamp || item.submitted_at || '',
      pod_id: item.pod_id || item.podId || '',
      symbol: item.symbol || '',
      side: item.side || '',
      qty: item.qty || item.quantity || 0,
      status: status,
      stage: item.stage || '',
      reason: executionReasonForDisplay({
        status: status,
        symbol: item.symbol || '',
        reason: item.reason || item.rejection_reason || item.rejection_detail || '',
        stage: item.stage || '',
      }),
      order_id: item.order_id || item.orderId || '',
    });
  });
  return out.slice(0, limit || 12);
}

function fallbackPodHealthRows() {
  return Object.keys(pods || {}).sort().map(function(pid) {
    var d = pods[pid] || {};
    var nav = getPodNav(d);
    var cash = getPodCash(d);
    var invested = getPodInvested(d);
    var startCap = getPodStartCap(d) || nav || 0;
    var positions = getPodPositions(d);
    return {
      pod_id: pid,
      status: nav > 0 || startCap > 0 ? 'OK' : 'CHECK',
      issues: nav > 0 || startCap > 0 ? [] : ['Missing live NAV'],
      starting_capital: startCap,
      allocated_capital: startCap,
      nav: nav || startCap,
      cash: cash,
      invested: invested,
      position_count: positions.length,
      last_nav_ts: d.timestamp || d.updated_at || null,
      last_nav_quality: 'dashboard_snapshot',
    };
  });
}

function normalizeStateHealthData(data, reason) {
  data = data || {};
  var warnings = (data.warnings || []).slice();
  if ((!data.pods || !data.pods.length) && Object.keys(pods || {}).length) {
    data.pods = fallbackPodHealthRows();
    warnings.push(reason || 'Health endpoint returned no pod rows; showing latest dashboard snapshot');
  }
  if (data.capital_per_pod == null || Number(data.capital_per_pod) <= 0) {
    var ids = Object.keys(pods || {});
    var totalStart = ids.reduce(function(sum, pid) {
      return sum + (getPodStartCap(pods[pid]) || 0);
    }, 0);
    data.capital_per_pod = ids.length && totalStart > 0 ? totalStart / ids.length : data.capital_per_pod;
  }
  data.nav_history = data.nav_history || {};
  if (!data.nav_history.total_rows && navHistory && navHistory.length) {
    data.nav_history.total_rows = navHistory.length;
    var last = navHistory[navHistory.length - 1] || {};
    data.nav_history.last_ts = last.ts ? new Date(last.ts).toISOString() : null;
  }
  data.broker = data.broker || { status: 'UNKNOWN', mismatch_count: null, errors: [] };
  data.evidence_review = data.evidence_review || { status: 'UNKNOWN', counts: {}, queue: [] };
  data.warnings = warnings;
  if (!data.status) data.status = warnings.length ? 'CHECK' : 'OK';
  return data;
}

function evidenceReviewBadgeClass(status) {
  status = String(status || '').toUpperCase();
  if (status === 'URGENT') return 'b-rejected';
  if (status === 'REVIEW' || status === 'WATCH') return 'b-pending';
  if (status === 'OK') return 'b-active';
  return 'b-pending';
}

function renderEvidenceReviewQueue(review) {
  review = review || {};
  var rows = review.queue || [];
  var counts = review.counts || {};
  var html = '<div class="sec-hdr"><span class="sec-title">Evidence Review Queue</span>' +
    '<span class="sec-badge">' + rows.length + ' item' + (rows.length === 1 ? '' : 's') + '</span>' +
    '<button class="export-btn" onclick="renderStateHealth()">Refresh</button></div>';
  html += '<div class="kpi-row">' +
    '<div class="kpi"><div class="kpi-lbl">Urgent</div><div class="kpi-val neg">' + (counts.URGENT || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Review</div><div class="kpi-val">' + (counts.REVIEW || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Watch</div><div class="kpi-val">' + (counts.WATCH || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Status</div><div class="kpi-val" style="font-size:18px">' + escapeHtml(review.status || 'UNKNOWN') + '</div></div>' +
    '</div>';
  html += '<div class="tbl-wrap broker-table-wrap evidence-review-wrap"><table class="dtbl"><thead><tr>' +
    '<th>Pod</th><th>Symbol</th><th>Status</th><th class="r">Evidence</th><th class="r">Coverage</th><th>Reason</th><th>Next Action</th><th>Updated</th>' +
    '</tr></thead><tbody>';
  if (!rows.length) {
    html += '<tr><td colspan="8" class="empty"><div class="empty-txt">No evidence or thesis review items</div><div class="empty-hint">Open holdings have no stale evidence, challenged theses, or weak-evidence warnings.</div></td></tr>';
  } else {
    html += rows.map(function(row) {
      var reasons = row.reasons || [];
      var reasonText = reasons.length ? reasons.join('; ') : 'Review evidence packet';
      var updated = row.evidence_generated_at ? formatRelativeTime(row.evidence_generated_at) : 'not recorded';
      return '<tr class="evidence-review-row" onclick="showPositionDetail(\'' + escapeHtml(row.pod_id || '') + '\', \'' + escapeHtml(row.symbol || '') + '\')">' +
        '<td style="font-weight:600">' + escapeHtml(String(row.pod_id || '').toUpperCase()) + '</td>' +
        '<td style="font-weight:700">' + tickerDisplay(row.symbol || '') + '</td>' +
        '<td><span class="badge ' + evidenceReviewBadgeClass(row.status) + '">' + escapeHtml(row.status || '') + '</span></td>' +
        '<td class="r">' + Number(row.evidence_score || 0).toFixed(0) + '</td>' +
        '<td class="r">' + Number(row.coverage_score || 0).toFixed(0) + '%</td>' +
        '<td class="evidence-review-reason">' + escapeHtml(reasonText) + '</td>' +
        '<td>' + escapeHtml(row.next_action || '') + '</td>' +
        '<td class="mono">' + escapeHtml(updated) + '</td>' +
        '</tr>';
    }).join('');
  }
  html += '</tbody></table></div>';
  return html;
}

function renderManagedRuntimePanel(managed) {
  managed = managed || {};
  var runs = managed.agent_runs || {};
  var artifacts = managed.artifacts || {};
  var budgets = managed.budgets || {};
  var scheduler = managed.scheduler || {};
  var artifactRows = (artifacts.artifacts || []).slice(0, 18);
  var jobRows = (scheduler.jobs || []).slice(0, 12);
  var runRows = (runs.recent || []).slice(0, 18);
  var today = budgets.today || {};
  var html = '<div class="sec-hdr"><span class="sec-title">Managed Agent Layer</span>' +
    '<span class="sec-badge">' + (runs.count || 0) + ' recent runs</span></div>';
  html += '<div class="kpi-row">' +
    '<div class="kpi"><div class="kpi-lbl">Failed Runs</div><div class="kpi-val ' + ((runs.failed_count || 0) ? 'neg' : '') + '">' + (runs.failed_count || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Running Jobs</div><div class="kpi-val">' + (scheduler.running_count || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Stale Artefacts</div><div class="kpi-val ' + ((artifacts.stale_count || 0) ? 'neg' : '') + '">' + (artifacts.stale_count || 0) + '</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Model Calls Today</div><div class="kpi-val">' + (today.calls || 0) + '</div><div class="kpi-sub">' + (today.failures || 0) + ' failures · ' + (((today.fallback_rate || 0) * 100).toFixed(0)) + '% fallback</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Est. Model Cost</div><div class="kpi-val">$' + Number(today.cost_estimate || 0).toFixed(4) + '</div><div class="kpi-sub">' + (today.token_estimate || 0) + ' tokens</div></div>' +
    '<div class="kpi"><div class="kpi-lbl">Budget Mode</div><div class="kpi-val" style="font-size:16px">' + escapeHtml(today.degraded ? 'DEGRADED' : 'NORMAL') + '</div><div class="kpi-sub">' + escapeHtml(today.degraded_reason || 'hard risk controls stay active') + '</div></div>' +
    '</div>';

  html += '<div class="sec-hdr"><span class="sec-title">Scheduler Jobs</span><span class="sec-badge">' + jobRows.length + ' jobs</span></div>';
  html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
    '<th>Job</th><th>Status</th><th>Trigger</th><th class="r">Runs</th><th class="r">Skipped</th><th>Updated</th><th>Error</th>' +
    '</tr></thead><tbody>';
  html += jobRows.length ? jobRows.map(function(j) {
    var status = String(j.status || '').toUpperCase();
    var cls = status === 'SUCCESS' ? 'b-active' : (status === 'FAILED' ? 'b-rejected' : 'b-pending');
    return '<tr><td class="mono">' + escapeHtml(j.job_name || '') + '</td>' +
      '<td><span class="badge ' + cls + '">' + escapeHtml(status || 'UNKNOWN') + '</span></td>' +
      '<td>' + escapeHtml(j.trigger || '-') + '</td>' +
      '<td class="r">' + (j.run_count || 0) + '</td>' +
      '<td class="r">' + (j.skipped_count || 0) + '</td>' +
      '<td class="mono">' + escapeHtml(formatRelativeTime(j.updated_at)) + '</td>' +
      '<td style="max-width:300px;white-space:normal">' + escapeHtml(j.last_error || '-') + '</td></tr>';
  }).join('') : '<tr><td colspan="7" class="empty"><div class="empty-txt">No scheduler jobs recorded yet</div></td></tr>';
  html += '</tbody></table></div>';

  html += '<div class="sec-hdr"><span class="sec-title">Artefact Dependencies</span><span class="sec-badge">' + artifactRows.length + ' shown</span></div>';
  html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
    '<th>Owner</th><th>Kind</th><th>Status</th><th class="r">Age</th><th>Expires</th><th>Source Run</th>' +
    '</tr></thead><tbody>';
  html += artifactRows.length ? artifactRows.map(function(a) {
    var status = String(a.status || '').toUpperCase();
    var cls = (status === 'FRESH' && !a.is_expired) ? 'b-active' : (status === 'FAILED' || a.is_expired ? 'b-rejected' : 'b-pending');
    return '<tr><td class="mono">' + escapeHtml(a.owner || '') + '</td>' +
      '<td class="mono">' + escapeHtml(a.kind || '') + '</td>' +
      '<td><span class="badge ' + cls + '">' + escapeHtml(a.is_expired ? 'EXPIRED' : status) + '</span></td>' +
      '<td class="r">' + (a.age_seconds != null ? Math.round(Number(a.age_seconds)) + 's' : '—') + '</td>' +
      '<td class="mono">' + escapeHtml(formatRelativeTime(a.expires_at)) + '</td>' +
      '<td class="mono">' + escapeHtml(a.source_run_id || '-') + '</td></tr>';
  }).join('') : '<tr><td colspan="6" class="empty"><div class="empty-txt">No artefacts recorded yet</div></td></tr>';
  html += '</tbody></table></div>';

  html += '<div class="sec-hdr"><span class="sec-title">Recent Agent Runs</span><span class="sec-badge">' + runRows.length + ' shown</span></div>';
  html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
    '<th>Time</th><th>Pod</th><th>Agent</th><th>Task</th><th>Status</th><th class="r">Duration</th><th>Summary/Error</th>' +
    '</tr></thead><tbody>';
  html += runRows.length ? runRows.map(function(r) {
    var status = String(r.status || '').toUpperCase();
    var cls = status === 'SUCCESS' ? 'b-active' : (status === 'FAILED' || status === 'ERROR' ? 'b-rejected' : 'b-pending');
    var detail = r.error || r.output_summary || '';
    return '<tr><td class="mono">' + escapeHtml(formatRelativeTime(r.started_at)) + '</td>' +
      '<td class="mono">' + escapeHtml(r.pod_id || '-') + '</td>' +
      '<td class="mono">' + escapeHtml(r.agent_type || '') + '</td>' +
      '<td class="mono">' + escapeHtml(r.task || '') + '</td>' +
      '<td><span class="badge ' + cls + '">' + escapeHtml(status || 'UNKNOWN') + '</span></td>' +
      '<td class="r">' + (r.duration_ms != null ? Math.round(Number(r.duration_ms)) + ' ms' : '—') + '</td>' +
      '<td style="max-width:360px;white-space:normal">' + escapeHtml(detail || '-') + '</td></tr>';
  }).join('') : '<tr><td colspan="7" class="empty"><div class="empty-txt">No agent runs recorded yet</div></td></tr>';
  html += '</tbody></table></div>';
  return html;
}

function renderStateHealthFallback(el, reason) {
  var data = normalizeStateHealthData({}, reason);
  var podsData = data.pods || [];
  if (!podsData.length) {
    el.innerHTML = '<div class="empty"><div class="empty-txt">Could not load state health</div><div class="empty-hint">' + escapeHtml(reason || '') + '</div></div>';
    return;
  }
  var html = '<div class="broker-panel">' +
    '<div class="sec-hdr"><span class="sec-title">System Health</span><span class="badge b-pending">LOCAL SNAPSHOT</span>' +
    '<button class="export-btn" onclick="renderStateHealth()">Refresh</button></div>' +
    '<div class="broker-errors"><div>' + escapeHtml(reason || 'Health endpoint unavailable; showing latest dashboard snapshot') + '</div></div>' +
    '<div class="sec-hdr"><span class="sec-title">Pod State Integrity</span><span class="sec-badge">' + podsData.length + ' pods</span></div>' +
    '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr><th>Pod</th><th>Status</th><th class="r">Start Cap</th><th class="r">NAV</th><th class="r">Cash</th><th class="r">Invested</th><th class="r">Positions</th></tr></thead><tbody>';
  html += podsData.map(function(p) {
    return '<tr><td style="font-weight:600">' + escapeHtml(String(p.pod_id || '').toUpperCase()) + '</td>' +
      '<td><span class="badge ' + (p.status === 'OK' ? 'b-active' : 'b-pending') + '">' + escapeHtml(p.status || '') + '</span></td>' +
      '<td class="r">' + moneyOrDash(p.starting_capital) + '</td>' +
      '<td class="r">' + moneyOrDash(p.nav) + '</td>' +
      '<td class="r">' + moneyOrDash(p.cash) + '</td>' +
      '<td class="r">' + moneyOrDash(p.invested) + '</td>' +
      '<td class="r">' + (p.position_count || 0) + '</td></tr>';
  }).join('');
  html += '</tbody></table></div></div>';
  el.innerHTML = html;
}

function renderStateHealth() {
  var el = document.getElementById('state-health-panel');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="empty-txt">Checking state health…</div></div>';
  fetchJsonWithTimeout('/api/state-health', {}, 3500).then(function(data) {
    data = normalizeStateHealthData(data);
    var podsData = data.pods || [];
    var nav = data.nav_history || {};
    var broker = data.broker || {};
    var dq = data.data_quality || {};
    var fs = data.foresight || {};
    var specialists = data.specialists || {};
    var committee = data.committee_reviews || {};
    var statusCls = data.status === 'OK' ? 'b-active' : 'b-pending';
    var html = '<div class="broker-panel">';
    html += '<div class="sec-hdr"><span class="sec-title">System Health</span>' +
      '<span class="badge ' + statusCls + '">' + escapeHtml(data.status || 'UNKNOWN') + '</span>' +
      '<button class="export-btn" onclick="renderStateHealth()">Refresh</button></div>';
    html += '<div class="kpi-row">' +
      '<div class="kpi"><div class="kpi-lbl">Pod Capital</div><div class="kpi-val">' + moneyOrDash(data.capital_per_pod) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">NAV Rows</div><div class="kpi-val">' + (nav.total_rows || 0) + '</div><div class="kpi-sub">' + countText(nav.repaired_rows || 0, 'repaired row') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Broker Match</div><div class="kpi-val">' + escapeHtml(broker.status || 'UNKNOWN') + '</div><div class="kpi-sub">' + (broker.mismatch_count == null ? 'not checked' : countText(broker.mismatch_count, 'mismatch')) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Data Quality</div><div class="kpi-val">' + escapeHtml(dq.status || 'UNKNOWN') + '</div><div class="kpi-sub">' + countText(dq.check_count || 0, 'position flagged') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Catalysts</div><div class="kpi-val">' + (fs.event_count || 0) + '</div><div class="kpi-sub">' + countText((fs.counts || {}).stale || 0, 'stale') + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Specialists</div><div class="kpi-val">' + (specialists.brief_count || 0) + '</div><div class="kpi-sub">briefs</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">IC Reviews</div><div class="kpi-val">' + (committee.review_count || 0) + '</div><div class="kpi-sub">challenge records</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Last NAV</div><div class="kpi-val" style="font-size:14px">' + escapeHtml(formatEndDate(nav.last_ts)) + '</div><div class="kpi-sub">' + escapeHtml(formatTime(nav.last_ts)) + '</div></div>' +
      '</div>';
    var warnings = (data.warnings || []).concat(broker.errors || []);
    if (warnings.length) {
      html += '<div class="broker-errors">' + warnings.map(function(w) { return '<div>' + escapeHtml(w) + '</div>'; }).join('') + '</div>';
    }
    html += renderManagedRuntimePanel(data.managed_runtime || {});
    html += renderEvidenceReviewQueue(data.evidence_review);
    var dqRows = dq.positions || [];
    html += '<div class="sec-hdr"><span class="sec-title">Market Data Quality</span><span class="sec-badge">' + (dqRows.length || 0) + ' positions</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Pod</th><th>Symbol</th><th>Status</th><th class="r">Price</th><th>Source</th><th>Updated</th><th class="r">Current Notional</th><th>Issues</th>' +
      '</tr></thead><tbody>';
    if (!dqRows.length) {
      html += '<tr><td colspan="8" class="empty"><div class="empty-txt">No open positions to check</div></td></tr>';
    } else {
      html += dqRows.map(function(row) {
        var ok = row.status === 'OK';
        return '<tr>' +
          '<td style="font-weight:600">' + escapeHtml(String(row.pod_id || '').toUpperCase()) + '</td>' +
          '<td class="mono">' + escapeHtml(row.symbol || '') + '</td>' +
          '<td><span class="badge ' + (ok ? 'b-active' : 'b-pending') + '">' + escapeHtml(row.status || '') + '</span></td>' +
          '<td class="r">' + moneyOrDash(row.current_price) + '</td>' +
          '<td>' + escapeHtml(row.price_source || '-') + '</td>' +
          '<td class="mono">' + escapeHtml(formatRelativeTime(row.price_updated_at)) + '</td>' +
          '<td class="r">' + moneyOrDash(row.current_notional) + '</td>' +
          '<td>' + ((row.issues || []).length ? escapeHtml((row.issues || []).join('; ')) : '-') + '</td>' +
          '</tr>';
      }).join('');
    }
    html += '</tbody></table></div>';
    var dqFailures = dq.recent_failures || [];
    if (dqFailures.length) {
      html += '<div class="sec-hdr"><span class="sec-title">Recent Data Gate Blocks</span><span class="sec-badge">' + dqFailures.length + ' events</span></div>';
      html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
        '<th>Pod</th><th>Symbol</th><th>Side</th><th class="r">Price</th><th>Source</th><th>Checked</th><th>Issues</th>' +
        '</tr></thead><tbody>' + dqFailures.map(function(f) {
          return '<tr>' +
            '<td style="font-weight:600">' + escapeHtml(String(f.pod_id || '').toUpperCase()) + '</td>' +
            '<td class="mono">' + escapeHtml(f.symbol || '') + '</td>' +
            '<td>' + escapeHtml(f.side || '') + '</td>' +
            '<td class="r">' + moneyOrDash(f.price) + '</td>' +
            '<td>' + escapeHtml(f.price_source || '-') + '</td>' +
            '<td class="mono">' + escapeHtml(formatRelativeTime(f.checked_at)) + '</td>' +
            '<td>' + escapeHtml((f.issues || []).join('; ') || '-') + '</td>' +
            '</tr>';
        }).join('') + '</tbody></table></div>';
    }
    html += '<div class="sec-hdr"><span class="sec-title">Pod State Integrity</span><span class="sec-badge">' + podsData.length + ' pods</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Pod</th><th>Status</th><th>Trading Mode</th><th class="r">Start Cap</th><th class="r">NAV</th><th class="r">Cash</th><th class="r">Invested</th><th class="r">Positions</th><th>Last NAV</th><th>Issues</th>' +
      '</tr></thead><tbody>';
    if (!podsData.length) {
      html += '<tr><td colspan="10" class="empty"><div class="empty-txt">No pod health data yet</div></td></tr>';
    } else {
      html += podsData.map(function(p) {
        var ok = p.status === 'OK';
        var tradingMode = String(p.trading_mode || 'normal').replace(/_/g, ' ').toUpperCase();
        var tradingReason = p.trading_block_reason || '';
        var modeCls = tradingMode === 'NORMAL' ? 'b-active' : 'b-pending';
        return '<tr>' +
          '<td style="font-weight:600">' + escapeHtml(String(p.pod_id || '').toUpperCase()) + '</td>' +
          '<td><span class="badge ' + (ok ? 'b-active' : 'b-pending') + '">' + escapeHtml(p.status || '') + '</span></td>' +
          '<td><span class="badge ' + modeCls + '" title="' + escapeHtml(tradingReason) + '">' + escapeHtml(tradingMode) + '</span></td>' +
          '<td class="r">' + moneyOrDash(p.starting_capital) + '</td>' +
          '<td class="r">' + moneyOrDash(p.nav) + '</td>' +
          '<td class="r">' + moneyOrDash(p.cash) + '</td>' +
          '<td class="r">' + moneyOrDash(p.invested) + '</td>' +
          '<td class="r">' + (p.position_count || 0) + '</td>' +
          '<td class="mono">' + escapeHtml(formatRelativeTime(p.last_nav_ts)) + '</td>' +
          '<td>' + ((p.issues || []).length ? escapeHtml((p.issues || []).join('; ')) : '—') + '</td>' +
          '</tr>';
      }).join('');
    }
    html += '</tbody></table></div>';
    html += '</div>';
    el.innerHTML = html;
  }).catch(function(err) {
    renderStateHealthFallback(el, err && err.message ? err.message : 'Could not load state health');
  });
}

function localBrokerPositionRows() {
  var rowsBySymbol = {};
  var localPositions = (_positionsFromApi && _positionsFromApi.length) ? _positionsFromApi.slice() : [];
  if (!localPositions.length) {
    Object.keys(pods || {}).forEach(function(pid) {
      getPodPositions(pods[pid] || {}).forEach(function(p) {
        localPositions.push(Object.assign({}, p, { _pod: pid }));
      });
    });
  }
  localPositions.forEach(function(p) {
    var symbol = p.symbol || '';
    if (!symbol) return;
    var qty = Number(p.qty || 0);
    var price = Number(p.current_price || p.price || 0);
    var row = rowsBySymbol[symbol] || {
      symbol: symbol,
      status: 'LOCAL_ONLY',
      local_qty: 0,
      broker_qty: 0,
      qty_delta: -qty,
      local_notional: 0,
      pods: [],
    };
    row.local_qty += qty;
    row.local_notional += Math.abs(qty * price);
    row.pods.push({
      pod_id: p._pod || p.pod_id || '',
      qty: qty,
      current_price: price,
      notional: Math.abs(qty * price),
    });
    rowsBySymbol[symbol] = row;
  });
  return Object.keys(rowsBySymbol).sort().map(function(k) {
    var row = rowsBySymbol[k];
    row.qty_delta = Number(row.broker_qty || 0) - Number(row.local_qty || 0);
    return row;
  });
}

function renderBrokerReconciliationFallback(el, reason) {
  var positions = localBrokerPositionRows();
  var diagnostics = recentExecutionDiagnostics(12);
  if (!positions.length && !diagnostics.length) {
    el.innerHTML = '<div class="empty"><div class="empty-txt">Could not load broker reconciliation</div><div class="empty-hint">' + escapeHtml(reason || '') + '</div></div>';
    return;
  }
  var html = '<div class="broker-panel">' +
    '<div class="sec-hdr"><span class="sec-title">Broker Reconciliation</span><span class="badge b-pending">LOCAL SNAPSHOT</span>' +
    '<button class="export-btn" onclick="renderBrokerReconciliation()">Refresh</button></div>' +
    '<div class="broker-errors"><div>' + escapeHtml(reason || 'Broker reconciliation unavailable; showing local dashboard state') + '</div></div>' +
    '<div class="sec-hdr"><span class="sec-title">Position Match</span><span class="sec-badge">' + positions.length + ' local</span></div>' +
    '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr><th>Symbol</th><th>Status</th><th class="r">Local Qty</th><th class="r">Broker Qty</th><th class="r">Delta</th><th>Pods</th></tr></thead><tbody>';
  if (!positions.length) {
    html += '<tr><td colspan="6" class="empty"><div class="empty-txt">No local positions loaded yet</div></td></tr>';
  } else {
    html += positions.map(function(p) {
      var podsTxt = (p.pods || []).map(function(pp) {
        return (pp.pod_id || '').toUpperCase() + ' ' + Number(pp.qty || 0).toFixed(4);
      }).join(', ');
      return '<tr><td style="font-weight:600">' + tickerDisplay(p.symbol || '') + '</td>' +
        '<td><span class="badge b-pending">' + escapeHtml(p.status || 'LOCAL_ONLY') + '</span></td>' +
        '<td class="r">' + Number(p.local_qty || 0).toFixed(4) + '</td>' +
        '<td class="r">—</td><td class="r">—</td><td>' + (podsTxt ? escapeHtml(podsTxt) : '—') + '</td></tr>';
    }).join('');
  }
  html += '</tbody></table></div>';
  html += '<div class="sec-hdr"><span class="sec-title">Recent Execution Diagnostics</span><span class="sec-badge">' + diagnostics.length + ' item' + (diagnostics.length === 1 ? '' : 's') + '</span></div>' +
    '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr><th>Pod</th><th>Symbol</th><th>Status</th><th>Stage</th><th>Reason</th><th>Next Action</th></tr></thead><tbody>';
  html += diagnostics.length ? diagnostics.map(function(d) {
    var ss = d.status === 'REJECTED' ? 'b-rejected' : d.status === 'PENDING' ? 'b-pending' : 'b-partial';
    return '<tr><td>' + escapeHtml(String(d.pod_id || '').toUpperCase()) + '</td><td style="font-weight:600">' + tickerDisplay(d.symbol || '') + '</td>' +
      '<td><span class="badge ' + ss + '">' + escapeHtml(d.status || '') + '</span></td><td class="exec-stage">' + escapeHtml((d.stage || '—').replace(/_/g, ' ')) + '</td>' +
      '<td><span class="exec-reason" title="' + escapeHtml(d.reason || '') + '">' + escapeHtml(d.reason || '—') + '</span></td><td>' + escapeHtml(orderDiagnosticAction(d)) + '</td></tr>';
  }).join('') : '<tr><td colspan="6" class="empty"><div class="empty-txt">No rejected or pending diagnostics</div></td></tr>';
  html += '</tbody></table></div></div>';
  el.innerHTML = html;
}

function renderBrokerReconciliation() {
  var el = document.getElementById('broker-reconciliation-panel');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="empty-txt">Reconciling with Alpaca…</div></div>';
  Promise.all([
    fetchJsonWithTimeout('/api/broker-reconciliation', {}, 4500),
    reconcileExecutionOrders().catch(function() { return { updates: [], errors: ['Order reconciliation failed'] }; })
  ]).then(function(results) {
    var data = results[0] || {};
    var exec = results[1] || {};
    var acct = data.account || {};
    var mismatches = data.mismatches || [];
    var positions = data.positions || [];
    if (!positions.length && _positionsFromApi && _positionsFromApi.length) {
      positions = localBrokerPositionRows();
      errors.push('Broker reconciliation endpoint returned no positions; showing local dashboard positions only');
    }
    var openOrders = data.open_orders || [];
    var errors = (data.errors || []).concat(exec.errors || []);
    var statusClass = data.status === 'OK' && !errors.length ? 'b-active' : 'b-rejected';
    var statusText = data.status === 'OK' && !errors.length ? 'IN SYNC' : 'CHECK';

    var html = '<div class="broker-panel">';
    html += '<div class="sec-hdr"><span class="sec-title">Broker Reconciliation</span>' +
      '<span class="badge ' + statusClass + '">' + statusText + '</span>' +
      '<button class="export-btn" onclick="renderBrokerReconciliation()">Refresh</button></div>';
    html += '<div class="kpi-row">' +
      '<div class="kpi"><div class="kpi-lbl">Broker Equity</div><div class="kpi-val">' + moneyOrDash(acct.equity) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Buying Power</div><div class="kpi-val">' + moneyOrDash(acct.buying_power) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Broker Positions</div><div class="kpi-val">' + (acct.position_count != null ? acct.position_count : positions.length) + '</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">Order Updates</div><div class="kpi-val">' + ((exec.updates || []).length || 0) + '</div><div class="kpi-sub">reconciled now</div></div>' +
      '</div>';

    if (errors.length) {
      html += '<div class="broker-errors">' + errors.map(function(e) {
        return '<div>' + escapeHtml(e) + '</div>';
      }).join('') + '</div>';
    }

    html += '<div class="sec-hdr"><span class="sec-title">Position Match</span><span class="sec-badge">' + mismatches.length + ' mismatch' + (mismatches.length === 1 ? '' : 'es') + '</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Symbol</th><th>Status</th><th class="r">Local Qty</th><th class="r">Broker Qty</th><th class="r">Delta</th><th>Pods</th>' +
      '</tr></thead><tbody>';
    if (!positions.length) {
      html += '<tr><td colspan="6" class="empty"><div class="empty-txt">No local or broker positions</div></td></tr>';
    } else {
      html += positions.map(function(p) {
        var ok = p.status === 'OK';
        var podsTxt = (p.pods || []).map(function(pp) {
          return (pp.pod_id || '').toUpperCase() + ' ' + Number(pp.qty || 0).toFixed(4);
        }).join(', ');
        return '<tr>' +
          '<td style="font-weight:600">' + tickerDisplay(p.symbol || '') + '</td>' +
          '<td><span class="badge ' + (ok ? 'b-active' : 'b-rejected') + '">' + escapeHtml(p.status || '') + '</span></td>' +
          '<td class="r">' + Number(p.local_qty || 0).toFixed(4) + '</td>' +
          '<td class="r">' + Number(p.broker_qty || 0).toFixed(4) + '</td>' +
          '<td class="r ' + (ok ? '' : 'neg') + '">' + Number(p.qty_delta || 0).toFixed(4) + '</td>' +
          '<td>' + (podsTxt ? escapeHtml(podsTxt) : '—') + '</td>' +
          '</tr>';
      }).join('');
    }
    html += '</tbody></table></div>';

    var diagnostics = recentExecutionDiagnostics(12);
    html += '<div class="sec-hdr"><span class="sec-title">Recent Execution Diagnostics</span><span class="sec-badge">' + diagnostics.length + ' item' + (diagnostics.length === 1 ? '' : 's') + '</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Pod</th><th>Symbol</th><th>Status</th><th>Stage</th><th>Reason</th><th>Next Action</th>' +
      '</tr></thead><tbody>';
    if (!diagnostics.length) {
      html += '<tr><td colspan="6" class="empty"><div class="empty-txt">No rejected or pending diagnostics</div></td></tr>';
    } else {
      html += diagnostics.map(function(d) {
        var ss = d.status === 'REJECTED' ? 'b-rejected' : d.status === 'PENDING' ? 'b-pending' : 'b-partial';
        return '<tr>' +
          '<td>' + escapeHtml(String(d.pod_id || '').toUpperCase()) + '</td>' +
          '<td style="font-weight:600">' + tickerDisplay(d.symbol || '') + '</td>' +
          '<td><span class="badge ' + ss + '">' + escapeHtml(d.status || '') + '</span></td>' +
          '<td class="exec-stage">' + escapeHtml((d.stage || '—').replace(/_/g, ' ')) + '</td>' +
          '<td><span class="exec-reason" title="' + escapeHtml(d.reason || '') + '">' + escapeHtml(d.reason || '—') + '</span></td>' +
          '<td>' + escapeHtml(orderDiagnosticAction(d)) + '</td>' +
          '</tr>';
      }).join('');
    }
    html += '</tbody></table></div>';

    html += '<div class="sec-hdr"><span class="sec-title">Broker Open Orders</span><span class="sec-badge">' + openOrders.length + ' open</span></div>';
    html += '<div class="tbl-wrap broker-table-wrap"><table class="dtbl"><thead><tr>' +
      '<th>Order</th><th>Symbol</th><th>Side</th><th class="r">Qty</th><th>Status</th><th>Submitted</th>' +
      '</tr></thead><tbody>';
    if (!openOrders.length) {
      html += '<tr><td colspan="6" class="empty"><div class="empty-txt">No open broker orders</div></td></tr>';
    } else {
      html += openOrders.map(function(o) {
        return '<tr>' +
          '<td class="mono">' + escapeHtml(String(o.order_id || '').slice(0, 12)) + '</td>' +
          '<td style="font-weight:600">' + tickerDisplay(o.symbol || '') + '</td>' +
          '<td><span class="badge ' + (String(o.side || '').toUpperCase() === 'BUY' ? 'b-buy' : 'b-sell') + '">' + escapeHtml(String(o.side || '').toUpperCase()) + '</span></td>' +
          '<td class="r">' + Number(o.qty || 0).toFixed(4) + '</td>' +
          '<td><span class="badge b-pending">' + escapeHtml(o.status || '') + '</span></td>' +
          '<td>' + escapeHtml(String(o.submitted_at || '—')) + '</td>' +
          '</tr>';
      }).join('');
    }
    html += '</tbody></table></div></div>';
    el.innerHTML = html;
  }).catch(function(err) {
    renderBrokerReconciliationFallback(el, err && err.message ? err.message : 'Could not load broker reconciliation');
  });
}

function localDecisionAuditItems(limit) {
  var items = [];
  (activityFeed || []).forEach(function(a) {
    var action = a.action || '';
    if (action && [
      'trade_decision', 'thesis_verification', 'thesis_review', 'position_review',
      'mandate_update', 'allocation', 'quality_gate_warning', 'thesis_gate_failed',
      'thesis_challenged', 'thesis_revised', 'data_quality_gate_failed',
      'loss_review_gate_failed', 'broker_guard_blocked', 'evidence_review_required',
      'evidence_review_blocked'
    ].indexOf(action) === -1) return;
    items.push({
      ts: a.ts || a.timestamp || '',
      pod_id: a.pod_id || '',
      stage: action || 'agent_activity',
      agent: a.agent_role || a.agent_id || '',
      symbol: a.symbol || '',
      decision: a.summary || '',
      detail: a.detail || '',
      status: a.status || 'INFO',
      reason: a.reason || '',
    });
  });
  Object.keys(orderBook || {}).forEach(function(oid) {
    var o = orderBook[oid] || {};
    items.push({
      ts: o.ts || o.timestamp || o.submitted_at || '',
      pod_id: o.pod_id || o.podId || '',
      stage: o.stage || 'execution',
      agent: 'execution',
      symbol: o.symbol || '',
      decision: ((o.side || '') + ' ' + (o.qty || o.quantity || '')).trim(),
      detail: o.reason || o.rejection_reason || o.rejection_detail || '',
      status: String(o.status || 'INFO').toUpperCase(),
      reason: o.reason || o.rejection_reason || o.rejection_detail || '',
      order_id: oid,
    });
  });
  (executedTrades || []).forEach(function(t) {
    items.push({
      ts: t.ts || t.timestamp || '',
      pod_id: t.podId || t.pod_id || '',
      stage: 'execution_fill',
      agent: 'execution',
      symbol: t.symbol || '',
      decision: ((t.side || '') + ' ' + (t.qty || '')).trim(),
      detail: 'Filled at ' + (t.price || t.fill_price || ''),
      status: String(t.status || 'FILLED').toUpperCase(),
      reason: '',
      order_id: t.orderId || t.order_id || '',
    });
  });
  items.sort(function(a, b) { return String(b.ts || '').localeCompare(String(a.ts || '')); });
  return items.slice(0, limit || 80);
}

function executionTruthBadgeClass(status) {
  status = String(status || '').toUpperCase();
  if (status === 'REJECTED' || status === 'BLOCKED' || status === 'FAILED' || status === 'FAIL') return 'b-rejected';
  if (status === 'PENDING' || status === 'PROPOSED' || status === 'PARTIAL' || status === 'WARN' || status === 'WATCH' || status === 'ACTIVE' || status === 'REDUCE_ONLY' || status === 'GUARDED' || status === 'REVIEW_REQUIRED') return 'b-pending';
  if (status === 'FILLED' || status === 'PASS' || status === 'OK' || status === 'RECORDED') return 'b-filled';
  return 'b-active';
}

function renderExecutionTruthPanel(rows) {
  rows = rows || [];
  var html = '<div style="margin-bottom:12px">' +
    '<div class="sec-hdr"><span class="sec-title">Execution Truth</span>' +
    '<span class="sec-badge">' + rows.length + ' pod' + (rows.length === 1 ? '' : 's') + '</span></div>';
  if (!rows.length) {
    return html + '<div class="empty"><div class="empty-txt">No execution truth snapshot yet</div></div></div>';
  }
  html += '<div class="tbl-wrap"><table class="dtbl"><thead><tr>' +
    '<th>Pod</th><th>Status</th><th>PM Decision</th><th>Gate / Stage</th><th>Reason</th><th>Last Order</th>' +
    '</tr></thead><tbody>';
  html += rows.map(function(row) {
    var status = String(row.status || 'UNKNOWN').toUpperCase();
    var gateBits = [];
    if (row.thesis_gate && row.thesis_gate.passed === false) gateBits.push('thesis failed');
    if (row.quality_gate && row.quality_gate.action && row.quality_gate.action !== 'pass') {
      gateBits.push('quality ' + row.quality_gate.action);
    }
    if (row.data_gate && row.data_gate.passed === false) gateBits.push('data failed');
    if (row.evidence_guard && row.evidence_guard.blocked_count) gateBits.push('evidence review ' + row.evidence_guard.blocked_count);
    var stage = gateBits.length ? gateBits.join(', ') : (row.stage || '—');
    var order = row.last_order_result || {};
    var orderText = order.symbol
      ? (tickerDisplay(order.symbol) + ' ' + escapeHtml(order.side || '') + ' ' + escapeHtml(order.qty || '') + ' ' + escapeHtml(order.status || ''))
      : '—';
    var symbols = (row.active_symbols || []).map(tickerDisplay).join(', ');
    var pmText = row.pm_summary || (symbols ? 'Active: ' + symbols : 'No active trade');
    var modelText = row.quality_gate && row.quality_gate.llm && row.quality_gate.llm.model
      ? ' · ' + row.quality_gate.llm.provider + '/' + row.quality_gate.llm.model
      : '';
    return '<tr>' +
      '<td><b>' + escapeHtml(String(row.pod_id || '').toUpperCase()) + '</b></td>' +
      '<td><span class="badge ' + executionTruthBadgeClass(status) + '">' + escapeHtml(status.replace(/_/g, ' ')) + '</span></td>' +
      '<td>' + escapeHtml(pmText + modelText) + '</td>' +
      '<td>' + escapeHtml(String(stage).replace(/_/g, ' ')) + '</td>' +
      '<td style="max-width:320px;white-space:normal">' + escapeHtml(row.reason || '—') + '</td>' +
      '<td>' + orderText + '</td>' +
      '</tr>';
  }).join('');
  return html + '</tbody></table></div></div>';
}

function renderDecisionAudit() {
  var el = document.getElementById('decision-audit-panel');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="empty-txt">Loading decision audit…</div></div>';
  fetchJsonWithTimeout('/api/decision-audit?limit=80', {}, 3500).then(function(data) {
    var items = data.items || [];
    if (!items.length) items = localDecisionAuditItems(80);
    var truthRows = data.execution_truth && data.execution_truth.pods ? data.execution_truth.pods : [];
    var html = '<div class="broker-panel">';
    html += '<div class="sec-hdr"><span class="sec-title">Decision Audit Trail</span>' +
      '<span class="sec-badge">' + items.length + ' event' + (items.length === 1 ? '' : 's') + '</span>' +
      '<button class="export-btn" onclick="renderDecisionAudit()">Refresh</button></div>';
    html += renderExecutionTruthPanel(truthRows);
    html += '<div class="audit-list">';
    if (!items.length) {
      html += '<div class="empty"><div class="empty-txt">No decision events yet</div></div>';
    } else {
      html += items.map(function(item) {
        var status = String(item.status || 'INFO').toUpperCase();
        var cls = status === 'REJECTED' ? 'b-rejected' : status === 'FILLED' ? 'b-filled' : status === 'PENDING' ? 'b-pending' : 'b-active';
        var pod = item.pod_id ? String(item.pod_id).toUpperCase() : 'FIRM';
        var detail = item.detail || item.reason || '';
        var modelMeta = item.model ? item.provider + '/' + item.model + (item.task ? ' · ' + item.task : '') : '';
        return '<div class="audit-card">' +
          '<div class="audit-card-head">' +
            '<span class="badge ' + cls + '">' + escapeHtml(status) + '</span>' +
            '<span class="audit-stage">' + escapeHtml((item.stage || 'event').replace(/_/g, ' ')) + '</span>' +
            '<span class="audit-pod">' + escapeHtml(pod) + '</span>' +
            (item.symbol ? '<span class="audit-symbol">' + tickerDisplay(item.symbol) + '</span>' : '') +
            (modelMeta ? '<span class="audit-model">' + escapeHtml(modelMeta) + '</span>' : '') +
            '<span class="audit-time">' + escapeHtml(formatRelativeTime(item.ts)) + '</span>' +
          '</div>' +
          '<div class="audit-decision">' + escapeHtml(item.decision || '—') + '</div>' +
          (detail ? '<div class="audit-detail">' + escapeHtml(detail) + '</div>' : '') +
          '</div>';
      }).join('');
    }
    html += '</div></div>';
    el.innerHTML = html;
  }).catch(function(err) {
    var items = localDecisionAuditItems(80);
    if (!items.length) {
      el.innerHTML = '<div class="empty"><div class="empty-txt">Could not load decision audit</div></div>';
      return;
    }
    var html = '<div class="broker-panel"><div class="sec-hdr"><span class="sec-title">Decision Audit Trail</span>' +
      '<span class="sec-badge">' + items.length + ' local event' + (items.length === 1 ? '' : 's') + '</span>' +
      '<button class="export-btn" onclick="renderDecisionAudit()">Refresh</button></div>' +
      '<div class="broker-errors"><div>' + escapeHtml(err && err.message ? err.message : 'Decision audit endpoint unavailable; showing local dashboard events') + '</div></div>' +
      '<div class="audit-list">';
    html += items.map(function(item) {
      var status = String(item.status || 'INFO').toUpperCase();
      var cls = status === 'REJECTED' ? 'b-rejected' : status === 'FILLED' ? 'b-filled' : status === 'PENDING' ? 'b-pending' : 'b-active';
      var pod = item.pod_id ? String(item.pod_id).toUpperCase() : 'FIRM';
      var detail = item.detail || item.reason || '';
      var modelMeta = item.model ? item.provider + '/' + item.model + (item.task ? ' · ' + item.task : '') : '';
      return '<div class="audit-card"><div class="audit-card-head">' +
        '<span class="badge ' + cls + '">' + escapeHtml(status) + '</span>' +
        '<span class="audit-stage">' + escapeHtml((item.stage || 'event').replace(/_/g, ' ')) + '</span>' +
        '<span class="audit-pod">' + escapeHtml(pod) + '</span>' +
        (item.symbol ? '<span class="audit-symbol">' + tickerDisplay(item.symbol) + '</span>' : '') +
        (modelMeta ? '<span class="audit-model">' + escapeHtml(modelMeta) + '</span>' : '') +
        '<span class="audit-time">' + escapeHtml(formatRelativeTime(item.ts)) + '</span></div>' +
        '<div class="audit-decision">' + escapeHtml(item.decision || '—') + '</div>' +
        (detail ? '<div class="audit-detail">' + escapeHtml(detail) + '</div>' : '') + '</div>';
    }).join('');
    el.innerHTML = html + '</div></div>';
  });
}

function renderOpsOverview() {
  var cards = document.getElementById('pod-strategy-cards');
  var feed = document.getElementById('live-thesis-feed');
  var reg = document.getElementById('regime-overview');
  if (!cards || !feed || !reg) return;
  var ids = Object.keys(pods).sort();
  cards.innerHTML = ids.map(function(id) {
    var d = pods[id] || {};
    var nav = d.nav || 0;
    var pm = d.performance_metrics || {};
    var wr = pm.max_drawdown != null ? 'DD ' + (pm.max_drawdown * 100).toFixed(0) + '%' : '—';
    var posc = (d.current_positions && d.current_positions.length) ? d.current_positions.length : 0;
    var act = '—';
    var ag = agentActivity[id + '_pm'] || agentActivity[id + '.pm'];
    if (ag && ag[0]) act = (ag[0].summary || '').slice(0, 80);
    return '<div class="kpi" style="min-width:140px"><div class="kpi-lbl">' + id.toUpperCase() + '</div>' +
      '<div class="kpi-val">$' + nav.toFixed(0) + '</div>' +
      '<div class="kpi-sub">' + wr + ' · ' + posc + ' pos</div>' +
      '<div class="kpi-sub" style="font-size:9px">' + escapeHtml(act) + '</div></div>';
  }).join('');
  feed.innerHTML = '<div class="sec-hdr"><span class="sec-title">Latest PM activity</span></div>' +
    activityFeed.slice(0, 12).map(function(a) {
      if ((a.agent_role || '').indexOf('PM') === -1 && (a.agent_id || '').indexOf('pm') === -1) return '';
      return '<div style="font-size:10px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.06)"><b>' +
        escapeHtml(a.pod_id || '') + '</b> ' + escapeHtml(a.summary || '') +
        (a.detail ? '<div style="color:var(--text-muted);white-space:pre-wrap;max-height:120px;overflow-y:auto">' +
        escapeHtml(a.detail) + '</div>' : '') + '</div>';
    }).join('') || '<div class="empty-txt">No PM feed yet</div>';
  reg.innerHTML = ids.map(function(id) {
    var d = pods[id] || {};
    var mr = d.macro_regime || (d.features && d.features.macro_outlook) || '—';
    return '<div style="font-size:11px;margin-bottom:6px"><b>' + id.toUpperCase() + '</b> regime: ' + escapeHtml(String(mr)) + '</div>';
  }).join('');
}

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
  if (name === 'social') {
    fetchResearchFeedAudit(false).then(function() {
      renderNewsFeed();
    }).catch(function() {});
  }
  if (name === 'feed-health') {
    renderResearchFeedAudit();
  }
  if (name === 'foresight') {
    renderForesightLedger();
  }
}
document.querySelectorAll('.sub-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchResearchSubTab(btn.dataset.subtab));
});

// ─── 4. WebSocket ────────────────────────────────────────────────────────
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
var ws = null;
var backendReachableAt = 0;
var snapshotFallbackInflight = false;

function wsIsOpen() {
  return ws && ws.readyState === WebSocket.OPEN;
}

function setConn(on) {
  const dot = document.getElementById('conn-dot');
  const lbl = document.getElementById('conn-label');
  if (!dot || !lbl) return;
  dot.classList.toggle('on', on);
  lbl.classList.toggle('on', on);
  lbl.textContent = on ? 'CONNECTED' : 'DISCONNECTED';
}

function updateIterationDisplay(data) {
  var sd = data || {};
  if (sd.iteration != null) iterCount = sd.iteration;
  var iterEl = document.getElementById('iter-ctr');
  if (iterEl) iterEl.textContent = (iterCount || iterCount === 0) ? iterCount : '—';

  var stageEl = document.getElementById('iter-stage');
  if (!stageEl) return;
  var detail = sd.stage_detail || sd.stage || '';
  if (!detail || detail === 'Idle') {
    stageEl.textContent = '';
    stageEl.title = 'Current session stage';
    return;
  }
  stageEl.textContent = '- ' + detail;
  stageEl.title = detail + (sd.stage_updated_at ? ' @ ' + sd.stage_updated_at : '');
}

function applyBackendStatus(data) {
  var sd = data || {};
  backendReachableAt = Date.now();
  setConn(true);
  updateSessionStatus(!!sd.active);
  updateIterationDisplay(sd);
}

function fetchSnapshotFallback(force) {
  if (!force && wsIsOpen()) return;
  if (snapshotFallbackInflight) return;
  snapshotFallbackInflight = true;
  fetchJsonWithTimeout('/api/session/snapshot', {}, 4500)
    .then(function(snapshot) {
      backendReachableAt = Date.now();
      setConn(true);
      handleMessage(snapshot);
    })
    .catch(function(err) {
      if (!wsIsOpen()) console.warn('[dashboard] session snapshot fallback failed', err);
    })
    .finally(function() {
      snapshotFallbackInflight = false;
    });
}

function pollSessionStatus() {
  fetchJsonWithTimeout('/api/session/status', {}, 3500)
    .then(function(data) {
      applyBackendStatus(data);
      if (!wsIsOpen()) fetchSnapshotFallback(false);
    })
    .catch(function(err) {
      if (!wsIsOpen() && Date.now() - backendReachableAt > 6000) {
        setConn(false);
      }
      console.warn('[dashboard] session status poll failed', err);
    });
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    backendReachableAt = Date.now();
    setConn(true);
  };
  ws.onclose = () => {
    if (Date.now() - backendReachableAt > 6000) setConn(false);
    setTimeout(connect, 3000);
    pollSessionStatus();
  };
  ws.onerror = () => {
    try { ws.close(); } catch(e) {}
    pollSessionStatus();
  };
  ws.onmessage = ev => {
    try {
      backendReachableAt = Date.now();
      setConn(true);
      handleMessage(JSON.parse(ev.data));
    } catch(e) {
      console.error(e);
      fetchSnapshotFallback(true);
    }
  };
}
connect();
pollSessionStatus();
setInterval(pollSessionStatus, 3000);

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

  tbody.innerHTML = signals.map((s, i) => {
    const q = s.question || s.market || JSON.stringify(s);
    const marketId = marketHistoryKey(s) || q;
    const prevProb = previousMarketProbability(marketId, s.timestamp || new Date().toISOString());
    const delta = formatDelta(s.implied_prob, prevProb);
    const rowId = 'poly-row-' + i;
    return '<tr class="poly-market-row" data-rowid="' + rowId + '" style="cursor:pointer">' +
      '<td><span class="poly-q-short">' + truncate(q, 40) + '</span>' +
      '<span class="poly-q-full" id="' + rowId + '" style="display:none;white-space:normal;word-break:break-word;color:var(--text-primary)">' + escapeHtml(q) + '</span></td>' +
      '<td class="num">' + statusBadge(s.status || 'Active') + '</td>' +
      '<td class="num">' + (s.yes_price != null ? s.yes_price.toFixed(2) : '—') + '</td>' +
      '<td class="num">' + (s.no_price != null ? s.no_price.toFixed(2) : '—') + '</td>' +
      '<td class="num accent">' + formatPct(s.implied_prob) + '</td>' +
      '<td class="num">' + delta + '</td>' +
      '<td class="num">' + formatVol(s.volume_24h) + '</td>' +
      '<td class="num">' + formatEndDate(s.end_date) + '</td>' +
      '</tr>';
  }).join('');

  // Click handler: toggle full question text
  tbody.querySelectorAll('.poly-market-row').forEach(function(row) {
    row.addEventListener('click', function() {
      var rowId = row.dataset.rowid;
      var shortEl = row.querySelector('.poly-q-short');
      var fullEl = document.getElementById(rowId);
      if (!shortEl || !fullEl) return;
      var isExpanded = fullEl.style.display !== 'none';
      shortEl.style.display = isExpanded ? '' : 'none';
      fullEl.style.display = isExpanded ? 'none' : '';
      row.style.background = isExpanded ? '' : 'var(--bg-elevated)';
    });
  });
}

const COLORS = ['#00cfe8', '#f0a030', '#00c888', '#7c5cfc', '#e84040'];
const MAX_MARKETS = 5;
const BUCKET_MS = 4 * 60 * 60 * 1000;
const WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

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
    if (!bucketed[bucket]) bucketed[bucket] = { ts: bucket, byId: {} };
    (e.signals || []).forEach(function(sig) {
      var id = marketHistoryKey(sig);
      if (id) bucketed[bucket].byId[id] = sig;
    });
  });

  const buckets = Object.keys(bucketed).map(Number).sort((a, b) => a - b);
  const latestByMarket = {};
  buckets.forEach(function(b) {
    Object.keys(bucketed[b].byId || {}).forEach(function(id) {
      latestByMarket[id] = bucketed[b].byId[id];
    });
  });
  const latestSignals = Object.keys(latestByMarket)
    .map(function(id) { return latestByMarket[id]; })
    .sort(function(a, b) {
      return (b.volume_24h || 0) - (a.volume_24h || 0) || (b.implied_prob || 0) - (a.implied_prob || 0);
    })
    .slice(0, MAX_MARKETS);

  const topIds = latestSignals.map(s => marketHistoryKey(s) || JSON.stringify(s));
  const labels = buckets.map(b => new Date(b).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }));

  const datasets = topIds.map((id, i) => {
    const market = latestSignals[i];
    const data = buckets.map(b => {
      const entry = bucketed[b];
      const sig = (entry && entry.byId) ? entry.byId[id] : null;
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
  if (countEl) countEl.textContent = flattenedSignalHistory().length;
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
  recent.forEach((entry, entryIdx) => {
    const top5 = [...(entry.signals || [])]
      .sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0))
      .slice(0, 5);
    top5.forEach((sig, i) => {
      const hRowId = 'hist-row-' + entryIdx + '-' + i;
      rows.push('<tr class="poly-market-row" data-rowid="' + hRowId + '" style="cursor:pointer">' +
        '<td class="num">' + (i === 0 ? formatTime(entry.ts) : '') + '</td>' +
        '<td><span class="poly-q-short">' + truncate(sig.question, 35) + '</span>' +
        '<span class="poly-q-full" id="' + hRowId + '" style="display:none;white-space:normal;word-break:break-word;color:var(--text-primary)">' + escapeHtml(sig.question || '') + '</span></td>' +
        '<td class="num accent">' + formatPct(sig.implied_prob) + '</td>' +
        '</tr>');
    });
    rows.push('<tr style="height:4px"><td colspan="3" style="border-bottom:1px solid var(--border-dim)"></td></tr>');
  });

  tbody.innerHTML = rows.join('');

  // Click handler: toggle full question text
  tbody.querySelectorAll('.poly-market-row').forEach(function(row) {
    row.addEventListener('click', function() {
      var rowId = row.dataset.rowid;
      var shortEl = row.querySelector('.poly-q-short');
      var fullEl = document.getElementById(rowId);
      if (!shortEl || !fullEl) return;
      var isExpanded = fullEl.style.display !== 'none';
      shortEl.style.display = isExpanded ? '' : 'none';
      fullEl.style.display = isExpanded ? 'none' : '';
      row.style.background = isExpanded ? '' : 'var(--bg-elevated)';
    });
  });
}

function renderHistoryTableV2() {
  const tbody = document.getElementById('history-body');
  if (!tbody) return;

  const historyRows = flattenedSignalHistory();
  if (!historyRows.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No history yet - waiting for first cycle</td></tr>';
    return;
  }

  const rows = historyRows.slice(-80).reverse().map(function(row, idx) {
    const sig = row.signal || {};
    const hRowId = 'hist-row-v2-' + idx;
    const q = sig.question || sig.market || '';
    const prevProb = previousMarketProbability(row.id, row.ts);
    const delta = formatDelta(sig.implied_prob, prevProb);
    return '<tr class="poly-market-row" data-rowid="' + hRowId + '" style="cursor:pointer">' +
      '<td class="num">' + formatTime(row.ts) + '</td>' +
      '<td><span class="poly-q-short">' + escapeHtml(truncate(q, 76)) + '</span>' +
      '<span class="poly-q-full" id="' + hRowId + '" style="display:none;white-space:normal;word-break:break-word;color:var(--text-primary)">' + escapeHtml(q) + '</span></td>' +
      '<td class="num">' + statusBadge(sig.status || 'Active') + '</td>' +
      '<td class="num accent">' + formatPct(sig.implied_prob) + '</td>' +
      '<td class="num">' + delta + '</td>' +
      '<td class="num">' + formatVol(sig.volume_24h) + '</td>' +
      '<td class="num">' + formatEndDate(sig.end_date) + '</td>' +
      '</tr>';
  });

  tbody.innerHTML = rows.join('');

  tbody.querySelectorAll('.poly-market-row').forEach(function(row) {
    row.addEventListener('click', function() {
      var rowId = row.dataset.rowid;
      var shortEl = row.querySelector('.poly-q-short');
      var fullEl = document.getElementById(rowId);
      if (!shortEl || !fullEl) return;
      var isExpanded = fullEl.style.display !== 'none';
      shortEl.style.display = isExpanded ? '' : 'none';
      fullEl.style.display = isExpanded ? 'none' : '';
      row.style.background = isExpanded ? '' : 'var(--bg-elevated)';
    });
  });
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
  if (isNaN(d.getTime())) return '';
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
  return Math.floor(diff / 86400000) + 'd ago';
}

function newsItemText(item) {
  return String((item && (item.text || item.title || item.headline || item.summary)) || '').trim();
}

function newsItemSource(item) {
  return String((item && (item.handle || item.username || item.source || item.publisher)) || 'news').trim() || 'news';
}

function newsItemTimestamp(item) {
  if (!item) return 0;
  var raw = item.timestamp || item.published || item.published_at || item.date || item.ts;
  var ms = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(ms) ? ms : 0;
}

function newsItemKey(item) {
  var url = String((item && item.url) || '').trim().toLowerCase();
  if (url && url !== '#') return 'url|' + url;
  return 'text|' + newsItemSource(item).toLowerCase() + '|' + newsItemText(item).toLowerCase().slice(0, 180);
}

function normalizeNewsFeed(items) {
  var seen = new Set();
  return (items || [])
    .filter(function(item) { return item && newsItemText(item); })
    .sort(function(a, b) { return newsItemTimestamp(b) - newsItemTimestamp(a); })
    .filter(function(item) {
      var key = newsItemKey(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, NEWS_CACHE_LIMIT);
}

function mergeNewsFeed(incoming) {
  researchXFeed = normalizeNewsFeed((researchXFeed || []).concat(incoming || []));
  researchXTweetCount = researchXFeed.length;
}

function newsFeedStats(feed) {
  var sources = {};
  var scored = 0;
  var fresh = 0;
  var newest = 0;
  var now = Date.now();
  (feed || []).forEach(function(item) {
    var source = newsItemSource(item);
    sources[source] = (sources[source] || 0) + 1;
    if (item.sentiment != null || item.relevancy != null || item.impact != null) scored += 1;
    var ts = newsItemTimestamp(item);
    if (ts) {
      newest = Math.max(newest, ts);
      if (now - ts <= NEWS_FRESH_MS) fresh += 1;
    }
  });
  var sourceRows = Object.keys(sources)
    .sort(function(a, b) { return sources[b] - sources[a] || a.localeCompare(b); })
    .map(function(source) { return { source: source, count: sources[source] }; });
  return {
    total: (feed || []).length,
    source_count: sourceRows.length,
    sources: sourceRows,
    scored: scored,
    fresh: fresh,
    newest: newest,
  };
}

function createNewsCard(item) {
  const text = newsItemText(item);
  const url = item.url || '#';
  const source = newsItemSource(item);
  const ts = item.timestamp || item.published;
  const tsMs = newsItemTimestamp(item);
  const sent = item.sentiment;
  const cat = item.category || 'Markets';
  const isFresh = tsMs && Date.now() - tsMs <= NEWS_FRESH_MS;
  const hasSentiment = sent != null || item.relevancy != null || item.impact != null;
  const sentClass = sent != null && sent > 0.1 ? 'bullish' : sent != null && sent < -0.1 ? 'bearish' : 'neutral';
  const scoreLabel = hasSentiment
    ? '<span class="nc-score">sentiment</span>'
    : '<span class="nc-score muted">raw</span>';
  return '<div class="news-card' + (isFresh ? ' fresh' : '') + '">' +
    '<div class="nc-meta">' +
    (isFresh ? '<span class="nc-new">NEW</span>' : '') +
    '<span class="nc-cat">' + escapeHtml(cat) + '</span>' +
    '<span class="nc-dot ' + sentClass + '"></span>' +
    '<span class="nc-time">' + formatRelativeTime(ts) + '</span>' +
    scoreLabel +
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
  const uniqueSourcesEl = document.getElementById('social-unique-sources');
  const sourceBreakdownEl = document.getElementById('social-source-breakdown');
  const refreshEl = document.getElementById('social-last-refresh');
  const badgeEl = document.getElementById('social-badge');

  if (!researchFeedAuditLoading && Date.now() - researchFeedAuditLastFetchMs > RESEARCH_FEED_REFRESH_MS) {
    fetchResearchFeedAudit(false).then(function() {
      renderNewsFeed();
    }).catch(function() {});
  }

  const feed = normalizeNewsFeed(researchXFeed || []);
  researchXFeed = feed;
  researchXTweetCount = feed.length;
  const stats = newsFeedStats(feed);
  const count = stats.total;
  const sentiment = researchSocialScore != null ? researchSocialScore.toFixed(3) : '-';

  if (sentimentEl) sentimentEl.textContent = sentiment;
  if (countEl) countEl.textContent = count;
  if (sourcesEl) sourcesEl.textContent = NEWS_SCORE_WINDOW;
  if (uniqueSourcesEl) uniqueSourcesEl.textContent = stats.source_count;
  if (sourceBreakdownEl) {
    const topSources = stats.sources.slice(0, 6).map(function(row) {
      return row.source + ' ' + row.count;
    }).join(' | ');
    sourceBreakdownEl.textContent = topSources
      ? 'Fresh ' + stats.fresh + ' | Showing ' + Math.min(stats.total, NEWS_DISPLAY_LIMIT) + ' of ' + stats.total + ' | ' + topSources
      : 'Waiting for source mix...';
  }
  const newestIso = stats.newest ? new Date(stats.newest).toISOString() : newsLastRefresh;
  if (refreshEl) refreshEl.textContent = newestIso ? formatRelativeTime(newestIso) : '-';
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
  wrap.innerHTML = feed.slice(0, NEWS_DISPLAY_LIMIT).map(createNewsCard).join('');
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function researchTags(values, cls) {
  const arr = Array.isArray(values) ? values.filter(Boolean) : [];
  if (!arr.length) return '<span class="rf-tag muted">none</span>';
  return arr.slice(0, 8).map(function(v) {
    return '<span class="rf-tag ' + (cls || '') + '">' + escapeHtml(String(v)) + '</span>';
  }).join('');
}

function renderResearchSourceHealthTable(sources) {
  const panel = document.getElementById('research-source-health-panel');
  const badge = document.getElementById('rf-source-badge');
  if (badge) badge.textContent = (sources || []).length + ' sources';
  if (!panel) return;
  if (!sources || !sources.length) {
    panel.innerHTML = '<div class="empty-txt">No source health yet</div>';
    return;
  }
  panel.innerHTML =
    '<table class="dtbl research-source-table">' +
      '<thead><tr>' +
        '<th>Source</th><th>Type</th><th>Status</th><th>Items</th><th>Last Success</th><th>Failures</th><th>Error</th>' +
      '</tr></thead>' +
      '<tbody>' +
        sources.map(function(source) {
          const status = String(source.status || 'unknown').toLowerCase();
          const statusClass = status === 'ok' || status === 'success' || status === 'cached' ? 'ok' : status === 'stale' ? 'warn' : 'bad';
          return '<tr>' +
            '<td>' + escapeHtml(source.source || '-') + '</td>' +
            '<td>' + escapeHtml(source.source_type || '-') + '</td>' +
            '<td><span class="rf-status ' + statusClass + '">' + escapeHtml(status.toUpperCase()) + '</span></td>' +
            '<td>' + (source.item_count || 0) + '</td>' +
            '<td>' + escapeHtml(formatRelativeTime(source.last_success_at)) + '</td>' +
            '<td>' + (source.consecutive_failures || 0) + '</td>' +
            '<td>' + escapeHtml(truncate(source.error || '-', 80)) + '</td>' +
          '</tr>';
        }).join('') +
      '</tbody>' +
    '</table>';
}

function renderResearchFeedItems(items) {
  const panel = document.getElementById('research-feed-audit-panel');
  const badge = document.getElementById('rf-item-badge');
  if (badge) badge.textContent = (items || []).length + ' items';
  if (!panel) return;
  if (!items || !items.length) {
    panel.innerHTML = '<div class="empty-txt">No research feed audit yet</div>';
    return;
  }
  panel.innerHTML = items.map(function(item) {
    const action = item.action_audit || {};
    const actionStatus = String(action.status || 'monitor').toLowerCase();
    const matched = Array.isArray(action.matched_events) ? action.matched_events : [];
    const url = item.url || '#';
    const title = item.title || item.text || 'Untitled research item';
    const urgency = item.urgency != null ? Math.round(Number(item.urgency) * 100) + '%' : '-';
    return '<div class="research-item-card">' +
      '<div class="rf-item-top">' +
        '<div>' +
          '<div class="rf-item-meta">' +
            '<span>' + escapeHtml(item.source || 'news') + '</span>' +
            '<span>' + escapeHtml(item.source_type || '-') + '</span>' +
            '<span>' + escapeHtml(formatRelativeTime(item.published_at || item.last_seen_at)) + '</span>' +
            '<span>urgency ' + escapeHtml(urgency) + '</span>' +
          '</div>' +
          '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener" class="rf-item-title">' + escapeHtml(title) + '</a>' +
        '</div>' +
        '<span class="rf-action ' + actionStatus + '">' + escapeHtml(actionStatus.replace('_', ' ').toUpperCase()) + '</span>' +
      '</div>' +
      '<div class="rf-route-grid">' +
        '<div><span class="rf-label">Pods</span><div class="rf-tags">' + researchTags(item.affected_pods, 'pod') + '</div></div>' +
        '<div><span class="rf-label">Factors</span><div class="rf-tags">' + researchTags(item.factors, 'factor') + '</div></div>' +
        '<div><span class="rf-label">Tickers</span><div class="rf-tags">' + researchTags(item.tickers, 'ticker') + '</div></div>' +
        '<div><span class="rf-label">Held</span><div class="rf-tags">' + researchTags(item.held_symbols, 'held') + '</div></div>' +
      '</div>' +
      '<div class="rf-next-action">' + escapeHtml(action.next_action || 'Monitor for trade thesis relevance.') + '</div>' +
      (matched.length ? '<div class="rf-matches">' + matched.map(function(m) {
        return '<span>' + escapeHtml((m.kind || 'event') + ' ' + (m.pod_id || '') + ' ' + (m.symbol || '') + ' ' + (m.action || m.status || '')) + '</span>';
      }).join('') + '</div>' : '') +
    '</div>';
  }).join('');
}

function researchAuditItemsToNews(items) {
  return (items || []).map(function(item) {
    var raw = item.raw && typeof item.raw === 'object' ? item.raw : {};
    return Object.assign({}, raw, {
      title: item.title || raw.title || raw.headline || item.text || '',
      text: item.text || raw.text || raw.summary || raw.headline || item.title || '',
      headline: item.title || raw.headline || raw.title || '',
      url: item.url || raw.url || '#',
      source: item.source || raw.source || raw.publisher || 'news',
      publisher: item.source || raw.publisher || raw.source || 'news',
      category: item.category || raw.category || item.source_type || 'Markets',
      timestamp: item.published_at || item.last_seen_at || raw.timestamp || raw.published_at || raw.published,
      published_at: item.published_at || raw.published_at || raw.published,
      sentiment: item.sentiment != null ? item.sentiment : raw.sentiment,
      reliability: item.reliability != null ? item.reliability : raw.reliability,
      asset_classes: item.asset_classes || raw.asset_classes,
      factors: item.factors || raw.factors,
      tickers: item.tickers || raw.tickers
    });
  }).filter(function(item) {
    return newsItemText(item);
  });
}

function absorbResearchFeedAudit(report) {
  var items = researchAuditItemsToNews(report && report.items);
  if (items.length) {
    mergeNewsFeed(items);
  }
  if (report && report.last_fetch_time) {
    newsLastRefresh = report.last_fetch_time;
  }
  return items.length;
}

async function fetchResearchFeedAudit(force) {
  if (researchFeedAuditLoading) return researchFeedAudit;
  if (!force && researchFeedAudit && Date.now() - researchFeedAuditLastFetchMs < RESEARCH_FEED_REFRESH_MS) {
    return researchFeedAudit;
  }
  researchFeedAuditLoading = true;
  try {
    researchFeedAudit = await fetchJsonWithTimeout('/api/research-feed?limit=100', {}, 7000);
    researchFeedAuditLastFetchMs = Date.now();
    absorbResearchFeedAudit(researchFeedAudit);
  } catch (err) {
    researchFeedAuditLastFetchMs = Date.now();
    researchFeedAudit = {
      status: 'ERROR',
      items: [],
      sources: [],
      item_count: 0,
      source_count: 0,
      source_error_count: 1,
      last_fetch_time: null,
      error: String(err && err.message ? err.message : err),
    };
  } finally {
    researchFeedAuditLoading = false;
  }
  return researchFeedAudit;
}

async function renderResearchFeedAudit(force) {
  if (force || !researchFeedAudit) {
    await fetchResearchFeedAudit(!!force);
  }
  const report = researchFeedAudit || {};
  const items = report.items || [];
  const sources = report.sources || [];
  const needsReview = items.filter(function(item) {
    return item.action_audit && item.action_audit.status === 'needs_review';
  }).length;

  setText('rf-status', report.status || '-');
  setText('rf-items', report.item_count != null ? report.item_count : items.length);
  setText('rf-sources', report.source_count != null ? report.source_count : sources.length);
  setText('rf-source-errors', (report.source_error_count || 0) + ' checks');
  setText('rf-review', needsReview);
  setText('rf-last-fetch', 'last fetch ' + (report.last_fetch_time ? formatRelativeTime(report.last_fetch_time) : '-'));
  renderResearchSourceHealthTable(sources);
  renderResearchFeedItems(items);
}

function renderForesightRows(events) {
  var panel = document.getElementById('foresight-ledger-panel');
  if (!panel) return;
  if (!events || !events.length) {
    panel.innerHTML = '<div class="empty-txt">No catalyst events yet</div>';
    return;
  }
  panel.innerHTML =
    '<table class="dtbl foresight-table">' +
      '<thead><tr>' +
        '<th>Event</th><th>State</th><th>Pods</th><th>Factors</th><th class="num">Materiality</th><th class="num">Confidence</th><th>Direction</th><th>Specialists</th>' +
      '</tr></thead>' +
      '<tbody>' +
        events.map(function(event) {
          var impact = event.materiality_score != null ? Number(event.materiality_score).toFixed(2) : (event.impact_score != null ? Number(event.impact_score).toFixed(2) : '-');
          var conf = event.confidence != null ? Number(event.confidence).toFixed(2) : '-';
          var pods = Array.isArray(event.affected_pods) ? event.affected_pods : [];
          var factors = Array.isArray(event.factors) ? event.factors : [];
          var specs = Array.isArray(event.suggested_specialists) ? event.suggested_specialists : [];
          var refs = Array.isArray(event.source_refs) ? event.source_refs : [];
          var firstUrl = refs.find(function(ref) { return ref && ref.url; });
          var title = event.title || event.event_id || 'Untitled catalyst';
          var titleHtml = firstUrl && firstUrl.url
            ? '<a href="' + escapeHtml(firstUrl.url) + '" target="_blank" rel="noopener">' + escapeHtml(title) + '</a>'
            : escapeHtml(title);
          return '<tr>' +
            '<td><div class="rf-item-title">' + titleHtml + '</div>' +
              '<div class="rf-item-meta">' + escapeHtml(event.thread_id || event.event_id || '') + ' | ' + escapeHtml(truncate(event.summary || '', 180)) + '</div>' +
              '<div class="rf-item-meta">' + escapeHtml(truncate(event.transmission_path || event.uncertainty || '', 180)) + '</div></td>' +
            '<td><span class="badge ' + (String(event.status || '').toLowerCase() === 'active' ? 'b-active' : 'b-pending') + '">' + escapeHtml(String(event.status || 'active').toUpperCase()) + '</span></td>' +
            '<td><div class="rf-tags">' + researchTags(pods, 'pod') + '</div></td>' +
            '<td><div class="rf-tags">' + researchTags(factors, 'factor') + '</div></td>' +
            '<td class="num">' + escapeHtml(impact) + '</td>' +
            '<td class="num">' + escapeHtml(conf) + '</td>' +
            '<td>' + escapeHtml((event.direction || 'mixed').toUpperCase()) + '<div class="rf-item-meta">' + escapeHtml(event.horizon || '') + '</div></td>' +
            '<td><div class="rf-tags">' + researchTags(specs, 'held') + '</div></td>' +
          '</tr>';
        }).join('') +
      '</tbody>' +
    '</table>';
}

function renderCatalystThreads(threads) {
  var panel = document.getElementById('catalyst-thread-panel');
  if (!panel) return;
  setText('fs-thread-count', (threads || []).length + ' threads');
  if (!threads || !threads.length) {
    panel.innerHTML = '<div class="empty-txt">No catalyst threads yet</div>';
    return;
  }
  panel.innerHTML = '<table class="dtbl foresight-table"><thead><tr>' +
    '<th>Thread</th><th>Status</th><th class="num">Events</th><th>Pods</th><th>Factors</th><th class="num">Score</th><th>Latest</th>' +
    '</tr></thead><tbody>' +
    threads.map(function(t) {
      return '<tr>' +
        '<td><div class="rf-item-title">' + escapeHtml(t.title || t.thread_id || '') + '</div>' +
          '<div class="rf-item-meta">' + escapeHtml(t.thread_id || '') + '</div></td>' +
        '<td><span class="badge ' + (String(t.status || '').toLowerCase() === 'active' ? 'b-active' : 'b-pending') + '">' + escapeHtml(String(t.status || 'active').toUpperCase()) + '</span></td>' +
        '<td class="num">' + (t.event_count || 0) + '</td>' +
        '<td><div class="rf-tags">' + researchTags(t.affected_pods || [], 'pod') + '</div></td>' +
        '<td><div class="rf-tags">' + researchTags(t.factors || [], 'factor') + '</div></td>' +
        '<td class="num">' + Number(t.materiality_score || 0).toFixed(2) + '</td>' +
        '<td class="mono">' + escapeHtml(formatRelativeTime(t.latest_updated_at)) + '</td>' +
      '</tr>';
    }).join('') + '</tbody></table>';
}

async function fetchForesightLedger(force) {
  if (foresightLedgerLoading) return foresightLedger;
  if (!force && foresightLedger && Date.now() - foresightLedgerLastFetchMs < RESEARCH_FEED_REFRESH_MS) {
    return foresightLedger;
  }
  foresightLedgerLoading = true;
  try {
    foresightLedger = await fetchJsonWithTimeout('/api/foresight?limit=100', {}, 7000);
    catalystThreads = await fetchJsonWithTimeout('/api/catalyst-threads?limit=50', {}, 7000);
    foresightLedgerLastFetchMs = Date.now();
  } catch (err) {
    foresightLedgerLastFetchMs = Date.now();
    foresightLedger = {
      status: 'ERROR',
      events: [],
      counts: { active: 0, stale: 0, failed: 1 },
      event_count: 0,
      error: String(err && err.message ? err.message : err),
    };
    catalystThreads = { threads: [], count: 0, status: 'ERROR' };
  } finally {
    foresightLedgerLoading = false;
  }
  return foresightLedger;
}

async function renderForesightLedger(force) {
  if (force || !foresightLedger) {
    await fetchForesightLedger(!!force);
  }
  var report = foresightLedger || {};
  var counts = report.counts || {};
  setText('fs-status', report.status || '-');
  setText('fs-active', counts.active || 0);
  setText('fs-stale', counts.stale || 0);
  setText('fs-failed', counts.failed || 0);
  renderForesightRows(report.events || []);
  renderCatalystThreads((catalystThreads || {}).threads || []);
}

function updateResearchTab(signals, confidence, macroScore) {
  researchSignals = signals || [];
  researchPolyConf = confidence != null ? confidence : 0.5;
  researchMacroScore = macroScore;

  if (researchSignals.length > 0) {
    mergePolymarketHistory(researchSignals);
  }

  ensurePolymarketHistoryLayout();
  renderCurrentMarkets(researchSignals);
  updateHistoricalChart();
  renderHistoryTableV2();
  renderContributors(researchSignals, researchPolyConf, researchMacroScore, researchMomentum);
  renderMacroIndicators();
  updateVixKpi();
  renderNewsFeed();
}

// ─── 6. Message Handler ───────────────────────────────────────────────────
function handleMessage(msg) {
  if (msg.type === 'session_snapshot') {
    var snap = msg.data || {};
    updateIterationDisplay(snap);
    if (snap.session_active !== undefined) updateSessionStatus(!!snap.session_active);
    if (snap.firm_inception_pnl !== undefined && snap.firm_inception_pnl !== null) {
      firmInceptionPnl = snap.firm_inception_pnl;
    }
    if (snap.benchmark_returns && typeof snap.benchmark_returns === 'object') {
      benchmarkReturns = snap.benchmark_returns;
    }
    if (snap.drawdown_tier) drawdownTierBadge = snap.drawdown_tier;
    if (snap.research_feed) {
      researchFeedAudit = snap.research_feed;
      researchFeedAuditLastFetchMs = Date.now();
      absorbResearchFeedAudit(researchFeedAudit);
      renderNewsFeed();
    }
    fetch('/api/nav-history?limit=' + MAX_NAV_HISTORY).then(function(r) { return r.json(); }).then(function(data) {
      var hist = (data && data.history) ? data.history : [];
      if (hist.length === 0) return;
      if (replaceNavHistoryFromApi(hist)) {
        updateNavChart();
        updateDrawdownChart();
        updatePodsTable();
        updateFirmMetrics();
        updatePerfTable();
        updateAttribution();
      }
    }).catch(function() {});
    var podSums = snap.pod_summaries || {};
    for (var pid in podSums) {
      var m = podSums[pid];
      if (m && m.data) {
        pods[m.pod_id || pid] = mergePodData(m.pod_id || pid, m.data);
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
          mergeNewsFeed(pData.x_feed);
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
      if (o.data && o.data.order_id) orderBook[o.data.local_order_id || o.data.order_id] = o.data;
    });
    (snap.position_reviews || []).forEach(function(rv) {
      addReviewEvent(rv);
    });
    if (snap.loss_reviews) {
      renderLossReviews(snap.loss_reviews);
    }
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
    updateIterationDisplay(sd);
    if (sd.firm_inception_pnl != null && sd.firm_inception_pnl !== undefined) {
      firmInceptionPnl = sd.firm_inception_pnl;
    }
    if (sd.benchmark_returns && typeof sd.benchmark_returns === 'object') {
      benchmarkReturns = sd.benchmark_returns;
    }
    if (sd.drawdown_tier) drawdownTierBadge = sd.drawdown_tier;
    updateFirmMetrics();
    updateNavChart();
    return;
  }
  if (msg.type === 'pod_summary' || msg.type === 'pod_enrichment') {
    const data = msg.data;
    const pod_id = msg.pod_id || data.pod_id;
    if (pod_id) {
      if (msg.type === 'pod_summary') {
        pods[pod_id] = mergePodData(pod_id, data);
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
          mergeNewsFeed(data.x_feed || []);
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
      podNavSpark[pod_id].push(getPodNav(pods[pod_id]) || 0);
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
    triggerPodRowPulse(t.pod_id, 'trade');
    const srcFloor = podFloorMap[t.pod_id] ?? 0;
    if (typeof createDataRoute === 'function') createDataRoute(srcFloor, 4, 0x00cfe8);
  } else if (msg.type === 'governance') {
    const gv = msg.data;
    if (gv.agent && gv.decision) {
      recordGov(gv.agent, gv.decision, gv.reasoning || '', gv.weights || null);
      if (typeof triggerGovernanceLightFlow === 'function') triggerGovernanceLightFlow(gv.agent);
      triggerPodRowPulse(null, 'gov');
    }
  } else if (msg.type === 'risk_alert') {
    const ra = msg.data;
    riskAlerts.unshift(ra);
    if (riskAlerts.length > 50) riskAlerts.pop();
    var sev = ra.severity || (ra.action === 'firm_drawdown' ? 'warning' : 'warning');
    var txt = ra.message || ra.reason || JSON.stringify(ra);
    updateRiskAlertBanner(sev, txt);
    if (ra.loss_review) {
      var currentLoss = lossReviewState && lossReviewState.active ? lossReviewState.active : {};
      currentLoss[ra.loss_review.pod_id] = ra.loss_review;
      renderLossReviews(Object.assign({}, lossReviewState, { active: currentLoss }));
    }
    if (typeof triggerRiskAlert === 'function') triggerRiskAlert(ra);
  } else if (msg.type === 'agent_activity') {
    var act = msg.data;
    if (!agentActivity[act.agent_id]) agentActivity[act.agent_id] = [];
    agentActivity[act.agent_id].unshift(act);
    if (agentActivity[act.agent_id].length > 5) agentActivity[act.agent_id].pop();
    activityFeed.unshift({
      agent_id: act.agent_id,
      agent_role: act.agent_role,
      pod_id: act.pod_id,
      symbol: act.symbol,
      action: act.action,
      status: act.status,
      summary: act.summary,
      detail: act.detail,
      reason: act.reason,
      urls: act.urls,
      ts: msg.timestamp,
    });
    if (activityFeed.length > 50) activityFeed.pop();
    updateActivityFeed();
    updateDecisionTimeline();
    if (typeof triggerAgentActivity === 'function') triggerAgentActivity(act.pod_id, act.agent_role);
    if (act.pod_id) triggerPodRowPulse(act.pod_id, 'trade');
    if (act.action === 'new_report' && act.filename) {
      onNewReport(act.filename);
    }
  } else if (msg.type === 'order_update') {
    var od = msg.data;
    if (od.order_id) {
      var orderKey = od.local_order_id || od.order_id;
      var existingOrder = Object.assign({}, orderBook[orderKey] || {}, orderBook[od.order_id] || {});
      orderBook[orderKey] = Object.assign(existingOrder, od);
      if (orderKey !== od.order_id && orderBook[od.order_id]) delete orderBook[od.order_id];
      if (od.status === 'FILLED' || od.status === 'PARTIAL') {
        addTrade(od.pod_id || 'unknown', od.symbol, od.side, od.fill_qty || od.qty, od.fill_price || 0, od.status, od.broker_order_id || od.order_id);
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
    let nav = getCurrentPodNav(id);
    const invested = d.invested ?? rm.invested ?? 0;
    const startCap = d.starting_capital ?? rm.starting_capital;
    // Fallback: nav=0 but pod has allocated capital (idle pod) — show starting_capital
    if (nav === 0 && startCap > 0 && invested === 0) nav = startCap;
    const cash = d.cash ?? rm.cash ?? 0;
    const dailyMove = getPodDailyMove(id);
    const pnl = dailyMove.pnl;
    const st  = (d.status || 'UNKNOWN').toUpperCase();
    const stCls = st === 'ACTIVE' ? 'b-active' : st === 'HALTED' ? 'b-halted' : 'b-idle';
    const pc  = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : 'neu';
    const spark = makeSparkline(podNavSpark[id]);
    const navTitle = `Invested: $${invested.toFixed(2)} | Cash: $${cash.toFixed(2)}`;
    var pm = pods[id] ? (pods[id].performance_metrics || {}) : {};
    var sharpeStr = (pm.sharpe != null && pm.sharpe !== 0) ? Number(pm.sharpe).toFixed(2) : '—';
    return `<tr data-pod="${id}" onclick="openDrilldown('${id}')" style="cursor:pointer" title="${navTitle}">
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r"><span title="${navTitle}">$${nav.toFixed(2)}</span></td>
      <td class="r">${spark}</td>
      <td class="r ${pc}">${formatPnlWithPct(pnl, dailyMove.base || podDailyPnlBase(d), { pct: dailyMove.pct, pctDecimals: 2 })}</td>
      <td class="r">${sharpeStr}</td>
      <td class="r"><span class="badge ${stCls}">${st}</span></td>
    </tr>`;
  }).join('');
}

function triggerPodRowPulse(podId, type) {
  // type: 'trade' (cyan) or 'gov' (purple cascade across all pods)
  if (type === 'gov') {
    var rows = document.querySelectorAll('#pods-table tr[data-pod]');
    rows.forEach(function(row, i) {
      setTimeout(function() {
        row.classList.remove('pod-signal-pulse', 'pod-gov-cascade');
        void row.offsetWidth;
        row.classList.add('pod-gov-cascade');
        row.addEventListener('animationend', function handler() {
          row.classList.remove('pod-gov-cascade');
          row.removeEventListener('animationend', handler);
        });
      }, i * 120);
    });
  } else {
    var row = document.querySelector('#pods-table tr[data-pod="' + podId + '"]');
    if (!row) return;
    row.classList.remove('pod-signal-pulse', 'pod-gov-cascade');
    void row.offsetWidth;
    row.classList.add('pod-signal-pulse');
    row.addEventListener('animationend', function handler() {
      row.classList.remove('pod-signal-pulse');
      row.removeEventListener('animationend', handler);
    });
  }
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

function asNumber(value, fallback) {
  var n = Number(value);
  return Number.isFinite(n) ? n : (fallback == null ? 0 : fallback);
}

var _lastValidNavSnapshot = null;

function positiveNumber(value) {
  var n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function copyPodNavs(podNavs) {
  var out = {};
  Object.keys(podNavs || {}).forEach(function(id) {
    var nav = positiveNumber(podNavs[id]);
    if (nav != null) out[id] = nav;
  });
  return out;
}

function inferSeedBaseline(referenceNav) {
  var ref = positiveNumber(referenceNav);
  if (ref == null) return null;
  var rounded = Math.round(ref / 100) * 100;
  if (rounded >= 500 && Math.abs(ref - rounded) <= Math.max(25, rounded * 0.10)) {
    return rounded;
  }
  return ref;
}

function repairLeadingSeedNavPlaceholders(hist) {
  var rows = (hist || []).map(function(row) {
    var copy = Object.assign({}, row || {});
    copy.pods = copyPodNavs(copy.pods || {});
    return copy;
  });
  var podMax = {};
  rows.forEach(function(row) {
    Object.keys(row.pods || {}).forEach(function(id) {
      var nav = positiveNumber(row.pods[id]);
      if (nav == null) return;
      podMax[id] = Math.max(podMax[id] || 0, nav);
    });
  });
  Object.keys(podMax).forEach(function(id) {
    var maxNav = podMax[id] || 0;
    if (maxNav < 500) return;
    var threshold = Math.max(500, maxNav * 0.5);
    var firstValidIdx = -1;
    for (var i = 0; i < rows.length; i += 1) {
      var nav = positiveNumber(rows[i].pods && rows[i].pods[id]);
      if (nav != null && nav >= threshold) {
        firstValidIdx = i;
        break;
      }
    }
    if (firstValidIdx <= 0) return;
    var baseline = inferSeedBaseline(rows[firstValidIdx].pods[id]);
    if (baseline == null) return;
    for (var j = 0; j < firstValidIdx; j += 1) {
      var seedNav = positiveNumber(rows[j].pods && rows[j].pods[id]);
      if (seedNav != null && seedNav < threshold) {
        rows[j].pods[id] = baseline;
      }
    }
  });
  rows.forEach(function(row) {
    var podSum = Object.keys(row.pods || {}).reduce(function(sum, id) {
      return sum + (positiveNumber(row.pods[id]) || 0);
    }, 0);
    if (podSum > 0) row.nav = podSum;
  });
  return rows;
}

function mergePodData(podId, incoming) {
  var prior = pods[podId] || {};
  var data = incoming || {};
  var merged = Object.assign({}, prior, data);
  var status = String(data.status || prior.status || '').toUpperCase();
  var inactiveLike = !sessionActive || status === 'IDLE' || status === 'HALTED' || status === 'STOPPED' || status === 'INACTIVE';
  var priorNav = positiveNumber(getPodNav(prior));
  var incomingHasNav = Object.prototype.hasOwnProperty.call(data, 'nav');
  var incomingNav = incomingHasNav ? positiveNumber(data.nav) : null;

  if (incomingHasNav && incomingNav == null && priorNav != null && inactiveLike) {
    merged.nav = priorNav;
  }

  if (data.risk_metrics && typeof data.risk_metrics === 'object') {
    var priorRisk = (prior.risk_metrics && typeof prior.risk_metrics === 'object') ? prior.risk_metrics : {};
    var mergedRisk = Object.assign({}, priorRisk, data.risk_metrics);
    var riskHasNav = Object.prototype.hasOwnProperty.call(data.risk_metrics, 'nav');
    var incomingRiskNav = riskHasNav ? positiveNumber(data.risk_metrics.nav) : null;
    var priorRiskNav = positiveNumber(priorRisk.nav) || priorNav;
    if (riskHasNav && incomingRiskNav == null && priorRiskNav != null && inactiveLike) {
      mergedRisk.nav = priorRiskNav;
    }
    merged.risk_metrics = mergedRisk;
  }

  return merged;
}

function buildNavHistoryPoint(tsMs, rawFirmNav, rawPods, fallbackSnapshot) {
  var fallback = fallbackSnapshot || null;
  var sourcePods = rawPods && typeof rawPods === 'object' ? rawPods : {};
  var keys = Object.keys(sourcePods);
  if (keys.length === 0 && fallback && fallback.pods) keys = Object.keys(fallback.pods);

  var podNavs = {};
  keys.forEach(function(id) {
    var nav = positiveNumber(sourcePods[id]);
    if (nav == null && fallback && fallback.pods) nav = positiveNumber(fallback.pods[id]);
    if (nav != null) podNavs[id] = nav;
  });

  var podSum = Object.keys(podNavs).reduce(function(sum, id) { return sum + podNavs[id]; }, 0);
  var firmNav = positiveNumber(rawFirmNav);
  var fallbackFirmNav = fallback ? positiveNumber(fallback.firmNav) : null;
  var collapsedAgainstFallback = fallbackFirmNav != null && (
    (firmNav != null && firmNav < fallbackFirmNav * 0.5) ||
    (podSum > 0 && podSum < fallbackFirmNav * 0.5)
  );
  if (collapsedAgainstFallback) {
    firmNav = fallbackFirmNav;
    if (fallback && fallback.pods) {
      podNavs = copyPodNavs(fallback.pods);
      podSum = Object.keys(podNavs).reduce(function(sum, id) { return sum + podNavs[id]; }, 0);
    }
  }
  if (firmNav != null && podSum > firmNav) firmNav = podSum;
  if (firmNav == null && podSum > 0) firmNav = podSum;
  if (firmNav == null && fallback) firmNav = fallbackFirmNav;
  if (firmNav == null) return null;

  return {
    t: formatNavTimestamp(tsMs),
    ts: tsMs,
    firmNav: firmNav,
    pods: podNavs,
    drawdown: 0,
  };
}

function rememberNavSnapshot(point) {
  if (!point || positiveNumber(point.firmNav) == null) return;
  _lastValidNavSnapshot = {
    firmNav: point.firmNav,
    pods: copyPodNavs(point.pods || {}),
  };
}

function replaceNavHistoryFromApi(hist) {
  var nextHistory = [];
  var fallback = null;
  repairLeadingSeedNavPlaceholders(hist || []).forEach(function(h) {
    var tsMs = Date.parse(h.ts) || Date.now();
    var point = buildNavHistoryPoint(tsMs, h.nav != null ? h.nav : h.firmNav, h.pods || {}, fallback);
    if (!point) return;
    nextHistory.push(point);
    fallback = {
      firmNav: point.firmNav,
      pods: copyPodNavs(point.pods || {}),
    };
  });
  if (nextHistory.length === 0) return false;
  navHistory = nextHistory.slice(-MAX_NAV_HISTORY);
  rememberNavSnapshot(navHistory[navHistory.length - 1]);
  recalculateNavDrawdowns();
  return true;
}

function formatSignedMoney(value, decimals) {
  var n = asNumber(value, 0);
  var places = decimals == null ? 2 : decimals;
  return (n >= 0 ? '+$' : '-$') + Math.abs(n).toFixed(places);
}

function formatSignedPct(value, decimals) {
  var n = asNumber(value, 0);
  var places = decimals == null ? 2 : decimals;
  return (n >= 0 ? '+' : '') + n.toFixed(places) + '%';
}

function formatPnlWithPct(pnl, baseNotional, opts) {
  opts = opts || {};
  var n = asNumber(pnl, 0);
  var text = formatSignedMoney(n, opts.moneyDecimals);
  var pct = opts.pct;
  var base = Math.abs(asNumber(baseNotional, 0));
  if (pct == null && base > 0) pct = (n / base) * 100;
  if (pct != null && Number.isFinite(Number(pct))) {
    text += ' (' + formatSignedPct(Number(pct), opts.pctDecimals) + ')';
  }
  return text;
}

function positionEntryNotional(p) {
  if (!p) return 0;
  var explicit = Math.abs(asNumber(p.entry_notional || p.cost_notional || p.initial_notional, 0));
  if (explicit > 0) return explicit;
  var qty = Math.abs(asNumber(p.qty || p.quantity, 0));
  var entry = asNumber(p.cost_basis || p.avg_entry || p.entry_price, 0);
  if (qty > 0 && entry > 0) return qty * entry;
  return Math.abs(asNumber(p.notional, 0));
}

function positionCurrentNotional(p) {
  if (!p) return 0;
  var qty = Math.abs(asNumber(p.qty || p.quantity, 0));
  var price = asNumber(p.current_price || p.price, 0);
  if (qty > 0 && price > 0) return qty * price;
  var explicit = Math.abs(asNumber(p.current_notional || p.market_value, 0));
  if (explicit > 0) return explicit;
  return Math.abs(asNumber(p.notional, 0));
}

function tradeEntryNotional(t) {
  if (!t) return 0;
  var explicit = Math.abs(asNumber(t.entry_notional || t.initial_notional, 0));
  if (explicit > 0) return explicit;
  var qty = Math.abs(asNumber(t.qty || t.quantity || t.qty_sold, 0));
  var entry = asNumber(t.entry_price || t.cost_basis || t.avg_entry || t.fill_price, 0);
  if (qty > 0 && entry > 0) return qty * entry;
  return Math.abs(asNumber(t.notional, 0));
}

function podDailyPnlBase(d) {
  return Math.abs(getPodNav(d || {}) || getPodStartCap(d || {}) || 0);
}

function dateOnly(value) {
  if (value == null || value === '') return '';
  var text = String(value);
  return text.length >= 10 ? text.slice(0, 10) : text;
}

function displayDateOnly(value) {
  return dateOnly(value) || '-';
}

function getAllocationBaseCapital(ids) {
  var startTotal = ids.reduce(function(sum, id) {
    return sum + (getPodStartCap(pods[id] || {}) || 0);
  }, 0);
  if (startTotal > 0) return startTotal;
  if (initialCapital > 0) return initialCapital;

  var navTotal = ids.reduce(function(sum, id) {
    return sum + (getPodNav(pods[id] || {}) || 0);
  }, 0);
  if (navTotal > 0) return navTotal;
  return ids.length > 0 ? ids.length * 1000 : 0;
}

function normalizeAllocationWeights(rawWeights, ids) {
  var weights = {};
  var complete = rawWeights && typeof rawWeights === 'object' && ids.length > 0;

  if (complete) {
    ids.forEach(function(id) {
      var value = rawWeights[id];
      if (value == null) value = rawWeights[id.toUpperCase()];
      value = Number(value);
      if (Number.isFinite(value) && value > 0) {
        weights[id] = value;
      } else {
        complete = false;
      }
    });

    if (complete) {
      var maxWeight = Math.max.apply(null, Object.values(weights));
      if (maxWeight > 1) {
        Object.keys(weights).forEach(function(id) { weights[id] = weights[id] / 100; });
      }
      var totalWeight = Object.values(weights).reduce(function(sum, value) { return sum + value; }, 0);
      if (totalWeight > 0) {
        Object.keys(weights).forEach(function(id) { weights[id] = weights[id] / totalWeight; });
        return weights;
      }
    }
  }

  var totalStart = ids.reduce(function(sum, id) {
    return sum + (getPodStartCap(pods[id] || {}) || 0);
  }, 0);
  if (totalStart > 0) {
    ids.forEach(function(id) {
      weights[id] = (getPodStartCap(pods[id] || {}) || 0) / totalStart;
    });
    return weights;
  }

  var equalWeight = ids.length > 0 ? 1 / ids.length : 0;
  ids.forEach(function(id) { weights[id] = equalWeight; });
  return weights;
}

function navDayKey(point) {
  if (!point || !point.ts) return '';
  var d = new Date(point.ts);
  if (isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

function currentDayKey() {
  return new Date().toISOString().slice(0, 10);
}

function latestNavPoint() {
  return navHistory.length > 0 ? navHistory[navHistory.length - 1] : null;
}

function todayBaselineNavPoint() {
  if (navHistory.length === 0) return null;
  var today = currentDayKey();
  for (var i = 0; i < navHistory.length; i += 1) {
    if (navDayKey(navHistory[i]) === today) return navHistory[i];
  }
  return navHistory[0];
}

function pointPodNav(point, id) {
  if (!point || !point.pods) return null;
  var value = positiveNumber(point.pods[id]);
  return value == null ? null : value;
}

function getCurrentPodNav(id) {
  var latest = latestNavPoint();
  var fromHistory = pointPodNav(latest, id);
  if (fromHistory != null) return fromHistory;
  return getPodNav(pods[id] || {});
}

function getPodStartingCapital(id, ids) {
  var d = pods[id] || {};
  var startCap = positiveNumber(getPodStartCap(d));
  if (startCap != null) return startCap;
  if (initialCapital > 0 && ids && ids.length > 0) return initialCapital / ids.length;
  return 1000;
}

function getFirmStartingCapital(ids) {
  var total = (ids || []).reduce(function(sum, id) {
    return sum + getPodStartingCapital(id, ids);
  }, 0);
  if (total > 0) return total;
  if (initialCapital > 0) return initialCapital;
  return (ids && ids.length ? ids.length : 4) * 1000;
}

function getCurrentFirmNav(ids) {
  var latest = latestNavPoint();
  var firmNav = positiveNumber(latest && latest.firmNav);
  if (firmNav != null) return firmNav;
  return (ids || []).reduce(function(sum, id) {
    return sum + getCurrentPodNav(id);
  }, 0);
}

function getPodDailyMove(id) {
  var latest = latestNavPoint();
  var baseline = todayBaselineNavPoint();
  var latestNav = pointPodNav(latest, id);
  var baseNav = pointPodNav(baseline, id);
  if (latestNav != null && baseNav != null) {
    var pnl = latestNav - baseNav;
    return {
      pnl: pnl,
      base: baseNav,
      pct: baseNav > 0 ? (pnl / baseNav) * 100 : 0,
      source: 'nav_history',
    };
  }
  var d = pods[id] || {};
  var fallbackPnl = asNumber(d.daily_pnl || (d.risk_metrics && d.risk_metrics.daily_pnl), 0);
  var fallbackBase = podDailyPnlBase(d) || getPodStartingCapital(id, Object.keys(pods));
  return {
    pnl: fallbackPnl,
    base: fallbackBase,
    pct: fallbackBase > 0 ? (fallbackPnl / fallbackBase) * 100 : 0,
    source: 'pod_summary',
  };
}

function getFirmDailyMove(ids) {
  var latest = latestNavPoint();
  var baseline = todayBaselineNavPoint();
  var latestNav = positiveNumber(latest && latest.firmNav);
  var baseNav = positiveNumber(baseline && baseline.firmNav);
  if (latestNav != null && baseNav != null) {
    var pnl = latestNav - baseNav;
    return {
      pnl: pnl,
      base: baseNav,
      pct: baseNav > 0 ? (pnl / baseNav) * 100 : 0,
      source: 'nav_history',
    };
  }
  var fallbackPnl = (ids || []).reduce(function(sum, id) { return sum + getPodPnl(pods[id] || {}); }, 0);
  var fallbackBase = getCurrentFirmNav(ids);
  return {
    pnl: fallbackPnl,
    base: fallbackBase,
    pct: fallbackBase > 0 ? (fallbackPnl / fallbackBase) * 100 : 0,
    source: 'pod_summary',
  };
}

function tradePodId(t) {
  return String((t && (t.pod_id || t.pod || t._pod)) || '').toLowerCase();
}

function tradeSymbol(t) {
  return String((t && (t.symbol || t.ticker)) || '').toUpperCase();
}

function tradeExitDay(t) {
  return dateOnly(t && (t.exit_date || t.exit_time || t.closed_at || t.timestamp || t.ts));
}

function isClosedToday(t) {
  return tradeExitDay(t) === currentDayKey();
}

function closedTradePnl(t) {
  return asNumber(t && (t.realized_pnl != null ? t.realized_pnl : t.pnl), 0);
}

function getPodClosedToday(id) {
  return (_ctData || []).filter(function(t) {
    return tradePodId(t) === id.toLowerCase() && isClosedToday(t);
  });
}

function getPodRealizedToday(id) {
  var trades = getPodClosedToday(id);
  var pnl = trades.reduce(function(sum, t) { return sum + closedTradePnl(t); }, 0);
  var base = trades.reduce(function(sum, t) { return sum + tradeEntryNotional(t); }, 0);
  return { pnl: pnl, base: base, trades: trades.length };
}

function getPodOpenPositions(id) {
  var rows = (_positionsFromApi && _positionsFromApi.length > 0)
    ? _positionsFromApi
    : getPodPositions(pods[id] || {}).map(function(p) { return Object.assign({ _pod: id }, p || {}); });
  return rows.filter(function(p) {
    return String(p._pod || p.pod_id || '').toLowerCase() === id.toLowerCase();
  });
}

function getPodOpenPnl(id) {
  var positions = getPodOpenPositions(id);
  var pnl = positions.reduce(function(sum, p) {
    return sum + asNumber(p.unrealized_pnl != null ? p.unrealized_pnl : p.unrealised_pnl, 0);
  }, 0);
  var base = positions.reduce(function(sum, p) { return sum + positionEntryNotional(p); }, 0);
  return { pnl: pnl, base: base, positions: positions.length };
}

function getPodTradeCount(id) {
  var executed = executedTrades.filter(function(t) {
    return String(t.podId || t.pod_id || '').toLowerCase() === id.toLowerCase();
  }).length;
  var closed = (_ctData || []).filter(function(t) {
    return tradePodId(t) === id.toLowerCase();
  }).length;
  return Math.max(executed, closed);
}

function buildPnlContributors(ids) {
  var rows = [];
  (ids || Object.keys(pods)).forEach(function(id) {
    getPodOpenPositions(id).forEach(function(p) {
      var pnl = asNumber(p.unrealized_pnl != null ? p.unrealized_pnl : p.unrealised_pnl, 0);
      if (Math.abs(pnl) < 0.005) return;
      rows.push({
        pod: id,
        symbol: String(p.symbol || '').toUpperCase(),
        type: 'Open',
        pnl: pnl,
        base: positionEntryNotional(p),
      });
    });
    getPodClosedToday(id).forEach(function(t) {
      var pnl = closedTradePnl(t);
      if (Math.abs(pnl) < 0.005) return;
      rows.push({
        pod: id,
        symbol: tradeSymbol(t),
        type: 'Closed today',
        pnl: pnl,
        base: tradeEntryNotional(t),
      });
    });
  });
  return rows.sort(function(a, b) { return Math.abs(b.pnl) - Math.abs(a.pnl); });
}

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
      updatePodsTable();
      updatePerfTable();
      updateAttribution();
      renderFactorRiskTable();
    })
    .catch(function() { _positionsFetchInFlight = false; });
}

function updateFirmMetrics() {
  const ids = Object.keys(pods);
  const nav = getCurrentFirmNav(ids);
  const dailyMove = getFirmDailyMove(ids);
  const act = ids.filter(id => (pods[id].status || '').toUpperCase() === 'ACTIVE').length;
  const pos = _positionsFromApi.length > 0 ? _positionsFromApi.length : ids.reduce((s,id) => {
    const p = getPodPositions(pods[id]);
    return s + (Array.isArray(p) ? p.length : (p && typeof p === 'object' ? Object.keys(p).length : 0));
  }, 0);

  if (ids.length > 0) {
    initialCapital = getFirmStartingCapital(ids);
  }

  const firmInvested = ids.reduce((s,id) => s + getPodInvested(pods[id]), 0);
  const firmCash = ids.reduce((s,id) => s + getPodCash(pods[id]), 0);

  document.getElementById('kpi-nav').textContent    = nav > 0 ? `$${nav.toFixed(0)}` : '—';
  if (nav > 0) document.getElementById('kpi-nav').title = `Invested: $${firmInvested.toFixed(0)} | Cash: $${firmCash.toFixed(0)}`;
  document.getElementById('kpi-active').textContent = act > 0 ? act : '—';
  document.getElementById('kpi-pos').textContent    = pos > 0 ? pos : '—';

  const pnlEl = document.getElementById('kpi-pnl');
  if (nav > 0) {
    pnlEl.textContent = `${formatPnlWithPct(dailyMove.pnl, dailyMove.base || nav, { pct: dailyMove.pct, pctDecimals: 2 })} today`;
    pnlEl.className   = 'kpi-sub ' + (dailyMove.pnl >= 0 ? 'pos' : 'neg');
  } else {
    pnlEl.textContent = '—';
    pnlEl.className   = 'kpi-sub';
  }

  var cpnlEl = document.getElementById('kpi-cpnl');
  var cretEl = document.getElementById('kpi-cret');
  if (cpnlEl && initialCapital > 0) {
    var cpnl = nav - initialCapital;
    var cret = (cpnl / initialCapital) * 100;
    cpnlEl.textContent = formatPnlWithPct(cpnl, initialCapital, { pct: cret, pctDecimals: 2 });
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
  const rawPodNavs = {};
  ids.forEach(id => { rawPodNavs[id] = getPodNav(pods[id]); });
  const rawFirmNav = ids.reduce((s,id) => s + (positiveNumber(rawPodNavs[id]) || 0), 0);
  const point = buildNavHistoryPoint(Date.now(), rawFirmNav, rawPodNavs, sessionActive ? null : _lastValidNavSnapshot);
  if (!point) return;
  // Track drawdown from high-water mark
  var hwm = 0;
  navHistory.forEach(function(h) { if (h.firmNav > hwm) hwm = h.firmNav; });
  if (point.firmNav > hwm) hwm = point.firmNav;
  point.drawdown = hwm > 0 ? (point.firmNav - hwm) / hwm : 0;
  navHistory.push(point);
  rememberNavSnapshot(point);
  if (navHistory.length > MAX_NAV_HISTORY) navHistory = navHistory.slice(-MAX_NAV_HISTORY);
  updateNavChart();
  updateDrawdownChart();
}

function formatNavTimestamp(tsMs) {
  var d = new Date(tsMs || Date.now());
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function formatChartTimeLabel(tsMs) {
  var d = new Date(tsMs || Date.now());
  if (chartPeriod === '24h') {
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  if (chartPeriod === '7d' || chartPeriod === '30d') {
    return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', hour12: false });
  }
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
}

function getChartPeriodCutoff(period) {
  var now = new Date();
  var p = period || chartPeriod || 'all';
  if (p === '24h') return now.getTime() - 24 * 60 * 60 * 1000;
  if (p === '7d') return now.getTime() - 7 * 24 * 60 * 60 * 1000;
  if (p === '30d') return now.getTime() - 30 * 24 * 60 * 60 * 1000;
  if (p === '3m') {
    now.setMonth(now.getMonth() - 3);
    return now.getTime();
  }
  if (p === '6m') {
    now.setMonth(now.getMonth() - 6);
    return now.getTime();
  }
  return null;
}

function recalculateNavDrawdowns() {
  var hwm = 0;
  navHistory.forEach(function(h) {
    var nav = Number(h.firmNav || 0);
    if (nav > hwm) hwm = nav;
    h.drawdown = hwm > 0 ? (nav - hwm) / hwm : 0;
  });
}

function getFilteredNavHistory() {
  var cutoff = getChartPeriodCutoff(chartPeriod);
  if (cutoff === null) return navHistory;
  var filtered = navHistory.filter(function(h) { return h.ts && h.ts >= cutoff; });
  return filtered.length > 0 ? filtered : navHistory.slice(-1);
}

function downsampleNavHistory(rows) {
  if (!rows || rows.length <= MAX_CHART_POINTS) return rows || [];
  var result = [];
  var step = (rows.length - 1) / (MAX_CHART_POINTS - 1);
  for (var i = 0; i < MAX_CHART_POINTS; i += 1) {
    result.push(rows[Math.round(i * step)]);
  }
  return result;
}

function getChartNavHistory() {
  return downsampleNavHistory(getFilteredNavHistory());
}

function navSeriesForPod(rows, podId) {
  return (rows || []).map(function(h) {
    return positiveNumber(h && h.pods ? h.pods[podId] : null);
  });
}

function hasUsableSeries(values) {
  return (values || []).some(function(v) { return v != null && v > 0; });
}

function firmNavDataset(rows, opts) {
  var options = opts || {};
  return {
    label: options.label || 'FIRM NAV',
    data: (rows || []).map(function(h) { return positiveNumber(h.firmNav) || null; }),
    borderColor: options.borderColor || '#ffffff',
    backgroundColor: options.backgroundColor || 'rgba(255,255,255,0.03)',
    borderWidth: options.borderWidth || 2,
    pointRadius: 0,
    tension: 0.3,
    fill: false,
  };
}

function firstPositiveDatasetValue(datasets) {
  for (var i = 0; i < (datasets || []).length; i += 1) {
    var ds = datasets[i] || {};
    if (String(ds.label || '').indexOf('S&P 500') === 0) continue;
    for (var j = 0; j < (ds.data || []).length; j += 1) {
      var v = positiveNumber(ds.data[j]);
      if (v != null && v > 0) return v;
    }
  }
  return null;
}

function benchmarkChartBase(rows, visibleDatasets) {
  if (showFirmNav && rows && rows.length > 0) {
    var firmBase = positiveNumber(rows[0].firmNav);
    if (firmBase != null && firmBase > 0) return firmBase;
  }
  var datasetBase = firstPositiveDatasetValue(visibleDatasets);
  if (datasetBase != null && datasetBase > 0) return datasetBase;
  if (rows && rows.length > 0) {
    return positiveNumber(rows[0].firmNav) || 1;
  }
  return 1;
}

function spBenchmarkDataset(rows, visibleDatasets) {
  if (!showSpBenchmark || !rows || rows.length < 2) return null;
  if (!benchmarkReturns || typeof benchmarkReturns !== 'object') return null;
  var spyBench = benchmarkReturns.equities;
  if (!spyBench || spyBench.return_pct == null) return null;

  var start = benchmarkChartBase(rows, visibleDatasets);
  var ret = Number(spyBench.return_pct) / 100;
  if (!Number.isFinite(ret)) return null;
  var line = rows.map(function(h, idx) {
    var t = idx / Math.max(rows.length - 1, 1);
    return start * (1 + ret * t);
  });
  return {
    label: 'S&P 500 (rebased)',
    data: line,
    borderColor: 'rgba(160,170,185,0.7)',
    borderWidth: 1.5,
    borderDash: [4, 4],
    pointRadius: 0,
    tension: 0.1,
    fill: false,
  };
}

function resizeChartInstance(chart) {
  if (chart && typeof chart.resize === 'function') {
    chart.resize();
  }
}

function resizePerformanceCharts() {
  resizeChartInstance(navChart);
  resizeChartInstance(ddChart);
  resizeChartInstance(_modalNavChart);
}

function schedulePerformanceChartResize() {
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(resizePerformanceCharts);
  }
  setTimeout(resizePerformanceCharts, 80);
}

function refreshPerformanceCharts() {
  updateNavChart();
  updateDrawdownChart();
  schedulePerformanceChartResize();
}

function updateNavChart() {
  var filtered = getChartNavHistory();
  const canvas = document.getElementById('navChart');
  if (!canvas || typeof Chart === 'undefined') return;
  const ctx    = canvas.getContext('2d');
  const labels = filtered.map(h => formatChartTimeLabel(h.ts));
  const ids    = Object.keys(pods).sort();
  const FALLBACK_COLORS = ['#00d4f0','#00d68f','#8b6cff','#f5a623'];
  const datasets = [];
  if (showFirmNav) {
    datasets.push(firmNavDataset(filtered));
  }
  ids.forEach((id, i) => {
    var data = navSeriesForPod(filtered, id);
    if (!hasUsableSeries(data)) return;
    datasets.push({
      label: id.toUpperCase(), data: data,
      borderColor: POD_COLORS[id] || FALLBACK_COLORS[i % FALLBACK_COLORS.length], borderWidth:1,
      pointRadius:0, tension:0.3, fill:false,
    });
  });
  if (datasets.length === 0 && filtered.length > 0) {
    datasets.push(firmNavDataset(filtered, {
      label: 'FIRM NAV',
      borderColor: '#00d4f0',
      backgroundColor: 'rgba(0,212,240,0.04)',
    }));
  }
  var benchmark = spBenchmarkDataset(filtered, datasets);
  if (benchmark) datasets.push(benchmark);

  if (navChart) {
    navChart.data.labels   = labels;
    navChart.data.datasets = datasets;
    navChart.update('none');
    schedulePerformanceChartResize();
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
  schedulePerformanceChartResize();
}

var _modalNavChart = null;
function expandNavChart() {
  var modal = document.getElementById('nav-chart-modal');
  if (!modal) return;
  modal.classList.add('open');
  document.addEventListener('keydown', _navModalKeyHandler);
  // Build the chart inside the modal using same data as navChart
  var ctx = document.getElementById('modal-nav-chart');
  if (!ctx) return;
  if (_modalNavChart) { _modalNavChart.destroy(); _modalNavChart = null; }
  if (!navChart) return;
  _modalNavChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: navChart.data.labels.slice(),
      datasets: navChart.data.datasets.map(function(ds) {
        return Object.assign({}, ds, { data: ds.data.slice() });
      }),
    },
    options: Object.assign({}, navChart.options, {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: Object.assign({}, (navChart.options || {}).plugins, {
        legend: { display: true, position: 'top',
          labels: { color: '#a0b8d0', font: { size: 11, family: "'IBM Plex Mono', monospace" }, padding: 12, usePointStyle: true, pointStyle: 'line' } },
        tooltip: { backgroundColor: '#243050', titleColor: '#00d4f0',
          bodyColor: '#f0f4fa', borderColor: '#4a5e80', borderWidth: 1, padding: 10 },
      }),
    }),
  });
}
function _navModalKeyHandler(e) {
  if (e.key === 'Escape') closeNavChartModal();
}
function closeNavChartModal(e) {
  if (e && e.target && e.target.id !== 'nav-chart-modal') return;
  var modal = document.getElementById('nav-chart-modal');
  if (modal) modal.classList.remove('open');
  document.removeEventListener('keydown', _navModalKeyHandler);
  if (_modalNavChart) { _modalNavChart.destroy(); _modalNavChart = null; }
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
    const nav = getCurrentPodNav(id);
    const sc  = getPodStartingCapital(id, ids);
    const ret = sc > 0 ? ((nav - sc) / sc * 100) : 0;
    const dailyMove = getPodDailyMove(id);
    const realized = getPodRealizedToday(id);
    const openPnl = getPodOpenPnl(id);
    var pm = d.performance_metrics || {};
    var sharpeStr = (pm.sharpe != null && pm.sharpe !== 0) ? Number(pm.sharpe).toFixed(2) : '—';
    return `<tr>
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r">$${nav.toFixed(2)}</td>
      <td class="r ${ret >= 0 ? 'pos' : 'neg'}">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
      <td class="r ${dailyMove.pnl >= 0 ? 'pos' : 'neg'}">${formatPnlWithPct(dailyMove.pnl, dailyMove.base || sc, { pct: dailyMove.pct, pctDecimals: 2 })}</td>
      <td class="r ${realized.pnl >= 0 ? 'pos' : 'neg'}">${formatPnlWithPct(realized.pnl, realized.base || sc, { pctDecimals: 2 })}</td>
      <td class="r ${openPnl.pnl >= 0 ? 'pos' : 'neg'}">${formatPnlWithPct(openPnl.pnl, openPnl.base || sc, { pctDecimals: 2 })}</td>
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
  renderFactorRiskTable();
  renderCorrelationHeatmap();
}

function updateRiskAlertBanner(severity, message) {
  const el = document.getElementById('risk-banner');
  var cls = severity === 'critical' ? 'critical' : (severity === 'info' ? 'info' : 'warning');
  el.className   = 'risk-banner ' + cls;
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
    const guard = String(d.risk_mode || (d.risk_metrics && d.risk_metrics.risk_mode) || 'normal').toUpperCase();
    const guardCls = guard === 'NORMAL' ? 'b-active' : 'b-pending';
    return `<tr>
      <td class="pod-name">${id.toUpperCase()}</td>
      <td class="r">${var95}</td>
      <td class="r">${lev}</td>
      <td class="r ${ddCls}">${dd}</td>
      <td class="r">${pos}</td>
      <td class="r"><span class="badge ${guardCls}">${escapeHtml(guard.replace(/_/g, ' '))}</span></td>
      <td class="r"><span class="badge ${sc}">${st}</span></td>
    </tr>`;
  }).join('');
}

// ─── 10. Execution ─────────────────────────────────────────────────────────
function normalizeLossReviewPayload(data) {
  data = data || {};
  if (!data.active && typeof data === 'object') {
    return { active: data, history: [], triggered_count: 0 };
  }
  return {
    active: data.active || {},
    history: data.history || [],
    triggered_count: Number(data.triggered_count || 0)
  };
}

function renderLossReviews(data) {
  lossReviewState = normalizeLossReviewPayload(data || lossReviewState);
  var panel = document.getElementById('loss-review-panel');
  var badge = document.getElementById('loss-review-badge');
  if (!panel) return;

  var active = lossReviewState.active || {};
  var reviews = Object.keys(active).sort().map(function(pid) { return active[pid]; });
  var triggered = reviews.filter(function(r) { return r && r.triggered; });
  if (badge) badge.textContent = triggered.length + ' active / ' + reviews.length + ' pods';

  if (!reviews.length) {
    panel.innerHTML = '<div class="empty"><div class="empty-txt">No loss reviews yet</div></div>';
    return;
  }

  panel.innerHTML = reviews.map(function(r) {
    r = r || {};
    var status = String(r.status || 'clear').toLowerCase();
    var statusCls = status === 'paused' ? 'critical' : (status === 'restricted' || status === 'watch' ? 'warning' : 'clear');
    var dailyCls = Number(r.daily_pnl || 0) >= 0 ? 'pos' : 'neg';
    var contributors = (r.top_contributors || []).slice(0, 4);
    var contribHtml = contributors.length ? contributors.map(function(c) {
      var pnl = Number(c.pnl || 0);
      var cls = pnl >= 0 ? 'pos' : 'neg';
      var navImpact = Number(c.nav_impact_pct || 0) * 100;
      return '<tr>' +
        '<td>' + escapeHtml(c.symbol || '') + '<div class="muted">' + escapeHtml(String(c.source || '').replace(/_/g, ' ')) + '</div></td>' +
        '<td class="r ' + cls + '">' + formatPnlWithPct(pnl, Number(c.notional || 0), { pct: Number(c.pnl_pct || 0) * 100, pctDecimals: 2 }) + '</td>' +
        '<td class="r ' + cls + '">' + (navImpact >= 0 ? '+' : '') + navImpact.toFixed(2) + '% NAV</td>' +
      '</tr>';
    }).join('') : '<tr><td colspan="3" class="empty"><div class="empty-txt">No negative contributor</div></td></tr>';

    return '<div class="loss-review-card ' + statusCls + '">' +
      '<div class="lr-head">' +
        '<div><div class="lr-pod">' + escapeHtml(String(r.pod_id || '').toUpperCase()) + '</div>' +
        '<div class="lr-reason">' + escapeHtml(r.trigger_reason || '') + '</div></div>' +
        '<span class="lr-status ' + statusCls + '">' + escapeHtml(status) + '</span>' +
      '</div>' +
      '<div class="lr-metrics">' +
        '<div><span>Daily P&L</span><b class="' + dailyCls + '">' + formatPnlWithPct(Number(r.daily_pnl || 0), Number(r.baseline_nav || r.starting_capital || 0), { pct: Number(r.daily_pnl_pct || 0) * 100, pctDecimals: 2 }) + '</b></div>' +
        '<div><span>Open</span><b class="' + (Number(r.open_unrealized_pnl || 0) >= 0 ? 'pos' : 'neg') + '">' + formatSignedMoney(Number(r.open_unrealized_pnl || 0)) + '</b></div>' +
        '<div><span>Realized</span><b class="' + (Number(r.realized_today || 0) >= 0 ? 'pos' : 'neg') + '">' + formatSignedMoney(Number(r.realized_today || 0)) + '</b></div>' +
      '</div>' +
      '<div class="lr-subtitle">Loss Drivers</div>' +
      '<div class="tbl-wrap lr-table-wrap"><table class="dtbl"><thead><tr><th>Symbol</th><th class="r">P&L</th><th class="r">NAV Impact</th></tr></thead><tbody>' + contribHtml + '</tbody></table></div>' +
      '<div class="lr-actions">' +
        '<details open><summary>CRO Action</summary><p>' + escapeHtml(r.cro_action || '') + '</p></details>' +
        '<details><summary>CIO Decision</summary><p>' + escapeHtml(r.cio_decision || '') + '</p></details>' +
        '<details><summary>PM Defense Prompt</summary><p>' + escapeHtml(r.pm_defense_prompt || '') + '</p></details>' +
      '</div>' +
    '</div>';
  }).join('');
}

function fetchLossReviews() {
  return fetchJsonWithTimeout('/api/loss-reviews', {}, 3500)
    .then(function(data) {
      renderLossReviews(data);
      return data;
    })
    .catch(function() {
      renderLossReviews(lossReviewState);
    });
}

function getCommodityOpenPositions() {
  var positions = [];
  if (_positionsFromApi && _positionsFromApi.length > 0) {
    positions = _positionsFromApi.filter(function(p) {
      return String(p._pod || p.pod_id || '').toLowerCase() === 'commodities';
    });
  }
  if (positions.length === 0) {
    var pod = pods.commodities || {};
    positions = getPodPositions(pod).map(function(p) {
      return Object.assign({ _pod: 'commodities' }, p || {});
    });
  }
  return positions;
}

function buildClientCommodityFactorReport() {
  var pod = pods.commodities || {};
  var positions = getCommodityOpenPositions();
  if (!positions.length) return { factors: {}, source: 'client_fallback' };

  var nav = getPodNav(pod) || positions.reduce(function(sum, p) {
    return sum + Math.abs(Number(p.notional || ((p.qty || 0) * (p.current_price || p.cost_basis || 0))) || 0);
  }, 0);
  var factors = {};

  positions.forEach(function(p) {
    var symbol = String(p.symbol || '').toUpperCase();
    var profile = COMMODITY_FACTOR_PROFILES[symbol];
    var notional = Math.abs(Number(p.notional || ((p.qty || 0) * (p.current_price || p.cost_basis || 0))) || 0);
    if (!profile || notional <= 0) return;

    Object.keys(profile).forEach(function(factor) {
      var factorNotional = notional * Number(profile[factor] || 0);
      if (factorNotional <= 0) return;
      if (!factors[factor]) {
        factors[factor] = {
          notional: 0,
          pct_nav: 0,
          limit_pct: COMMODITY_FACTOR_LIMITS[factor] || 0.40,
          breach: false,
          symbols: []
        };
      }
      factors[factor].notional += factorNotional;
      if (factors[factor].symbols.indexOf(symbol) === -1) factors[factor].symbols.push(symbol);
    });
  });

  Object.keys(factors).forEach(function(factor) {
    factors[factor].pct_nav = nav > 0 ? factors[factor].notional / nav : 0;
    factors[factor].breach = factors[factor].pct_nav > factors[factor].limit_pct;
  });

  return { factors: factors, risk_mode: 'dashboard_fallback', source: 'client_fallback' };
}

function renderFactorRiskTable() {
  var tbody = document.getElementById('factor-risk-table');
  if (!tbody) return;
  var pod = pods.commodities || pods.Commodities || null;
  var report = pod && (pod.factor_exposures || (pod.risk_metrics && pod.risk_metrics.factor_exposures));
  if (!report || !report.factors || Object.keys(report.factors || {}).length === 0) {
    report = buildClientCommodityFactorReport();
  }
  var factors = report && report.factors ? report.factors : {};
  var rows = Object.keys(factors).sort(function(a, b) {
    return (factors[b].pct_nav || 0) - (factors[a].pct_nav || 0);
  });
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty"><div class="empty-txt">No commodity factor exposure yet</div><div class="empty-hint">Open commodity positions will be mapped here by shared risk factor</div></td></tr>';
    return;
  }
  tbody.innerHTML = rows.slice(0, 10).map(function(factor) {
    var row = factors[factor] || {};
    var pct = (row.pct_nav || 0) * 100;
    var lim = (row.limit_pct || 0) * 100;
    var breach = !!row.breach;
    var badge = breach ? '<span class="badge b-halted">BREACH</span>' : '<span class="badge b-active">OK</span>';
    var syms = Array.isArray(row.symbols) ? row.symbols.join(', ') : '';
    return `<tr>
      <td class="pod-name">${factor.replace(/_/g, ' ').toUpperCase()}</td>
      <td>${syms ? escapeHtml(syms) : '-'}</td>
      <td class="r ${breach ? 'neg' : ''}">${pct.toFixed(1)}%</td>
      <td class="r">${lim.toFixed(1)}%</td>
      <td class="r">${badge}</td>
    </tr>`;
  }).join('');
}

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

function executionReasonForDisplay(t) {
  var reason = t.reason || '';
  var symbol = String(t.symbol || '');
  var isGeneric = !reason || reason.toLowerCase() === 'order rejected';
  if (t.status === 'REJECTED' && isGeneric && symbol.indexOf('/') >= 0) {
    return 'Broker rejected before accepting the crypto order. Crypto orders must use GTC/IOC time-in-force; restart the server if this generic reason persists.';
  }
  if (t.status === 'REJECTED' && isGeneric) {
    return 'Broker rejected before accepting the order; restart the server if the detailed stage/reason is still missing.';
  }
  return reason;
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
        ts: o.timestamp || '', orderId: oid,
        stage: o.stage || '',
        reason: o.reason || o.rejection_detail || o.rejection_reason || ''
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
    document.getElementById('exec-table').innerHTML = '<tr><td colspan="8" class="empty"><div class="empty-txt">No trades yet</div></td></tr>';
    return;
  }
  document.getElementById('exec-table').innerHTML = allItems.slice(0, 30).map(function(t) {
    var sc = t.side === 'BUY' ? 'b-buy' : 'b-sell';
    var ss = t.status === 'FILLED' ? 'b-filled' : t.status === 'PENDING' ? 'b-pending' : t.status === 'PARTIAL' ? 'b-partial' : t.status === 'REJECTED' ? 'b-rejected' : 'b-pending';
    var reason = executionReasonForDisplay(t);
    var stage = (t.stage || (t.status === 'REJECTED' && reason ? 'broker' : '')).replace(/_/g, ' ');
    var reasonCell = reason ? '<span class="exec-reason" title="' + escapeHtml(reason) + '">' + escapeHtml(reason) + '</span>' : '-';
    return '<tr>' +
      '<td>' + (t.podId || 'unknown').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(t.symbol || '') + '</td>' +
      '<td><span class="badge ' + sc + '">' + (t.side || '') + '</span></td>' +
      '<td class="r">' + (t.qty || 0) + '</td>' +
      '<td class="r">$' + (t.price || 0).toFixed(2) + '</td>' +
      '<td class="r"><span class="badge ' + ss + '">' + (t.status || '') + '</span></td>' +
      '<td>' + (stage ? '<span class="exec-stage">' + escapeHtml(stage.toUpperCase()) + '</span>' : '-') + '</td>' +
      '<td>' + reasonCell + '</td>' +
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
  const baseCapital = getAllocationBaseCapital(names);
  const allocWeights = normalizeAllocationWeights(latestAllocWeights, names);
  document.getElementById('alloc-grid').innerHTML = names.map(id => {
    const weight = allocWeights[id] || 0;
    const allocation = baseCapital * weight;
    const currentNav = getPodNav(pods[id] || {});
    const nav = currentNav > 0 ? currentNav : allocation;
    const pct = weight > 0 ? (weight * 100).toFixed(0) + '%' : '-';
    const allocationLabel = allocation > 0 ? 'Allocated $' + allocation.toFixed(0) : 'Allocated -';
    const navDelta = currentNav > 0 && allocation > 0 ? currentNav - allocation : 0;
    const navClass = navDelta > 0.005 ? ' pos' : navDelta < -0.005 ? ' neg' : '';
    return `<div class="alloc-tile">
      <div class="alloc-pod">${id.toUpperCase()}</div>
      <div class="alloc-val${navClass}">$${nav > 0 ? nav.toFixed(2) : '—'}</div>
      <div class="alloc-pct">Current NAV</div>
      <div class="alloc-sub">${allocationLabel} · ${pct}</div>
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
      ${d.reasoning ? `<div class="gov-card-sub">${d.reasoning}</div>` : ''}
    </div>`;
  }).join('');
}

// ─── 12. Top Holdings ──────────────────────────────────────────────────────
// Uses _positionsFromApi (fetched from /api/positions) — same as drilldown and KPI
function positionPriceCell(p, fallback) {
  var price = Number(p.current_price || fallback || 0);
  var source = String(p.price_source || '').toUpperCase();
  var stale = !!p.price_stale;
  var meta = '';
  if (stale) {
    meta = '<div class="quote-meta quote-stale">STALE' + (source ? ' - ' + escapeHtml(source) : '') + '</div>';
  } else if (source) {
    meta = '<div class="quote-meta">' + escapeHtml(source) + '</div>';
  }
  return '<div class="price-stack">$' + price.toFixed(2) + meta + '</div>';
}

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
    var notional = positionCurrentNotional(p);
    var entryNotional = positionEntryNotional(p);
    var podEsc = escapeHtml(p._pod || '');
    var symEsc = escapeHtml(p.symbol || '');
    var entryDate = escapeHtml(p.entry_date || '—');
    var thesis = p.entry_thesis ? escapeHtml(p.entry_thesis) : '';
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
      '<td class="r">' + positionPriceCell(p, entry) + '</td>' +
      '<td class="r ' + pc + '">' + formatPnlWithPct(pnl, entryNotional, { pct: p.pnl_pct, pctDecimals: 2 }) + '</td>' +
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
    else /* notional */            { av = positionCurrentNotional(a); bv = positionCurrentNotional(b); }
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
var _positionDetailRequestToken = 0;

function positionModalKeyHandler(e) {
  if (e.key === 'Escape') closePositionModal();
}

function setPositionDetailsOpen(group, open) {
  var overlay = document.getElementById('pos-modal-overlay');
  if (!overlay) return;
  var selector = group === 'fills' ? '.pos-fills details' : group === 'reasoning' ? '.pmh-list details' : 'details';
  overlay.querySelectorAll(selector).forEach(function(detail) {
    detail.open = !!open;
  });
}

function enhancePositionModalDetails(overlay) {
  if (!overlay) return;
  overlay.querySelectorAll('.pos-fills details, .pmh-list details, .evidence-list details').forEach(function(detail) {
    detail.addEventListener('toggle', function() {
      if (detail.open) detail.scrollIntoView({ block: 'nearest' });
    });
  });
}

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
  document.removeEventListener('keydown', positionModalKeyHandler);
  document.addEventListener('keydown', positionModalKeyHandler);
  _openModalPodId = podId;
  _openModalSymbol = symbol;
  var requestToken = ++_positionDetailRequestToken;

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
    .then(function(d) {
      if (requestToken !== _positionDetailRequestToken || _openModalPodId !== podId || _openModalSymbol !== symbol) return;
      renderPositionModal(d, overlay);
    })
    .catch(function() {
      clearTimeout(timeout);
      if (requestToken !== _positionDetailRequestToken || _openModalPodId !== podId || _openModalSymbol !== symbol) return;
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
    take_profit_levels: pos.take_profit_levels || [],
    take_profit_hits: pos.take_profit_hits || [],
    max_hold_days: pos.max_hold_days || 0,
    conviction: pos.conviction || 0,
    thesis_status: pos.thesis_status || 'unknown',
    thesis_issues: pos.thesis_issues || [],
    thesis_review: pos.thesis_review || {},
    evidence_packet: pos.evidence_packet || {},
    evidence_packets: pos.evidence_packets || [],
    entry_macro_regime: pos.entry_macro_regime || '',
    days_held: daysHeld,
    fills: pos.fills || [],
    partial_exits: pos.partial_exits || []
  };
}

function closePositionModal() {
  var o = document.getElementById('pos-modal-overlay');
  if (o) o.classList.remove('open');
  document.removeEventListener('keydown', positionModalKeyHandler);
  _positionDetailRequestToken++;
  _openModalPodId = null;
  _openModalSymbol = null;
}

function evidenceStageLabel(value) {
  return String(value || 'check').replace(/_/g, ' ').toUpperCase();
}

function renderEvidenceChecks(checks) {
  if (!Array.isArray(checks) || !checks.length) {
    return '<div class="pos-empty">No recorded checks for this packet.</div>';
  }
  return '<div class="evidence-list">' + checks.map(function(check, idx) {
    check = check || {};
    var status = String(check.status || 'INFO').toUpperCase();
    var score = check.score != null ? 'Score ' + Number(check.score).toFixed(2) : '';
    var meta = [];
    if (check.source) meta.push(String(check.source));
    if (check.price != null) meta.push('$' + Number(check.price).toFixed(2));
    if (check.price_age_seconds != null) meta.push(String(check.price_age_seconds) + 's old');
    return '<details class="evidence-check" data-detail-key="evidence-check-' + idx + '">' +
      '<summary class="evidence-check-summary">' +
        '<span class="badge ' + executionTruthBadgeClass(status) + '">' + escapeHtml(status) + '</span>' +
        '<span class="evidence-check-name">' + escapeHtml(evidenceStageLabel(check.name)) + '</span>' +
        '<span class="evidence-check-score">' + escapeHtml(score || meta.join(' | ')) + '</span>' +
        '<span class="pmh-caret">v</span>' +
      '</summary>' +
      '<div class="pmh-text">' + escapeHtml(check.detail || '') +
        (check.warnings && check.warnings.length ? '<br><b>Warnings:</b><br>' + escapeHtml(check.warnings.join('\n')) : '') +
        (check.issues && check.issues.length ? '<br><b>Issues:</b><br>' + escapeHtml(check.issues.join('\n')) : '') +
      '</div>' +
    '</details>';
  }).join('') + '</div>';
}

function renderEvidenceItems(items) {
  if (!Array.isArray(items) || !items.length) return '<div class="pos-empty">No items captured.</div>';
  return items.map(function(item) {
    item = item || {};
    var title = item.title || item.text || 'Untitled item';
    var bits = [];
    if (item.source) bits.push(item.source);
    if (item.probability != null) bits.push('p=' + Number(item.probability).toFixed(2));
    if (item.sentiment != null) bits.push('sent=' + Number(item.sentiment).toFixed(2));
    if (item.impact != null) bits.push('impact=' + Number(item.impact).toFixed(2));
    return '<div class="evidence-item">' +
      '<div class="evidence-item-title">' + escapeHtml(title) + '</div>' +
      (bits.length ? '<div class="evidence-item-meta">' + escapeHtml(bits.join(' | ')) + '</div>' : '') +
    '</div>';
  }).join('');
}

function renderSpecialistBriefItems(items) {
  if (!Array.isArray(items) || !items.length) return '<div class="pos-empty">No specialist briefs captured.</div>';
  return items.slice(0, 8).map(function(item) {
    item = item || {};
    var support = Array.isArray(item.supporting_evidence) ? item.supporting_evidence.join('; ') : '';
    var oppose = Array.isArray(item.opposing_evidence) ? item.opposing_evidence.join('; ') : '';
    return '<div class="evidence-item">' +
      '<div class="evidence-item-title">' + escapeHtml((item.type || 'specialist') + (item.symbol ? ' ' + item.symbol : '')) + '</div>' +
      '<div class="evidence-item-meta">' + escapeHtml(item.question || '') + '</div>' +
      '<div class="evidence-note">' + escapeHtml(item.conclusion || '') + '</div>' +
      (support ? '<div class="evidence-item-meta">Supports: ' + escapeHtml(support) + '</div>' : '') +
      (oppose ? '<div class="evidence-item-meta">Pushback: ' + escapeHtml(oppose) + '</div>' : '') +
    '</div>';
  }).join('');
}

function renderEvidencePacket(packet) {
  if (!packet || typeof packet !== 'object' || !Object.keys(packet).length) return '';
  var trade = packet.trade || {};
  var market = packet.market_context || {};
  var position = packet.position_context || {};
  var evidence = packet.evidence || {};
  var missing = Array.isArray(packet.missing_evidence) ? packet.missing_evidence : [];
  var fred = market.fred || {};
  var fredHtml = Object.keys(fred).length
    ? Object.keys(fred).map(function(k) {
        return '<span class="evidence-chip">' + escapeHtml(k + ': ' + fred[k]) + '</span>';
      }).join('')
    : '<span class="evidence-muted">No FRED metrics captured.</span>';
  var triggers = Array.isArray(packet.review_triggers) ? packet.review_triggers : [];
  return '<div class="pos-section">' +
    '<div class="pos-section-title">Trade Evidence Packet</div>' +
    '<div class="evidence-card">' +
      '<div class="evidence-grid">' +
        '<div><span>Action</span><b>' + escapeHtml((trade.side || '') + ' ' + (trade.qty || '')) + '</b></div>' +
        '<div><span>Conviction</span><b>' + (trade.conviction != null ? (Number(trade.conviction) * 100).toFixed(0) + '%' : '-') + '</b></div>' +
        '<div><span>Price Source</span><b>' + escapeHtml(market.price_source || '-') + '</b></div>' +
        '<div><span>Price Age</span><b>' + (market.price_age_seconds != null ? escapeHtml(String(market.price_age_seconds) + 's') : '-') + '</b></div>' +
        '<div><span>Macro Regime</span><b>' + escapeHtml(market.macro_regime || '-') + '</b></div>' +
        '<div><span>Existing Qty</span><b>' + escapeHtml(String(position.existing_qty || 0)) + '</b></div>' +
      '</div>' +
      (missing.length ? '<div class="evidence-warning"><b>Missing / weak evidence:</b><br>' + escapeHtml(missing.join('\n')) + '</div>' : '<div class="thesis-ok">No missing-evidence warnings recorded.</div>') +
      '<details class="evidence-subsection" open data-detail-key="evidence-checks"><summary>Checks</summary>' + renderEvidenceChecks(packet.checks || []) + '</details>' +
      '<details class="evidence-subsection" data-detail-key="evidence-facts"><summary>Market Facts</summary><div class="evidence-chip-row">' + fredHtml + '</div></details>' +
      '<details class="evidence-subsection" data-detail-key="evidence-catalysts"><summary>Catalyst Trail</summary>' + renderEvidenceItems(evidence.catalysts || []) +
        (evidence.catalyst_reasoning ? '<div class="evidence-note"><b>PM catalyst reasoning:</b> ' + escapeHtml(evidence.catalyst_reasoning) + '</div>' : '') +
      '</details>' +
      '<details class="evidence-subsection" data-detail-key="evidence-specialists"><summary>Specialist Briefs</summary>' + renderSpecialistBriefItems(evidence.specialist_briefs || []) + '</details>' +
      (evidence.committee_review && evidence.committee_review.decision
        ? '<details class="evidence-subsection" data-detail-key="evidence-ic"><summary>Investment Committee Review</summary><div class="evidence-item"><div class="evidence-item-title">' + escapeHtml(evidence.committee_review.decision || '') + '</div><div class="evidence-note">' + escapeHtml(evidence.committee_review.reason || '') + '</div></div></details>'
        : '') +
      '<details class="evidence-subsection" data-detail-key="evidence-news"><summary>News Evidence</summary>' + renderEvidenceItems(evidence.top_news || []) + '</details>' +
      '<details class="evidence-subsection" data-detail-key="evidence-poly"><summary>Prediction Market Evidence</summary>' + renderEvidenceItems(evidence.top_prediction_markets || []) + '</details>' +
      (packet.invalidation ? '<div class="evidence-note"><b>Invalidation:</b> ' + escapeHtml(packet.invalidation) + '</div>' : '') +
      (triggers.length ? '<div class="evidence-note"><b>Review triggers:</b> ' + escapeHtml(triggers.join(', ')) + '</div>' : '') +
    '</div>' +
  '</div>';
}

function latestEvidencePacket(data) {
  if (data && data.evidence_packet && typeof data.evidence_packet === 'object' && Object.keys(data.evidence_packet).length) {
    return data.evidence_packet;
  }
  var packets = data && Array.isArray(data.evidence_packets) ? data.evidence_packets : [];
  for (var i = packets.length - 1; i >= 0; i--) {
    if (packets[i] && typeof packets[i] === 'object' && Object.keys(packets[i]).length) {
      return packets[i];
    }
  }
  return null;
}

function renderFillEvidence(packet) {
  if (!packet || typeof packet !== 'object' || !Object.keys(packet).length) return '';
  var checks = Array.isArray(packet.checks) ? packet.checks : [];
  var chips = checks.slice(0, 5).map(function(check) {
    var status = String((check || {}).status || 'INFO').toUpperCase();
    return '<span class="evidence-mini-chip ' + executionTruthBadgeClass(status) + '">' +
      escapeHtml(evidenceStageLabel((check || {}).name) + ': ' + status) +
    '</span>';
  }).join('');
  var missing = Array.isArray(packet.missing_evidence) ? packet.missing_evidence : [];
  return '<div class="fill-evidence">' +
    '<div class="fill-reason-label">Evidence Checks</div>' +
    '<div class="evidence-mini-row">' + (chips || '<span class="evidence-muted">No checks recorded.</span>') + '</div>' +
    (missing.length ? '<div class="evidence-mini-warning">' + escapeHtml(missing.slice(0, 4).join('\n')) + '</div>' : '') +
  '</div>';
}

function renderPositionModal(d, overlay) {
  var previousDetailState = {};
  if (overlay) {
    overlay.querySelectorAll('details[data-detail-key]').forEach(function(detail) {
      previousDetailState[detail.getAttribute('data-detail-key')] = !!detail.open;
    });
  }

  var pnl = d.unrealized_pnl || 0;
  var pnlCls = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
  var pnlPct = d.pnl_pct || 0;
  var totalRetCls = pnlPct >= 0 ? 'pos' : 'neg';

  // SL / TP progress bar
  var slPct = ((d.stop_loss_pct || 0.05) * 100).toFixed(1);
  var tpPct = ((d.take_profit_pct || 0.15) * 100).toFixed(1);
  var tpLevels = Array.isArray(d.take_profit_levels) ? d.take_profit_levels : [];
  var tpHits = Array.isArray(d.take_profit_hits) ? d.take_profit_hits : [];
  var maxTierPct = tpLevels.reduce(function(maxVal, level) {
    return Math.max(maxVal, Number(level.trigger_pct || 0));
  }, 0);
  var currentPnlPct = pnlPct;
  var barMin = -(d.stop_loss_pct || 0.05) * 100;
  var barMax = Math.max((d.take_profit_pct || 0.15), maxTierPct) * 100;
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
      reasoning: d.entry_thesis ? 'Entry: ' + cleanThesis(d.entry_thesis, d.symbol) : 'Position opened (fill data predates this session)',
      _synthetic: true
    }];
  }
  var fillsHtml = '';
  if (fills.length > 0) {
    fillsHtml = fills.map(function(f, idx) {
      var isBuy = f.side === 'BUY';
      var cls = (isBuy ? 'fill-buy' : 'fill-sell') + (f._synthetic ? ' fill-synthetic' : '');
      var icon = isBuy ? '+' : '-';
      var ts = f.timestamp ? new Date(f.timestamp).toLocaleDateString() : '—';
      var thesisText = cleanThesis(f.entry_thesis || f.reasoning || '', d.symbol);
      var conv = f.conviction > 0 ? ' · ' + (f.conviction * 100).toFixed(0) + '% conviction' : '';
      var tag = f.strategy_tag ? ' · ' + escapeHtml(f.strategy_tag) : '';
      var openAttr = idx === 0 ? ' open' : '';
      return '<details class="fill-entry ' + cls + '" data-detail-key="fill-' + idx + '"' + openAttr + '>' +
        '<summary class="fill-summary">' +
          '<span class="fill-icon">' + icon + '</span>' +
          '<span class="fill-info">' +
            '<span class="fill-side">' + escapeHtml(f.side || '') + '</span> ' +
            '<span class="fill-qty">' + escapeHtml(String(f.qty || 0)) + '</span> @ ' +
            '<span class="fill-px">$' + (f.fill_price || 0).toFixed(2) + '</span>' +
            '<span class="fill-meta">' + conv + tag + '</span>' +
          '</span>' +
          '<span class="fill-date">' + escapeHtml(ts) + '</span>' +
          '<span class="fill-caret">▾</span>' +
        '</summary>' +
        (thesisText
          ? '<div class="fill-reason"><div class="fill-reason-label">Entry / Expansion Thesis</div>' + escapeHtml(thesisText) + '</div>'
          : '<div class="fill-reason fill-reason-empty">No PM reasoning captured for this fill.</div>') +
        renderFillEvidence(f.evidence_packet) +
      '</details>';
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
        var rpBase = tradeEntryNotional({ qty: e.qty_sold, entry_price: e.entry_price || d.cost_basis });
        return '<div class="exit-entry">' +
          '<span class="exit-date">' + (e.date || '—') + '</span>' +
          '<span class="exit-qty">Sold ' + e.qty_sold + ' (' + e.pct_of_original + '% of original)</span>' +
          '<span class="exit-px">@ $' + (e.exit_price || 0).toFixed(2) + '</span>' +
          '<span class="exit-pnl ' + rpCls + '">P&L: ' + formatPnlWithPct(rpnl, rpBase, { moneyDecimals: 4, pctDecimals: 2 }) + '</span>' +
        '</div>';
      }).join('') + '</div>';
  }

  var convPct = ((d.conviction || 0) * 100).toFixed(0);

  var avgEntry = d.cost_basis || 0;
  var thesis = cleanThesis(d.entry_thesis || '', d.symbol);
  var review = d.thesis_review || {};
  var thesisStatus = String(d.thesis_status || review.status || 'unknown').toLowerCase();
  var thesisIssues = d.thesis_issues || review.issues || [];
  var thesisIssueHtml = thesisIssues && thesisIssues.length
    ? '<ul class="thesis-issues">' + thesisIssues.map(function(issue) {
        return '<li>' + escapeHtml(String(issue)) + '</li>';
      }).join('') + '</ul>'
    : '<div class="thesis-ok">No lifecycle issues detected.</div>';
  var thesisMonitors = review.monitors && review.monitors.length
    ? '<div class="thesis-monitors">Monitors: ' + escapeHtml(review.monitors.join(', ')) + '</div>'
    : '';
  var fillControls = fills.length > 0
    ? '<span class="pos-section-actions">' +
        '<button type="button" class="pos-detail-btn" onclick="setPositionDetailsOpen(\'fills\', true)">Expand all</button>' +
        '<button type="button" class="pos-detail-btn" onclick="setPositionDetailsOpen(\'fills\', false)">Collapse all</button>' +
      '</span>'
    : '';
  var tpLevelsHtml = '';
  if (tpLevels.length) {
    tpLevelsHtml = '<div class="tp-levels">' + tpLevels.map(function(level, idx) {
      var trigger = Number(level.trigger_pct || 0) * 100;
      var closePct = Number(level.close_pct || 0) * 100;
      var hit = tpHits.indexOf(idx) !== -1;
      var label = level.label || ('TP' + (idx + 1));
      return '<div class="tp-level ' + (hit ? 'hit' : 'open') + '">' +
        '<span class="tp-label">' + escapeHtml(label) + '</span>' +
        '<span class="tp-trigger">+' + trigger.toFixed(1) + '%</span>' +
        '<span class="tp-close">close ' + closePct.toFixed(0) + '%</span>' +
        '<span class="tp-status">' + (hit ? 'hit' : 'open') + '</span>' +
      '</div>';
    }).join('') + '</div>';
  }

  overlay.innerHTML = '<div class="pos-modal">' +
    '<button class="pos-modal-close" onclick="closePositionModal()">&times;</button>' +
    // Header
    '<div class="pos-hdr">' +
      '<div class="pos-hdr-left">' +
        '<span class="pos-symbol">' + tickerDisplay(d.symbol) + '</span>' +
        '<span class="badge b-' + escapeHtml(d.pod_id) + '">' + escapeHtml(d.pod_id).toUpperCase() + '</span>' +
      '</div>' +
      '<div class="pos-hdr-right">' +
        '<div class="pos-hdr-pnl ' + pnlCls + '">' + formatPnlWithPct(pnl, Math.abs((d.qty || 0) * (d.cost_basis || 0)), { moneyDecimals: 4, pct: pnlPct, pctDecimals: 2 }) + '</div>' +
      '</div>' +
    '</div>' +
    // Summary grid
    '<div class="pos-grid">' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Entry Date</div><div class="pos-cell-val">' + (d.entry_date || '—') + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Days Held</div><div class="pos-cell-val">' + (d.days_held > 0 ? d.days_held : (d.entry_date ? '< 1' : '—')) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Avg Entry</div><div class="pos-cell-val">$' + (d.cost_basis || 0).toFixed(2) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Current Price</div><div class="pos-cell-val">' + positionPriceCell(d, 0) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Quantity</div><div class="pos-cell-val">' + (d.qty || 0) + '</div></div>' +
      '<div class="pos-cell"><div class="pos-cell-lbl">Total Return</div><div class="pos-cell-val ' + totalRetCls + '">' + (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%</div></div>' +
    '</div>' +
    '<div class="pos-section">' +
      '<div class="pos-section-title">Thesis Health</div>' +
      '<div class="thesis-health thesis-' + escapeHtml(thesisStatus) + '">' +
        '<div class="thesis-health-row">' +
          '<span class="thesis-status">' + escapeHtml(thesisStatus.toUpperCase()) + '</span>' +
          '<span class="thesis-score">Score ' + ((review.score != null ? Number(review.score) : 0).toFixed(2)) + '</span>' +
          (review.block_adds ? '<span class="thesis-block">Adds blocked</span>' : '') +
        '</div>' +
        thesisIssueHtml +
        thesisMonitors +
      '</div>' +
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
      (tpLevelsHtml || '<div class="pos-exit-meta">Single TP closes the remaining position if reached.</div>') +
      '<div class="pos-exit-meta">Max hold: ' + (d.max_hold_days > 0 ? d.max_hold_days + ' days' : 'No limit (thesis-driven)') + '</div>' +
    '</div>' +
    // Fill timeline
    '<div class="pos-section">' +
      '<div class="pos-section-title">Fill Timeline (' + fillsCount + (fills.length > 0 && fills[0]._synthetic ? ' — entry reconstructed' : ' fills') + ')</div>' +
      (fillControls ? '<div class="pos-section-controlbar">' + fillControls + '</div>' : '') +
      '<div class="pos-fills">' + fillsHtml + '</div>' +
    '</div>' +
    // Partial exits
    exitsHtml +
    // Entry thesis
    (thesis ? '<div class="pos-section"><div class="pos-section-title">Entry Thesis</div><div class="pos-thesis">' + escapeHtml(thesis) + '</div></div>' : '') +
    // Evidence packet
    renderEvidencePacket(latestEvidencePacket(d)) +
    // Decision replay
    (function() {
      var chain = d.decision_chain || [];
      if (!chain.length) return '';
      var items = chain.map(function(c, idx) {
        var status = String(c.status || 'INFO').toUpperCase();
        var llm = c.llm && c.llm.model ? c.llm.provider + '/' + c.llm.model + ' · ' + c.llm.task : '';
        var ts = c.timestamp ? new Date(c.timestamp).toLocaleString() : '';
        return '<details class="pmh-entry" data-detail-key="decision-' + idx + '"' + (idx === 0 ? ' open' : '') + '>' +
          '<summary class="pmh-header">' +
            '<span class="badge ' + executionTruthBadgeClass(status) + '">' + escapeHtml(status) + '</span>' +
            '<span class="rh-badge">' + escapeHtml(String(c.stage || 'decision').replace(/_/g, ' ')) + '</span>' +
            '<span class="rh-ts">' + escapeHtml(ts) + '</span>' +
            (llm ? '<span class="audit-model">' + escapeHtml(llm) + '</span>' : '') +
            '<span class="pmh-caret">▾</span>' +
          '</summary>' +
          '<div class="pmh-text"><b>' + escapeHtml(c.summary || '') + '</b>' +
          (c.detail ? '<br>' + escapeHtml(c.detail) : '') + '</div>' +
        '</details>';
      }).join('');
      return '<div class="pos-section"><div class="pos-section-title">Decision Replay (' + chain.length + ' events)</div>' +
        '<div class="pmh-list">' + items + '</div></div>';
    })() +
    // PM Reasoning History
    (function() {
      var rh = d.reasoning_history;
      if (!rh || !rh.length) return '';
      var items = rh.map(function(r, idx) {
        var actionCls = r.action === 'HOLD' ? 'rh-hold' : r.action === 'BUY' ? 'rh-buy' : 'rh-sell';
        var ts = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';
        var conv = r.conviction > 0 ? ' (' + (r.conviction * 100).toFixed(0) + '% conviction)' : '';
        var text = cleanThesis(r.reasoning || '', d.symbol);
        return '<details class="pmh-entry ' + actionCls + '" data-detail-key="reason-' + idx + '"' + (idx === 0 ? ' open' : '') + '>' +
          '<summary class="pmh-header"><span class="rh-badge">' + escapeHtml(r.action) + '</span><span class="rh-ts">' + escapeHtml(ts + conv) + '</span><span class="pmh-caret">▾</span></summary>' +
          '<div class="pmh-text">' + escapeHtml(text || 'No reasoning captured.') + '</div>' +
        '</details>';
      }).join('');
      var controls = '<span class="pos-section-actions">' +
        '<button type="button" class="pos-detail-btn" onclick="setPositionDetailsOpen(\'reasoning\', true)">Expand all</button>' +
        '<button type="button" class="pos-detail-btn" onclick="setPositionDetailsOpen(\'reasoning\', false)">Collapse all</button>' +
      '</span>';
      return '<div class="pos-section"><div class="pos-section-title pos-section-title-row"><span>PM Reasoning History (' + rh.length + ' entries)</span>' + controls + '</div>' +
        '<div class="pmh-list">' + items + '</div></div>';
    })() +
  '</div>';
  Object.keys(previousDetailState).forEach(function(key) {
    var detail = overlay.querySelector('details[data-detail-key="' + key + '"]');
    if (detail) detail.open = previousDetailState[key];
  });
  enhancePositionModalDetails(overlay);
}

// ─── 13. Drawdown Chart ───────────────────────────────────────────────────
function updateDrawdownChart() {
  var canvas = document.getElementById('ddChart');
  if (!canvas || typeof Chart === 'undefined') return;
  var filtered = getChartNavHistory();
  if (filtered.length < 2 && navHistory.length >= 2) {
    filtered = downsampleNavHistory(navHistory.slice(-MAX_CHART_POINTS));
  }
  if (filtered.length < 2) return;
  var labels = filtered.map(function(h) { return formatChartTimeLabel(h.ts); });
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
    schedulePerformanceChartResize();
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
  schedulePerformanceChartResize();
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
    var shortSummary = fullSummary;
    var hasExpandable = detailText.length > 0;
    var expandContent = escapeHtml(detailText);
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
    // Thesis verification events get a distinct badge colour
    if (item.action === 'thesis_challenged') {
      roleColor = '#e8a000';  // amber — reasoning flagged
    } else if (item.action === 'thesis_revised') {
      roleColor = '#00d68f';  // green — accepted after revision
    } else if (item.action === 'evidence_review_required' || item.action === 'evidence_review_blocked') {
      roleColor = '#e84040';
    }
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
    var dailyMove = getPodDailyMove(id);
    return [
      id.toUpperCase(),
      getCurrentPodNav(id).toFixed(2),
      dailyMove.pnl.toFixed(2),
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
  var rows = getFilteredNavHistory().map(function(h) {
    var timeLabel = h.ts ? new Date(h.ts).toISOString() : h.t;
    var row = [timeLabel, h.firmNav.toFixed(2), ((h.drawdown || 0) * 100).toFixed(1) + '%'];
    podIds.forEach(function(id) { row.push(((h.pods && h.pods[id]) || 0).toFixed(2)); });
    return row;
  });
  downloadCsv('nav_history_' + new Date().toISOString().slice(0,10) + '.csv', headers, rows);
}

// ─── 16b. Closed Trades ─────────────────────────────────────────────────────
var _ctLastFetch = 0;
var _ctData = [];

function fetchClosedTrades(force) {
  var now = Date.now();
  if (!force && now - _ctLastFetch < 15000) return;
  _ctLastFetch = now;
  var controller = new AbortController();
  var timeout = setTimeout(function() { controller.abort(); }, 4000);
  fetch('/api/trades/closed', { signal: controller.signal })
    .then(function(r) { clearTimeout(timeout); if (!r.ok) throw new Error(r.statusText); return r.json(); })
    .then(function(data) {
      _ctData = Array.isArray(data) ? data : (data && (data.value || data.closed_positions)) || [];
      renderClosedTrades();
      renderOutcomeStats();
      updatePerfTable();
      updateAttribution();
    })
    .catch(function() { clearTimeout(timeout); });
}

function renderClosedTrades() {
  var tbody = document.getElementById('ct-table');
  var badge = document.getElementById('ct-badge');
  if (!tbody) return;
  if (badge) badge.textContent = _ctData.length + ' trade' + (_ctData.length !== 1 ? 's' : '');
  if (_ctData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty"><div class="empty-txt">No closed trades yet</div></td></tr>';
    return;
  }
  var totalPnl = 0;
  tbody.innerHTML = _ctData.slice(0, 30).map(function(t) {
    var pnl = t.realized_pnl || 0;
    totalPnl += pnl;
    var pc = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '';
    var pnlBase = tradeEntryNotional(t);
    var thesis = t.entry_reasoning || '';
    var entryDate = displayDateOnly(t.entry_date || t.entry_time);
    var exitDate = displayDateOnly(t.exit_date || t.exit_time);
    return '<tr>' +
      '<td class="pod-name">' + escapeHtml(t.pod_id || '').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(t.symbol || '') + '</td>' +
      '<td class="r">$' + (t.entry_price || 0).toFixed(2) + '</td>' +
      '<td class="r">$' + (t.exit_price || 0).toFixed(2) + '</td>' +
      '<td class="r">' + (t.qty || 0) + '</td>' +
      '<td class="r ct-pnl ' + pc + '">' + formatPnlWithPct(pnl, pnlBase, { pctDecimals: 2 }) + '</td>' +
      '<td class="r">' + (t.holding_days != null ? t.holding_days : '—') + '</td>' +
      '<td>' + escapeHtml(entryDate) + '</td>' +
      '<td>' + escapeHtml(exitDate) + '</td>' +
      '<td class="ct-thesis" title="' + escapeHtml(t.entry_reasoning || '') + '">' + escapeHtml(thesis) + '</td>' +
      '</tr>';
  }).join('');
}

// ─── 17. Chart Timeframe Toggle ────────────────────────────────────────────
function setChartPeriod(period) {
  chartPeriod = period || 'all';
  chartTimeframeMinutes = 0;
  document.querySelectorAll('.tf-btn[data-period]').forEach(function(b) {
    b.classList.toggle('active', b.dataset.period === chartPeriod);
  });
  refreshPerformanceCharts();
}

function setFirmNavVisible(visible) {
  showFirmNav = !!visible;
  var checkbox = document.getElementById('firm-nav-toggle');
  if (checkbox) checkbox.checked = showFirmNav;
  updateNavChart();
  syncModalNavChart();
  schedulePerformanceChartResize();
}

function setSpBenchmarkVisible(visible) {
  showSpBenchmark = !!visible;
  var checkbox = document.getElementById('sp-benchmark-toggle');
  if (checkbox) checkbox.checked = showSpBenchmark;
  updateNavChart();
  syncModalNavChart();
  schedulePerformanceChartResize();
}

function syncModalNavChart() {
  if (_modalNavChart && navChart) {
    _modalNavChart.data.labels = navChart.data.labels.slice();
    _modalNavChart.data.datasets = navChart.data.datasets.map(function(ds) {
      return Object.assign({}, ds, { data: ds.data.slice() });
    });
    _modalNavChart.update('none');
    resizeChartInstance(_modalNavChart);
  }
}

function setChartTimeframe(minutes) {
  var mins = Number(minutes || 0);
  if (mins >= 1440 && mins < 7 * 1440) return setChartPeriod('24h');
  if (mins >= 7 * 1440 && mins < 30 * 1440) return setChartPeriod('7d');
  if (mins >= 30 * 1440 && mins < 90 * 1440) return setChartPeriod('30d');
  return setChartPeriod('all');
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
    { lbl: 'Daily P&L', val: formatPnlWithPct(pnl, nav, { pctDecimals: 2 }) },
    { lbl: 'Cum. P&L', val: formatPnlWithPct(cpnl, sc, { pctDecimals: 2 }) },
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
      var notional = positionCurrentNotional(p);
      var entryNotional = positionEntryNotional(p);
      var entryDate = escapeHtml(p.entry_date || '—');
      var podEsc = escapeHtml(podId);
      var symEsc = escapeHtml(p.symbol || '');
      var thesis = p.entry_thesis ? escapeHtml(p.entry_thesis) : '';
      var symTitle = thesis ? 'Entry thesis: ' + thesis : 'No entry thesis recorded';
      return '<tr class="holdings-row" onclick="showPositionDetail(\'' + podEsc + '\',\'' + symEsc + '\')" title="Click for full detail" style="cursor:pointer">' +
        '<td style="font-weight:600" title="' + symTitle + '">' + tickerDisplay(p.symbol || '') + (thesis ? ' <span style="color:var(--text-dim);font-size:9px">✦</span>' : '') + '</td>' +
        '<td class="r">' + (p.qty || 0).toFixed(4) + '</td>' +
        '<td class="r">$' + entry.toFixed(2) + '</td>' +
        '<td class="r">$' + (p.current_price || entry).toFixed(2) + '</td>' +
        '<td class="r ' + pc + '">' + formatPnlWithPct(pnl, entryNotional, { pct: p.pnl_pct, pctDecimals: 2 }) + '</td>' +
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

function fetchCorrelationAndRender() {
  fetch('/api/correlation?limit=100').then(function(r) { return r.json(); }).then(function(data) {
    if (data && data.ids && data.ids.length >= 2 && data.matrix) {
      renderCorrelationFromApi(data);
      var banner = document.getElementById('risk-banner');
      if (data.high_correlation_pairs && data.high_correlation_pairs.length && banner) {
        var extra = 'High correlation: ' + data.high_correlation_pairs.map(function(p) {
          return p.a + '/' + p.b + ' r=' + p.r;
        }).join('; ');
        banner.className = 'risk-banner warning';
        banner.textContent = extra;
      }
    } else {
      renderCorrelationHeatmap();
    }
  }).catch(function() { renderCorrelationHeatmap(); });
}

function renderCorrelationFromApi(data) {
  var container = document.getElementById('correlation-heatmap');
  if (!container) return;
  var ids = data.ids;
  var mx = data.matrix;
  var html = '<table class="corr-table"><thead><tr><th></th>';
  ids.forEach(function(id) { html += '<th>' + id.toUpperCase() + '</th>'; });
  html += '</tr></thead><tbody>';
  ids.forEach(function(a) {
    html += '<tr><td class="corr-label">' + a.toUpperCase() + '</td>';
    ids.forEach(function(b) {
      var v = (mx[a] && mx[a][b] != null) ? mx[a][b] : 0;
      html += '<td class="corr-cell" style="background:' + corrColor(v) + '">' + Number(v).toFixed(2) + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
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
    var nav = getCurrentPodNav(id);
    var sc = getPodStartingCapital(id, ids);
    var move = getPodDailyMove(id);
    var pnl = move.pnl;
    var realized = getPodRealizedToday(id);
    var openPnl = getPodOpenPnl(id);
    firmPnl += pnl;
    return {
      id: id,
      pnl: pnl,
      ret: move.pct,
      trades: getPodTradeCount(id),
      nav: nav,
      base: move.base || sc,
      realized: realized,
      openPnl: openPnl,
    };
  });
  var maxAbsPnl = Math.max.apply(null, podStats.map(function(p) { return Math.abs(p.pnl); })) || 1;

  var html = '<div class="attr-section-title">Today by Pod</div><div class="attr-bars">';
  podStats.forEach(function(p) {
    var pct = firmPnl !== 0 ? (p.pnl / Math.abs(firmPnl) * 100) : 0;
    var barW = Math.abs(p.pnl) / maxAbsPnl * 100;
    var col = p.pnl >= 0 ? '#00d68f' : '#e84040';
    html += '<div class="attr-row">' +
      '<span class="attr-pod">' + p.id.toUpperCase() + '</span>' +
      '<div class="attr-bar-wrap"><div class="attr-bar" style="width:' + barW.toFixed(0) + '%;background:' + col + '"></div></div>' +
      '<span class="attr-val" style="color:' + col + '">' + formatPnlWithPct(p.pnl, p.base || p.nav || 0, { pct: p.ret, pctDecimals: 1 }) + '</span>' +
      '<span class="attr-pct">' + (pct >= 0 ? '+' : '') + pct.toFixed(0) + '%</span>' +
      '<span class="attr-stat">realized ' + formatPnlWithPct(p.realized.pnl, p.realized.base, { pctDecimals: 1 }) + ' - open ' + formatPnlWithPct(p.openPnl.pnl, p.openPnl.base, { pctDecimals: 1 }) + '</span>' +
      '</div>';
  });
  html += '</div>';

  var contributors = buildPnlContributors(ids).slice(0, 8);
  html += '<div class="attr-section-title attr-contrib-title">Top P&amp;L Contributors</div>';
  if (contributors.length === 0) {
    html += '<div class="empty"><div class="empty-txt">No material contributors yet</div></div>';
  } else {
    html += '<div class="tbl-wrap attr-contrib-wrap"><table class="dtbl attr-contrib-table">' +
      '<thead><tr><th>Symbol</th><th>Pod</th><th>Type</th><th class="r">P&amp;L</th></tr></thead><tbody>';
    contributors.forEach(function(row) {
      var cls = row.pnl >= 0 ? 'pos' : 'neg';
      html += '<tr>' +
        '<td class="pod-name">' + escapeHtml(row.symbol || '-') + '</td>' +
        '<td>' + escapeHtml(String(row.pod || '').toUpperCase()) + '</td>' +
        '<td>' + escapeHtml(row.type) + '</td>' +
        '<td class="r ' + cls + '">' + formatPnlWithPct(row.pnl, row.base, { pctDecimals: 2 }) + '</td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
  }
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
            var thesis = p.entry_thesis || '—';
            return '<tr><td><strong>' + tickerDisplay(p.symbol || '') + '</strong></td>' +
              '<td class="r">' + (p.qty || 0).toFixed(3) + '</td>' +
              '<td class="r">$' + entry.toFixed(2) + '</td>' +
              '<td class="r">$' + (p.current_price || entry).toFixed(2) + '</td>' +
              '<td class="r ' + pc + '">' + formatPnlWithPct(pnl, positionEntryNotional(p), { pct: p.pnl_pct, pctDecimals: 2 }) + '</td>' +
              '<td class="ct-thesis-cell" title="' + escapeHtml(thesis) + '">' + escapeHtml(thesis) + '</td></tr>';
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

function buildClosedOutcomeStatsByPod() {
  var grouped = {};
  (_ctData || []).forEach(function(t) {
    var pid = String(t.pod_id || t._pod || 'unknown').toLowerCase();
    if (!grouped[pid]) grouped[pid] = { trades: [], total_pnl: 0, total_notional: 0, wins: 0, winners: [], losers: [], winner_notional: 0, loser_notional: 0 };
    var pnl = Number(t.realized_pnl || 0);
    var notional = tradeEntryNotional(t);
    grouped[pid].trades.push(t);
    grouped[pid].total_pnl += pnl;
    grouped[pid].total_notional += notional;
    if (pnl > 0) {
      grouped[pid].wins += 1;
      grouped[pid].winners.push(pnl);
      grouped[pid].winner_notional += notional;
    } else if (pnl < 0) {
      grouped[pid].losers.push(pnl);
      grouped[pid].loser_notional += notional;
    }
  });

  var stats = {};
  Object.keys(grouped).forEach(function(pid) {
    var g = grouped[pid];
    var n = g.trades.length || 0;
    var winTotal = g.winners.reduce(function(sum, value) { return sum + value; }, 0);
    var lossTotal = g.losers.reduce(function(sum, value) { return sum + value; }, 0);
    stats[pid] = {
      total_trades: n,
      win_rate: n > 0 ? g.wins / n : 0,
      avg_pnl: n > 0 ? g.total_pnl / n : 0,
      total_pnl: g.total_pnl,
      avg_notional: n > 0 ? g.total_notional / n : 0,
      total_notional: g.total_notional,
      avg_winner_notional: g.winners.length > 0 ? g.winner_notional / g.winners.length : 0,
      avg_loser_notional: g.losers.length > 0 ? g.loser_notional / g.losers.length : 0,
      avg_winner: g.winners.length > 0 ? winTotal / g.winners.length : 0,
      avg_loser: g.losers.length > 0 ? lossTotal / g.losers.length : 0
    };
  });
  return stats;
}

function renderOutcomeStats() {
  var container = document.getElementById('outcome-grid');
  var badge = document.getElementById('outcomes-total-badge');
  if (!container) return;

  var apiStats = buildClosedOutcomeStatsByPod();
  var statsByPod = Object.keys(apiStats).length > 0 ? apiStats : Object.keys(pods).reduce(function(acc, pid) {
    acc[pid] = pods[pid].trade_outcome_stats || {};
    return acc;
  }, {});
  var podIds = Object.keys(statsByPod).filter(function(pid) {
    var s = statsByPod[pid] || {};
    return s.total_trades > 0;
  });

  var totalTrades = podIds.reduce(function(sum, pid) {
    return sum + ((statsByPod[pid] || {}).total_trades || 0);
  }, 0);
  if (badge) {
    badge.textContent = totalTrades + ' closed trade' + (totalTrades !== 1 ? 's' : '');
    badge.title = 'Closed-trade stats exclude open/unrealized P&L. Use NAV P&L to reconcile with Pod Returns.';
  }

  if (podIds.length === 0) {
    container.innerHTML = '<div class="outcome-pod-card"><div class="empty-txt">No closed trades yet</div></div>';
    return;
  }

  container.innerHTML = podIds.map(function(pid) {
    var s = statsByPod[pid] || {};
    var pod = pods[pid] || {};
    var startCap = getPodStartCap(pod);
    var navPnl = startCap > 0 ? getPodNav(pod) - startCap : null;
    var wrCls = s.win_rate >= 0.5 ? 'pos' : 'neg';
    var avgCls = s.avg_pnl >= 0 ? 'pos' : 'neg';
    var totCls = s.total_pnl >= 0 ? 'pos' : 'neg';
    var navCls = navPnl == null ? '' : navPnl >= 0 ? 'pos' : 'neg';

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
        stat('Avg P&amp;L', formatPnlWithPct(s.avg_pnl || 0, s.avg_notional || 0, { pctDecimals: 2 }), avgCls) +
        stat('Closed P&amp;L', formatPnlWithPct(s.total_pnl || 0, s.total_notional || 0, { pctDecimals: 2 }), totCls) +
        stat('NAV P&amp;L', navPnl == null ? '-' : formatPnlWithPct(navPnl, startCap, { pctDecimals: 2 }), navCls) +
        stat('Avg Winner', formatPnlWithPct(s.avg_winner || 0, s.avg_winner_notional || 0, { pctDecimals: 2 }), 'pos') +
        stat('Avg Loser', formatPnlWithPct(s.avg_loser || 0, s.avg_loser_notional || 0, { pctDecimals: 2 }), 'neg') +
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

function loadReportCorpus() {
  var container = document.getElementById('report-corpus-list');
  if (!container) return;
  container.innerHTML = '<div class="empty"><div class="empty-txt">Loading report corpus...</div></div>';
  fetchJsonWithTimeout('/api/reports/corpus?limit=80', {}, 6000)
    .then(function(data) {
      reportCorpus = data || {};
      var reports = reportCorpus.reports || [];
      if (!reports.length) {
        container.innerHTML = '<div class="empty"><div class="empty-txt">No report corpus entries yet</div><div class="empty-hint">PM, specialist, IC, thesis, hindsight, and meta reports will appear here.</div></div>';
        return;
      }
      container.innerHTML = '<div class="tbl-wrap tbl-wrap-scroll"><table class="dtbl"><thead><tr>' +
        '<th>Time</th><th>Type</th><th>Pod</th><th>Symbol</th><th>Title</th><th>Catalysts</th><th>Flags</th>' +
        '</tr></thead><tbody>' +
        reports.map(function(r) {
          var cats = Array.isArray(r.related_catalyst_ids) ? r.related_catalyst_ids : [];
          var flags = Array.isArray(r.quality_flags) ? r.quality_flags : [];
          return '<tr>' +
            '<td class="mono">' + escapeHtml(formatRelativeTime(r.created_at)) + '</td>' +
            '<td class="mono">' + escapeHtml(r.report_type || '') + '</td>' +
            '<td class="mono">' + escapeHtml(r.pod_id || '-') + '</td>' +
            '<td class="mono">' + escapeHtml(r.symbol || '-') + '</td>' +
            '<td><div class="rf-item-title">' + escapeHtml(r.title || '') + '</div><div class="rf-item-meta">' + escapeHtml(truncate(r.summary || '', 220)) + '</div></td>' +
            '<td><div class="rf-tags">' + researchTags(cats.slice(0, 4), 'factor') + '</div></td>' +
            '<td><div class="rf-tags">' + researchTags(flags.slice(0, 4), 'held') + '</div></td>' +
          '</tr>';
        }).join('') +
        '</tbody></table></div>';
    })
    .catch(function(err) {
      container.innerHTML = '<div class="empty"><div class="empty-txt">Failed to load report corpus</div><div class="empty-hint">' + escapeHtml(err && err.message ? err.message : '') + '</div></div>';
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
    var pnlBase = tradeEntryNotional(p);
    var entryP = p.entry_price || 0;
    var exitP = p.exit_price || 0;
    var retPct = entryP > 0 ? ((exitP - entryP) / entryP * 100) : 0;
    if (p.side === 'short') retPct = -retPct;
    var retCls = retPct >= 0 ? 'pos' : 'neg';
    var entryRaw = p.entry_time || p.entry_date || '';
    var exitRaw = p.exit_time || p.exit_date || '';
    var entryDate = displayDateOnly(entryRaw);
    var exitDate = displayDateOnly(exitRaw);
    var holdDays = '—';
    if (entryRaw && exitRaw) {
      try {
        holdDays = Math.round((new Date(exitRaw) - new Date(entryRaw)) / 86400000) + 'd';
      } catch(e) {}
    }
    return '<tr class="holdings-row" style="cursor:pointer" onclick="showClosedPositionDetail(' + idx + ')" title="Click for details">' +
      '<td class="pod-name">' + escapeHtml(p.pod_id || '').toUpperCase() + '</td>' +
      '<td style="font-weight:600">' + tickerDisplay(p.symbol || '') + '</td>' +
      '<td class="r">$' + entryP.toFixed(2) + '</td>' +
      '<td class="r">$' + exitP.toFixed(2) + '</td>' +
      '<td class="r">' + (p.qty || 0) + '</td>' +
      '<td class="r ' + pc + '">' + formatPnlWithPct(pnl, pnlBase, { pct: retPct, pctDecimals: 2 }) + '</td>' +
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
  var pnlBase = tradeEntryNotional(p);
  var entryP = p.entry_price || 0;
  var exitP = p.exit_price || 0;
  var retPct = entryP > 0 ? ((exitP - entryP) / entryP * 100) : 0;
  if (p.side === 'short') retPct = -retPct;
  var retCls = retPct >= 0 ? 'pos' : 'neg';
  var entryRaw = p.entry_time || p.entry_date || '';
  var exitRaw = p.exit_time || p.exit_date || '';
  var entryDate = displayDateOnly(entryRaw);
  var exitDate = displayDateOnly(exitRaw);
  var holdDays = '—';
  if (entryRaw && exitRaw) {
    try { holdDays = Math.round((new Date(exitRaw) - new Date(entryRaw)) / 86400000); } catch(e) {}
  }

  var entryThesis = cleanThesis(p.entry_reasoning || p.entry_thesis || '', p.symbol);
  var exitThesis = cleanThesis(p.exit_reasoning || '', p.symbol);
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
        '<div class="pos-hdr-pnl ' + pnlCls + '">' + formatPnlWithPct(pnl, pnlBase, { pct: retPct, pctDecimals: 2 }) + ' realized</div>' +
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
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Realized P&L</div><div class="pos-cell-val ' + pnlCls + '">' + formatPnlWithPct(pnl, pnlBase, { pct: retPct, pctDecimals: 2 }) + '</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Total Return</div><div class="pos-cell-val ' + retCls + '">' + (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Conviction</div><div class="pos-cell-val">' + (((p.conviction || 0) * 100).toFixed(0)) + '%</div></div>' +
        '<div class="pos-cell" style="flex:1;min-width:120px"><div class="pos-cell-lbl">Side</div><div class="pos-cell-val">' + (p.side || 'long').toUpperCase() + '</div></div>' +
      '</div>' +
    '</div>' +
    (entryThesis ? '<div class="pos-section"><div class="pos-section-title">Entry Thesis</div><div class="pos-thesis">' + escapeHtml(entryThesis) + '</div></div>' : '') +
    (exitThesis ? '<div class="pos-section"><div class="pos-section-title">Exit Thesis</div><div class="pos-thesis" style="border-left:2px solid var(--accent-red,#e8384f);padding-left:8px">' + escapeHtml(exitThesis) + '</div></div>' : '') +
    (exitWhen ? '<div class="pos-section"><div class="pos-section-title">Exit Condition</div><div class="pos-thesis closed-exit-when">' + escapeHtml(exitWhen) + '</div></div>' : '') +
    (p.strategy_tag ? '<div class="pos-section"><div class="pos-section-title">Strategy</div><div style="font-size:11px;color:var(--text-secondary);padding:6px 0">' + escapeHtml(p.strategy_tag) + '</div></div>' : '') +
  '</div>';
}

// ─── 22. Init ──────────────────────────────────────────────────────────────
initResearchHistoryChart();
updateGovHub();
loadSavedReports();
loadReportCorpus();
loadClosedPositions();
fetchResearchFeedAudit(true).then(function() {
  renderNewsFeed();
  renderResearchFeedAudit(false);
  renderForesightLedger(false);
}).catch(function() {
  renderNewsFeed();
});
setInterval(function() {
  fetchResearchFeedAudit(false).then(function() {
    renderNewsFeed();
  }).catch(function() {});
  fetchForesightLedger(false).then(function() {
    renderForesightLedger(false);
  }).catch(function() {});
}, RESEARCH_FEED_REFRESH_MS);
