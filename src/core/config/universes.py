"""Seed universes per pod — the LLM can trade ANY symbol Alpaca supports,
but these lists define what the researcher fetches bars for each cycle
so the PM has price context.

Edit these lists freely; no agent code changes needed.
"""

EQUITIES_SEED: list[str] = [
    # --- Broad Market ETFs ---
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP", "MDY",
    # --- Sector ETFs ---
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLY", "XLC", "XLB", "XLRE",
    # --- Thematic / Factor ETFs ---
    "ARKK", "SOXX", "SMH", "TAN", "LIT", "HACK", "IBB", "XBI",
    "KWEB", "CQQQ", "ICLN", "QCLN", "BOTZ", "ROBO",
    # --- International ETFs ---
    "EFA", "EEM", "VGK", "EWJ", "FXI", "EWZ", "INDA", "EWT", "EWY", "VWO",
    "IEMG", "MCHI",
    # --- Bond / Fixed Income ETFs ---
    "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND", "TIP", "EMB", "JNK",
    # --- Top US Stocks by Market Cap ---
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK.B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH",
    "HD", "XOM", "CVX", "LLY", "ABBV",
    "COST", "MRK", "PEP", "KO", "AVGO",
    "TMO", "ADBE", "CRM", "ACN", "MCD",
    "CSCO", "NKE", "NFLX", "AMD", "INTC",
    "QCOM", "TXN", "BA", "CAT", "DE",
    "GE", "UPS", "RTX", "LMT", "GS",
    "MS", "C", "BAC", "WFC", "SCHW",
    "PLTR", "SNOW", "UBER", "ABNB", "SQ",
    "SHOP", "COIN", "MSTR", "RIVN", "LCID",
]

FX_SEED: list[str] = [
    # --- Currency ETFs ---
    "FXE", "FXY", "FXB", "FXA", "FXC", "FXF",
    "UUP", "UDN", "CEW", "USDU",
    # --- Country / Regional Market ETFs ---
    "EWJ", "EWG", "EWU", "EWQ", "EWP", "EWI", "EWN", "EWL",
    "EWA", "EWC", "EWZ", "FXI", "INDA", "EWT", "EWY",
    "EWS", "EWM", "EWW", "EWH", "THD", "VNM", "EIDO", "EPHE",
    # --- Rate-Sensitive / Bond ETFs ---
    "TLT", "IEF", "SHY", "BWX", "IGOV", "LEMB", "EMLC",
    # --- EM / Frontier ETFs ---
    "EEM", "VWO", "IEMG", "FM",
]

CRYPTO_SEED: list[str] = [
    # --- Majors ---
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", "XRP/USD",
    "DOT/USD", "LTC/USD", "AVAX/USD",
    # --- DeFi ---
    "AAVE/USD", "UNI/USD", "SUSHI/USD", "CRV/USD",
    "LDO/USD", "LINK/USD", "GRT/USD",
    # --- Memes / Culture ---
    "DOGE/USD", "SHIB/USD", "PEPE/USD", "BONK/USD",
    "WIF/USD", "TRUMP/USD",
    # --- Infrastructure ---
    "FIL/USD", "RENDER/USD", "ARB/USD", "ONDO/USD", "POL/USD",
    # --- Other ---
    "BAT/USD", "BCH/USD", "HYPE/USD", "PAXG/USD",
    "SKY/USD", "XTZ/USD", "YFI/USD",
]

COMMODITIES_SEED: list[str] = [
    # --- Gold ---
    "GLD", "IAU", "GDX", "GDXJ", "SGOL",
    # --- Silver ---
    "SLV", "PSLV", "SIL",
    # --- Oil & Gas ---
    "USO", "XLE", "XOP", "OIH", "UNG", "AMLP",
    # --- Agriculture ---
    "DBA", "CORN", "WEAT", "SOYB", "MOO", "COW",
    # --- Broad Commodities ---
    "GSG", "PDBC", "COM", "DJP", "COMT",
    # --- Copper & Industrial Metals ---
    "CPER", "COPX", "DBB", "PICK",
    # --- Uranium & Nuclear ---
    "URA", "URNM",
    # --- Lithium & Battery Metals ---
    "LIT", "BATT",
    # --- Mining / Metal Equities ---
    "XME", "REMX",
    "FCX", "NEM", "GOLD", "BHP", "RIO", "AA", "CLF", "VALE", "MOS", "NTR",
]

POD_UNIVERSES: dict[str, list[str]] = {
    "equities": EQUITIES_SEED,
    "fx": FX_SEED,
    "crypto": CRYPTO_SEED,
    "commodities": COMMODITIES_SEED,
}
