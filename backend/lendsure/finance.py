"""
LendSure Financial Intelligence Center — backend API.
Seeded realistic Indian financial data + live-capable endpoints.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query

router = APIRouter(prefix="/api/finance", tags=["Financial Intelligence"])

_DB_FN: Any = None
_SESSION_FN: Any = None

# ── DDL ──────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS fi_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content TEXT DEFAULT '',
    published_at TEXT NOT NULL,
    image_url TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'economy',
    country TEXT NOT NULL DEFAULT 'IN',
    author TEXT DEFAULT '',
    symbols TEXT DEFAULT '[]',
    ai_summary TEXT DEFAULT '',
    lending_impact TEXT DEFAULT '',
    impact_level TEXT DEFAULT 'low',
    market_impact TEXT DEFAULT 'low',
    ai_confidence INTEGER DEFAULT 70,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fi_news_cat ON fi_news (category);
CREATE INDEX IF NOT EXISTS idx_fi_news_pub ON fi_news (published_at);

CREATE TABLE IF NOT EXISTS fi_market_assets (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'index',
    sector TEXT DEFAULT '',
    region TEXT DEFAULT 'IN',
    currency TEXT DEFAULT 'INR',
    current_price REAL DEFAULT 0,
    prev_close REAL DEFAULT 0,
    day_high REAL DEFAULT 0,
    day_low REAL DEFAULT 0,
    open_price REAL DEFAULT 0,
    volume INTEGER DEFAULT 0,
    change_abs REAL DEFAULT 0,
    change_pct REAL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fi_market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    volume INTEGER DEFAULT 0,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fi_snap_sym ON fi_market_snapshots (symbol, ts);

CREATE TABLE IF NOT EXISTS fi_economic_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator TEXT NOT NULL,
    value REAL,
    previous REAL,
    unit TEXT DEFAULT '',
    source TEXT DEFAULT '',
    last_updated TEXT NOT NULL,
    UNIQUE (indicator)
);

CREATE TABLE IF NOT EXISTS fi_watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT NOT NULL,
    name TEXT DEFAULT 'My Watchlist',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fi_watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS fi_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    source TEXT DEFAULT '',
    category TEXT DEFAULT 'market',
    affected_area TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fi_alerts_tok ON fi_alerts (session_token, is_read);
"""


def configure(db_fn, session_fn):
    global _DB_FN, _SESSION_FN
    _DB_FN = db_fn
    _SESSION_FN = session_fn


def _conn() -> sqlite3.Connection:
    return _DB_FN()


def _session(token: Optional[str]) -> Optional[dict]:
    return _SESSION_FN(token) if _SESSION_FN and token else None


# ── Seeding ──────────────────────────────────────────────────────────────────

def _seed_if_empty(conn: sqlite3.Connection):
    """Seed realistic Indian financial data on first run."""
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) c FROM fi_market_assets").fetchone()[0] > 0:
        return

    now = datetime.utcnow().isoformat()

    # ── Market assets ────────────────────────────────────────────────────────
    assets = [
        ("^NSEI", "NIFTY 50", "index", "Broad Market", "IN", 24850, 24780),
        ("^BSESN", "SENSEX", "index", "Broad Market", "IN", 81250, 81100),
        ("^NSEBANK", "NIFTY Bank", "index", "Banking", "IN", 51200, 51050),
        ("^CNXIT", "NIFTY IT", "index", "IT", "IN", 38900, 38700),
        ("^GSPC", "S&P 500", "index", "Broad Market", "US", 5650, 5620),
        ("^IXIC", "NASDAQ", "index", "Technology", "US", 18100, 18000),
        ("^DJI", "DOW JONES", "index", "Industrial", "US", 41300, 41150),
        ("^FTSE", "FTSE 100", "index", "Broad Market", "GB", 8400, 8370),
        ("^GDAXI", "DAX", "index", "Broad Market", "DE", 18900, 18820),
        ("^N225", "NIKKEI 225", "index", "Broad Market", "JP", 39500, 39350),
        ("USDINR=X", "USD/INR", "currency", "FX", "IN", 83.45, 83.28),
        ("EURINR=X", "EUR/INR", "currency", "FX", "IN", 90.80, 90.55),
        ("GBPINR=X", "GBP/INR", "currency", "FX", "IN", 105.20, 104.90),
        ("JPYINR=X", "JPY/INR", "currency", "FX", "IN", 0.558, 0.556),
        ("GC=F", "Gold", "commodity", "Precious Metals", "US", 2680, 2665),
        ("SI=F", "Silver", "commodity", "Precious Metals", "US", 31.50, 31.20),
        ("CL=F", "Crude Oil", "commodity", "Energy", "US", 78.50, 77.80),
        ("BTC-USD", "Bitcoin", "crypto", "Crypto", "US", 98500, 97200),
        ("ETH-USD", "Ethereum", "crypto", "Crypto", "US", 3850, 3790),
    ]
    for sym, name, atype, sector, region, price, prev in assets:
        chg = price - prev
        pct = (chg / prev * 100) if prev else 0
        day_h = price * (1 + abs(pct) / 200)
        day_l = price * (1 - abs(pct) / 200)
        vol = random.randint(500000, 50000000) if atype == "index" else random.randint(10000, 5000000)
        cur.execute(
            """INSERT OR REPLACE INTO fi_market_assets
               (symbol,name,asset_type,sector,region,currency,current_price,prev_close,
                day_high,day_low,open_price,volume,change_abs,change_pct,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sym, name, atype, sector, region, "INR" if region == "IN" else "USD",
             round(price, 2), round(prev, 2), round(day_h, 2), round(day_l, 2),
             round(prev + chg * 0.3, 2), vol, round(chg, 2), round(pct, 2), now),
        )

    # Generate historical snapshots for charts
    for sym, name, atype, sector, region, price, prev in assets:
        base = prev
        for d in range(90):
            ts = (datetime.utcnow() - timedelta(days=90 - d)).isoformat()
            noise = random.gauss(0, base * 0.008)
            p = round(base + noise + (price - prev) * d / 90, 2)
            cur.execute(
                "INSERT INTO fi_market_snapshots (symbol,price,volume,ts) VALUES (?,?,?,?)",
                (sym, p, random.randint(100000, 10000000), ts),
            )

    # ── Economic indicators ──────────────────────────────────────────────────
    indicators = [
        ("repo_rate", 6.50, 6.50, "%", "Reserve Bank of India"),
        ("reverse_repo_rate", 3.35, 3.35, "%", "Reserve Bank of India"),
        ("inflation_cpi", 5.08, 5.10, "%", "Ministry of Statistics"),
        ("inflation_wholesale", 0.26, 0.73, "%", "Ministry of Commerce"),
        ("gdp_growth", 6.80, 7.20, "%", "RBI / MOSPI"),
        ("unemployment", 3.20, 3.10, "%", "CMIE"),
        ("usd_inr", 83.45, 83.28, "INR", "RBI Reference Rate"),
        ("india_10y_yield", 7.12, 7.08, "%", "CCIL"),
        ("industrial_production", 3.40, 2.30, "%", "IIP Index"),
        ("credit_growth", 15.20, 14.80, "%", "RBI Weekly"),
        ("deposit_growth", 13.50, 13.20, "%", "RBI Weekly"),
        ("fpi_flows", 4850, 3200, "INR Cr", "NSDL"),
        ("fdi_inflows", 4500, 4800, "INR Cr", "DPIIT"),
        ("forex_reserves", 682, 679, "USD Bn", "RBI"),
        ("fiscal_deficit", 4.90, 5.10, "% of GDP", "Controller General"),
    ]
    for name, val, prev, unit, source in indicators:
        cur.execute(
            "INSERT OR REPLACE INTO fi_economic_indicators (indicator,value,previous,unit,source,last_updated) VALUES (?,?,?,?,?,?)",
            (name, val, prev, unit, source, now),
        )

    # ── News articles ────────────────────────────────────────────────────────
    news = [
        ("Reuters", "RBI holds repo rate steady at 6.5% amid global uncertainty", "The Reserve Bank of India maintained its benchmark repo rate at 6.50% in its latest monetary policy review, citing persistent inflation concerns and global economic headwinds. Governor Das noted that the stance remains withdrawal of accommodation.", "economy", "IN", "RBI keeps rates unchanged for eighth consecutive meeting. CPI inflation remains above the 4% target band."),
        ("Economic Times", "India GDP growth moderates to 6.8% in Q3 FY25", "India's GDP growth slowed to 6.8% year-on-year in the third quarter of FY25, down from 7.2% in Q2. The moderation was attributed to weaker manufacturing output and reduced government spending ahead of elections.", "economy", "IN", "Q3 GDP growth at 6.8%. Manufacturing and government capex weaker. Services sector remains resilient."),
        ("LiveMint", "SME credit demand surges 18% as small businesses expand operations", "Credit demand from small and medium enterprises grew 18% year-on-year in the latest quarter, driven by expansion in manufacturing and services sectors. NBFCs reported the highest growth in SME lending.", "credit", "IN", "SME credit demand up 18% YoY. NBFCs leading SME lending growth. Consumer credit steady."),
        ("Bloomberg", "Global crude oil prices rise 3% on OPEC+ production cuts", "Brent crude climbed above $82 per barrel after OPEC+ announced voluntary production cuts of 1.5 million barrels per day. The move is expected to increase input costs for Indian manufacturers.", "markets", "GLOBAL", "Oil prices up 3%. May increase input costs. Impact on inflation and borrowing costs possible."),
        ("Moneycontrol", "Indian banking sector NPAs fall to multi-year low of 3.2%", "Gross non-performing assets of Indian banks fell to 3.2% of total advances, the lowest level in over a decade. The improvement was driven by recoveries, write-offs, and stronger credit underwriting.", "banking", "IN", "Banking NPAs at multi-year low of 3.2%. Credit quality improving. Positive for lending environment."),
        ("Financial Express", "NBFC sector sees robust growth in retail lending", "Non-banking financial companies recorded 22% growth in retail loan disbursements, outpacing traditional banks. Home loans and MSME loans drove the growth, with digital-first NBFCs gaining market share.", "lending", "IN", "NBFC retail lending up 22%. Digital lenders gaining share. Competition increasing in retail segment."),
        ("Reuters", "US Federal Reserve signals potential rate cuts in 2025", "The Federal Reserve indicated it could begin cutting interest rates in 2025 if inflation continues to moderate. Markets rallied on the dovish signal, with the S&P 500 hitting new highs.", "economy", "US", "Fed signals possible rate cuts. Positive for global liquidity. May reduce capital outflow pressure on India."),
        ("Livemint", "Digital lending platforms report 40% rise in fraud attempts", "Digital lending platforms reported a 40% increase in fraud attempts in the last quarter, including synthetic identity fraud, document forgery, and income misrepresentation. Industry bodies are calling for stricter KYC norms.", "fintech", "IN", "Digital lending fraud attempts up 40%. Identity and document fraud rising. KYC norms may tighten."),
        ("Economic Times", "RBI introduces new framework for gold loan regulation", "The Reserve Bank of India announced a new regulatory framework for gold loans, requiring stricter collateral valuation norms and LTV ratio monitoring. The changes aim to reduce systemic risk in the gold loan segment.", "regulation", "IN", "New gold loan regulations announced. Stricter LTV monitoring. May affect gold-backed lending."),
        ("CNBC TV18", "Credit card defaults rise 15% amid consumer spending slowdown", "Credit card delinquencies rose 15% quarter-on-quarter as consumer spending showed signs of fatigue. Analysts flagged rising household debt-to-income ratios as a warning signal for unsecured lending.", "credit", "IN", "Credit card defaults up 15%. Consumer spending slowing. Household debt ratios rising."),
        ("Bloomberg", "Rupee falls to 83.80 against dollar on FII outflows", "The Indian rupee declined to 83.80 against the US dollar, pressured by continued foreign institutional investor outflows from Indian equity markets. The RBI intervened to prevent excessive volatility.", "markets", "IN", "Rupee weakening on FII outflows. RBI intervention ongoing. Import costs may rise."),
        ("Moneycontrol", "Housing market shows strong momentum with 12% sales growth", "Residential property sales grew 12% year-on-year across top cities, with affordable housing leading the demand. Home loan disbursements reached a five-year high, signaling strong housing credit growth.", "economy", "IN", "Housing sales up 12%. Home loan disbursements at 5-year high. Positive for housing finance segment."),
        ("Financial Express", "MSME sector contributes 30% to GDP, employability concerns persist", "The MSME sector's contribution to India's GDP reached 30%, but employability concerns persist with skill gaps in technology adoption. Government schemes are supporting digital transformation.", "economy", "IN", "MSME contributes 30% GDP. Skill gaps in tech adoption. Government supporting digital transformation."),
        ("Reuters", "Gold prices hit record high as central banks increase reserves", "Gold prices surged to a record $2,700 per ounce as central banks worldwide accelerated reserve diversification. India's forex reserves included higher gold allocation in recent quarters.", "markets", "GLOBAL", "Gold at record highs. Central bank buying. Positive for gold-backed lending collateral values."),
        ("LiveMint", "Fintech regulation: RBI proposes stricter norms for digital lending", "The RBI proposed stricter regulatory norms for digital lenders, including mandatory partnership with regulated entities, enhanced disclosure requirements, and standardized grievance redressal mechanisms.", "regulation", "IN", "Stricter fintech regulation proposed. May increase compliance costs. Could reshape digital lending landscape."),
        ("Economic Times", "Consumer confidence index rises to 8-month high", "The consumer confidence index reached an 8-month high of 104.5, driven by improved employment outlook and easing inflation expectations. Future expectations remained optimistic.", "economy", "IN", "Consumer confidence at 8-month high. Employment outlook improving. Positive for consumer lending."),
        ("CNBC TV18", "Corporate bond market sees record issuances in Q3", "Indian corporates raised a record ₹2.8 lakh crore through bond issuances in Q3 FY25, driven by infrastructure companies and NBFCs. Yields moderated on surplus liquidity.", "markets", "IN", "Record corporate bond issuances. Infrastructure and NBFC borrowing up. Liquidity comfortable."),
        ("Bloomberg", "Global trade tensions escalate with new tariff announcements", "Major economies announced new trade tariffs targeting technology and manufacturing sectors. The escalation could affect Indian IT exports and manufacturing supply chains in the medium term.", "economy", "GLOBAL", "Trade tensions escalating. Potential impact on Indian IT exports. Manufacturing supply chains at risk."),
        ("Moneycontrol", "Personal loan growth cools down to 14% as banks tighten norms", "Personal loan growth decelerated to 14% from 22% a year ago, as banks tightened credit assessment norms following RBI guidelines on unsecured lending risk weights.", "lending", "IN", "Personal loan growth cooling to 14%. Banks tightening norms. Regulatory impact visible."),
        ("Financial Express", "India's forex reserves surge to $682 billion, import cover improves", "India's foreign exchange reserves rose to $682 billion, providing 11 months of import cover. The strong reserve position provides a buffer against external volatility.", "economy", "IN", "Forex reserves at $682B. 11 months import cover. Strong external buffer."),
    ]
    for i, (source, title, desc, cat, country, summary) in enumerate(news):
        pub = (datetime.utcnow() - timedelta(hours=random.randint(1, 72))).isoformat()
        impact = random.choice(["low", "medium", "high"])
        mkt_impact = random.choice(["low", "medium", "high"])
        conf = random.randint(65, 92)
        lending_impact = ""
        if cat in ("economy", "credit", "lending"):
            lending_impact = "Moderate impact on lending environment. "
            if "rate" in title.lower() or "rbi" in title.lower():
                lending_impact += "Interest rate environment may affect borrowing costs."
            elif "credit" in title.lower():
                lending_impact += "Credit conditions could shift. Monitor portfolio risk."
            elif "inflation" in title.lower():
                lending_impact += "Inflation affects real borrowing costs and repayment capacity."
            else:
                lending_impact += "Economic conditions affect borrower repayment capacity."
        tags = []
        if "rbi" in title.lower():
            tags.append("rbi")
        if "rate" in title.lower():
            tags.append("interest-rates")
        if "inflation" in title.lower():
            tags.append("inflation")
        if cat == "banking":
            tags.append("banking")
        cur.execute(
            """INSERT INTO fi_news
               (source,source_url,title,description,content,published_at,image_url,
                category,country,author,symbols,ai_summary,lending_impact,
                impact_level,market_impact,ai_confidence,tags,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (source, f"https://{source.lower().replace(' ', '')}.com/article/{i}",
             title, desc, desc, pub, "", cat, country, source,
             json.dumps(tags), summary, lending_impact, impact, mkt_impact, conf,
             json.dumps(tags), now),
        )

    conn.commit()


def init_fi_db():
    conn = _conn()
    try:
        conn.executescript(DDL)
        _seed_if_empty(conn)
    finally:
        conn.close()
    start_live_refresh()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:].strip() or None


def _user_token(authorization: Optional[str]) -> str:
    t = _token(authorization)
    return t or "anonymous"


# ── Live data (background refresh; seeded data is always the fallback) ───────
# Markets: Yahoo Finance chart API (no key needed). News: NewsAPI.org when
# NEWS_API_KEY is set. A daemon thread refreshes every 15 min; request paths
# only ever read the DB, so a dead/slow provider can never slow the app.

import os as _os
import threading as _threading
import time as _time
import urllib.parse as _urlparse
import urllib.request as _urlreq

_YAHOO_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/126.0 Safari/537.36"}
_LIVE_TTL_S = 60
_live_lock = _threading.Lock()
_live_started = False
_live_status = {"markets": "seeded", "news": "seeded", "last_run": None}


def _http_json(url: str, headers: dict | None = None, timeout: int = 6):
    req = _urlreq.Request(url, headers=headers or {})
    with _urlreq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _fetch_yahoo_price(sym: str):
    """(price, prev_close, volume) or None. Retries across hosts on 429."""
    import urllib.error as _urlerror
    q = _urlparse.quote(sym, safe="")
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        for attempt in range(3):
            try:
                data = _http_json(
                    f"https://{host}/v8/finance/chart/{q}?interval=1d&range=5d",
                    _YAHOO_UA)
                meta = (data.get("chart", {}).get("result") or [{}])[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if not price or not prev:
                    closes = (((data.get("chart", {}).get("result") or [{}])[0]
                               .get("indicators", {}).get("quote") or [{}])[0]
                              .get("close") or [])
                    closes = [c for c in closes if c]
                    if len(closes) >= 2:
                        price, prev = closes[-1], closes[-2]
                if price and prev:
                    return round(float(price), 2), round(float(prev), 2), \
                        int(meta.get("regularMarketVolume") or 0)
                return None  # symbol unknown — don't hammer
            except _urlerror.HTTPError as e:
                last = e
                if e.code == 429:
                    _time.sleep(2 + attempt * 3)
                    continue
                break
            except Exception as e:
                last = e
                break
    return None


def _refresh_markets() -> int:
    """Pull live quotes for every tracked symbol. Returns # updated."""
    conn = _conn()
    try:
        syms = [r["symbol"] for r in
                conn.execute("SELECT symbol FROM fi_market_assets").fetchall()]
    finally:
        conn.close()
    updated = 0
    now = datetime.utcnow().isoformat()
    for i, sym in enumerate(syms):
        if i:
            _time.sleep(0.6)  # stay under Yahoo's rate limit
        got = _fetch_yahoo_price(sym)
        if not got:
            continue
        price, prev, vol = got
        try:
            chg = round(price - prev, 2)
            pct = round(chg / prev * 100, 4) if prev else 0.0
            conn = _conn()
            try:
                conn.execute(
                    "UPDATE fi_market_assets SET current_price=?, prev_close=?, "
                    "change_abs=?, change_pct=?, volume=?, updated_at=? WHERE symbol=?",
                    (price, prev, chg, pct, vol, now, sym))
                conn.execute(
                    "INSERT INTO fi_market_snapshots (symbol,price,volume,ts) VALUES (?,?,?,?)",
                    (sym, price, vol, now))
                conn.commit()
            finally:
                conn.close()
            updated += 1
        except Exception:
            continue
    with _live_lock:
        if updated:
            _live_status["markets"] = "live"
        _live_status["last_run"] = datetime.utcnow().isoformat()
    return updated


_NEWS_CAT_HINTS = [
    ("banking", ("bank", "npa", "rbi")),
    ("regulation", ("regulation", "sebi", "rbi", "framework", "norms")),
    ("credit", ("credit", "loan", "default", "delinquen", "emi")),
    ("lending", ("lending", "nbFc", "msme", "sme")),
    ("fintech", ("fintech", "upi", "digital", "startup")),
    ("economy", ("gdp", "inflation", "economy", "rbi", "rate", "growth")),
]


def _classify_live_news(title: str, desc: str) -> str:
    text = f"{title} {desc}".lower()
    for cat, hints in _NEWS_CAT_HINTS:
        if any(h.lower() in text for h in hints):
            return cat
    return "markets"


def _refresh_news() -> int:
    """Pull live headlines when a NewsAPI key is configured. Returns # added."""
    key = _os.environ.get("NEWS_API_KEY") or _os.environ.get("LENDSURE_NEWS_API_KEY") or ""
    if not key:
        return 0
    data = _http_json(
        "https://newsapi.org/v2/top-headlines?country=in&category=business&pageSize=30",
        {"X-Api-Key": key, **_YAHOO_UA})
    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI: {data.get('message', 'bad response')}")
    now = datetime.utcnow().isoformat()
    added = 0
    conn = _conn()
    try:
        for a in data.get("articles", []):
            title = (a.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            exists = conn.execute("SELECT 1 FROM fi_news WHERE title=? LIMIT 1",
                                  (title,)).fetchone()
            if exists:
                continue
            desc = (a.get("description") or "")[:500]
            src = (a.get("source") or {}).get("name", "NewsAPI")[:60]
            conn.execute(
                """INSERT INTO fi_news (source,source_url,title,description,content,
                   published_at,image_url,category,country,author,symbols,ai_summary,
                   lending_impact,impact_level,market_impact,ai_confidence,tags,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (src, a.get("url") or "", title, desc, desc,
                 a.get("publishedAt") or now, a.get("urlToImage") or "",
                 _classify_live_news(title, desc), "IN", src, "[]",
                 desc[:240], "", "medium", "medium", 60, "[]", now))
            added += 1
        conn.commit()
    finally:
        conn.close()
    with _live_lock:
        _live_status["news"] = "live"
        _live_status["last_run"] = datetime.utcnow().isoformat()
    return added


def _live_refresh_loop():
    _time.sleep(5)  # let boot finish
    while True:
        try:
            n = _refresh_markets()
            print(f"[live] markets refreshed: {n} symbols", flush=True)
        except Exception as e:
            print(f"[live] markets refresh failed ({e}); using seeded data", flush=True)
        try:
            n = _refresh_news()
            if n:
                print(f"[live] news added: {n} articles", flush=True)
        except Exception as e:
            print(f"[live] news refresh failed ({e}); using seeded data", flush=True)
        _time.sleep(_LIVE_TTL_S)


def start_live_refresh():
    global _live_started
    with _live_lock:
        if _live_started:
            return
        _live_started = True
    _threading.Thread(target=_live_refresh_loop, daemon=True).start()


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/overview")
def overview(authorization: Optional[str] = Header(default=None)):
    conn = _conn()
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()

        # Market status
        nifty = cur.execute("SELECT * FROM fi_market_assets WHERE symbol='^NSEI'").fetchone()
        sensex = cur.execute("SELECT * FROM fi_market_assets WHERE symbol='^BSESN'").fetchone()
        usdinr = cur.execute("SELECT * FROM fi_market_assets WHERE symbol='USDINR=X'").fetchone()
        gold = cur.execute("SELECT * FROM fi_market_assets WHERE symbol='GC=F'").fetchone()
        btc = cur.execute("SELECT * FROM fi_market_assets WHERE symbol='BTC-USD'").fetchone()

        market_assets = []
        for a in [nifty, sensex, usdinr, gold, btc]:
            if a:
                market_assets.append({
                    "symbol": a["symbol"], "name": a["name"],
                    "price": a["current_price"], "change_pct": a["change_pct"],
                    "change_abs": a["change_abs"], "updated_at": a["updated_at"],
                })

        # Economic summary
        repo = cur.execute("SELECT * FROM fi_economic_indicators WHERE indicator='repo_rate'").fetchone()
        inflation = cur.execute("SELECT * FROM fi_economic_indicators WHERE indicator='inflation_cpi'").fetchone()
        gdp = cur.execute("SELECT * FROM fi_economic_indicators WHERE indicator='gdp_growth'").fetchone()
        credit = cur.execute("SELECT * FROM fi_economic_indicators WHERE indicator='credit_growth'").fetchone()

        economy = {}
        for name, row in [("repo_rate", repo), ("inflation", inflation), ("gdp_growth", gdp), ("credit_growth", credit)]:
            if row:
                economy[name] = {"value": row["value"], "previous": row["previous"], "unit": row["unit"], "source": row["source"]}

        # Latest news
        latest_news = cur.execute(
            "SELECT id,source,title,category,impact_level,published_at,ai_summary,lending_impact FROM fi_news ORDER BY published_at DESC LIMIT 5"
        ).fetchall()

        # Alerts
        tok = _user_token(authorization)
        alerts = cur.execute(
            "SELECT COUNT(*) c FROM fi_alerts WHERE session_token=? AND is_read=0", (tok,)
        ).fetchone()["c"]

        # Credit environment score (derived)
        repo_val = repo["value"] if repo else 6.5
        infl_val = inflation["value"] if inflation else 5.0
        gdp_val = gdp["value"] if gdp else 6.8
        credit_val = credit["value"] if credit else 15.0
        env_score = round(min(100, max(30,
            50 + (gdp_val - 5) * 8 - (repo_val - 5) * 6 - (infl_val - 4) * 5 + (credit_val - 10) * 1.5
        )), 1)
        env_label = "FAVORABLE" if env_score >= 70 else ("NEUTRAL" if env_score >= 50 else "CHALLENGING")

        return {
            "market_status": market_assets,
            "economy": economy,
            "latest_news": [dict(r) for r in latest_news],
            "unread_alerts": alerts,
            "lending_environment": {"score": env_score, "label": env_label},
            "last_updated": now,
        }
    finally:
        conn.close()


# ── Markets ──────────────────────────────────────────────────────────────────

@router.get("/markets")
def markets(region: str = "all", asset_type: str = "all"):
    conn = _conn()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM fi_market_assets WHERE 1=1"
        params: list[Any] = []
        if region != "all":
            q += " AND region=?"
            params.append(region)
        if asset_type != "all":
            q += " AND asset_type=?"
            params.append(asset_type)
        rows = cur.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/markets/{symbol}")
def market_detail(symbol: str, range_: str = Query("3M", alias="range")):
    conn = _conn()
    try:
        cur = conn.cursor()
        asset = cur.execute("SELECT * FROM fi_market_assets WHERE symbol=?", (symbol,)).fetchone()
        if not asset:
            raise HTTPException(404, "Asset not found")

        days_map = {"1D": 1, "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "5Y": 1825}
        days = days_map.get(range_, 90)
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        snapshots = cur.execute(
            "SELECT price, volume, ts FROM fi_market_snapshots WHERE symbol=? AND ts>=? ORDER BY ts",
            (symbol, cutoff),
        ).fetchall()

        # Related news
        related = cur.execute(
            "SELECT id,title,source,published_at,category,impact_level FROM fi_news WHERE category IN ('markets','economy','banking') ORDER BY published_at DESC LIMIT 5"
        ).fetchall()

        return {
            "asset": dict(asset),
            "history": [dict(r) for r in snapshots],
            "related_news": [dict(r) for r in related],
        }
    finally:
        conn.close()


# ── News ─────────────────────────────────────────────────────────────────────

@router.get("/news")
def news(
    category: str = "all",
    country: str = "all",
    search: str = "",
    page: int = 1,
    page_size: int = 20,
):
    conn = _conn()
    try:
        cur = conn.cursor()
        q = "SELECT id,source,title,description,category,country,published_at,impact_level,market_impact,lending_impact,ai_confidence,ai_summary,tags,image_url,source_url FROM fi_news WHERE 1=1"
        params: list[Any] = []
        if category != "all":
            q += " AND category=?"
            params.append(category)
        if country != "all":
            q += " AND country=?"
            params.append(country)
        if search:
            q += " AND (title LIKE ? OR description LIKE ? OR ai_summary LIKE ?)"
            params.extend([f"%{search}%"] * 3)
        total = cur.execute(f"SELECT COUNT(*) c FROM ({q})", params).fetchone()["c"]
        q += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        rows = cur.execute(q, params).fetchall()
        return {"total": total, "page": page, "page_size": page_size, "articles": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── News Ticker for Financial Intelligence ───────────────────────────────────
# NOTE: must be declared BEFORE /news/{article_id} or FastAPI matches the
# literal "ticker" against the int path param and returns 422.

@router.get("/news/ticker")
def news_ticker():
    conn = _conn()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id,title,source,category,impact_level,published_at FROM fi_news ORDER BY published_at DESC LIMIT 10"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/news/{article_id}")
def news_article(article_id: int):
    conn = _conn()
    try:
        cur = conn.cursor()
        article = cur.execute("SELECT * FROM fi_news WHERE id=?", (article_id,)).fetchone()
        if not article:
            raise HTTPException(404, "Article not found")
        related = cur.execute(
            "SELECT id,title,source,published_at,category FROM fi_news WHERE id!=? AND category=? ORDER BY published_at DESC LIMIT 5",
            (article_id, article["category"]),
        ).fetchall()
        return {"article": dict(article), "related": [dict(r) for r in related]}
    finally:
        conn.close()


# ── Economy ──────────────────────────────────────────────────────────────────

@router.get("/economy")
def economy():
    conn = _conn()
    try:
        cur = conn.cursor()
        indicators = cur.execute("SELECT * FROM fi_economic_indicators ORDER BY indicator").fetchall()
        return [dict(r) for r in indicators]
    finally:
        conn.close()


# ── Credit Environment ──────────────────────────────────────────────────────

@router.get("/credit-environment")
def credit_environment():
    conn = _conn()
    try:
        cur = conn.cursor()
        indicators = cur.execute("SELECT * FROM fi_economic_indicators ORDER BY indicator").fetchall()
        # Derive credit environment assessment
        credit_g = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='credit_growth'").fetchone()
        repo_r = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='repo_rate'").fetchone()
        infl = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='inflation_cpi'").fetchone()

        cg = credit_g["value"] if credit_g else 15
        rr = repo_r["value"] if repo_r else 6.5
        inf = infl["value"] if infl else 5.0

        factors = []
        if cg >= 14:
            factors.append({"name": "Credit Growth", "status": "positive", "detail": f"Credit growing at {cg}%"})
        else:
            factors.append({"name": "Credit Growth", "status": "neutral", "detail": f"Credit growth at {cg}%"})

        if rr <= 6.5:
            factors.append({"name": "Policy Rate", "status": "positive", "detail": f"Repo rate at {rr}% — accommodative"})
        else:
            factors.append({"name": "Policy Rate", "status": "negative", "detail": f"Repo rate elevated at {rr}%"})

        if inf <= 5.0:
            factors.append({"name": "Inflation", "status": "positive", "detail": f"CPI at {inf}% — within tolerance"})
        else:
            factors.append({"name": "Inflation", "status": "negative", "detail": f"CPI at {inf}% — above target"})

        score = round(min(100, max(30, 50 + (cg - 10) * 5 - (rr - 5) * 8 - (inf - 4) * 6)), 1)
        label = "POSITIVE" if score >= 70 else ("NEUTRAL" if score >= 50 else "CAUTIOUS")

        return {
            "score": score,
            "label": label,
            "factors": factors,
            "indicators": [dict(r) for r in indicators],
        }
    finally:
        conn.close()


# ── Watchlist ────────────────────────────────────────────────────────────────

@router.get("/watchlist")
def get_watchlist(authorization: Optional[str] = Header(default=None)):
    tok = _user_token(authorization)
    conn = _conn()
    try:
        cur = conn.cursor()
        wl = cur.execute("SELECT * FROM fi_watchlists WHERE session_token=? LIMIT 1", (tok,)).fetchone()
        if not wl:
            cur.execute("INSERT INTO fi_watchlists (session_token,name,created_at) VALUES (?,?,?)",
                        (tok, "My Watchlist", datetime.utcnow().isoformat()))
            conn.commit()
            wl = cur.execute("SELECT * FROM fi_watchlists WHERE session_token=? LIMIT 1", (tok,)).fetchone()
        items = cur.execute("SELECT wi.symbol, a.name, a.asset_type, a.current_price, a.change_pct, a.change_abs, a.sector, a.region, a.currency "
                            "FROM fi_watchlist_items wi LEFT JOIN fi_market_assets a ON wi.symbol=a.symbol "
                            "WHERE wi.watchlist_id=?", (wl["id"],)).fetchall()
        return {"watchlist": dict(wl), "items": [dict(r) for r in items]}
    finally:
        conn.close()


@router.post("/watchlist/add")
def add_to_watchlist(symbol: str, authorization: Optional[str] = Header(default=None)):
    tok = _user_token(authorization)
    conn = _conn()
    try:
        cur = conn.cursor()
        wl = cur.execute("SELECT * FROM fi_watchlists WHERE session_token=? LIMIT 1", (tok,)).fetchone()
        if not wl:
            cur.execute("INSERT INTO fi_watchlists (session_token,name,created_at) VALUES (?,?,?)",
                        (tok, "My Watchlist", datetime.utcnow().isoformat()))
            conn.commit()
            wl = cur.execute("SELECT * FROM fi_watchlists WHERE session_token=? LIMIT 1", (tok,)).fetchone()
        asset = cur.execute("SELECT * FROM fi_market_assets WHERE symbol=?", (symbol,)).fetchone()
        if not asset:
            raise HTTPException(404, "Asset not found")
        try:
            cur.execute("INSERT INTO fi_watchlist_items (watchlist_id,symbol,added_at) VALUES (?,?,?)",
                        (wl["id"], symbol, datetime.utcnow().isoformat()))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        return {"ok": True}
    finally:
        conn.close()


@router.post("/watchlist/remove")
def remove_from_watchlist(symbol: str, authorization: Optional[str] = Header(default=None)):
    tok = _user_token(authorization)
    conn = _conn()
    try:
        cur = conn.cursor()
        wl = cur.execute("SELECT * FROM fi_watchlists WHERE session_token=? LIMIT 1", (tok,)).fetchone()
        if wl:
            cur.execute("DELETE FROM fi_watchlist_items WHERE watchlist_id=? AND symbol=?", (wl["id"], symbol))
            conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(authorization: Optional[str] = Header(default=None), unread_only: bool = False):
    tok = _user_token(authorization)
    conn = _conn()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM fi_alerts WHERE session_token=?"
        params: list[Any] = [tok]
        if unread_only:
            q += " AND is_read=0"
        q += " ORDER BY created_at DESC LIMIT 50"
        rows = cur.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int, authorization: Optional[str] = Header(default=None)):
    tok = _user_token(authorization)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE fi_alerts SET is_read=1 WHERE id=? AND session_token=?", (alert_id, tok))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── Ticker ───────────────────────────────────────────────────────────────────

@router.get("/ticker")
def ticker():
    conn = _conn()
    try:
        cur = conn.cursor()
        syms = ["^NSEI", "^BSESN", "USDINR=X", "GC=F", "BTC-USD", "^NSEBANK"]
        assets = cur.execute(
            f"SELECT symbol,name,current_price,change_pct,change_abs FROM fi_market_assets WHERE symbol IN ({','.join('?'*len(syms))})",
            syms,
        ).fetchall()
        return [dict(r) for r in assets]
    finally:
        conn.close()


# ── AI Briefing ──────────────────────────────────────────────────────────────

@router.get("/briefing")
def ai_briefing():
    conn = _conn()
    try:
        cur = conn.cursor()
        repo = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='repo_rate'").fetchone()
        infl = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='inflation_cpi'").fetchone()
        gdp = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='gdp_growth'").fetchone()
        credit = cur.execute("SELECT value FROM fi_economic_indicators WHERE indicator='credit_growth'").fetchone()
        nifty = cur.execute("SELECT change_pct FROM fi_market_assets WHERE symbol='^NSEI'").fetchone()
        usdinr = cur.execute("SELECT change_pct FROM fi_market_assets WHERE symbol='USDINR=X'").fetchone()

        rr = repo["value"] if repo else 6.5
        inf = infl["value"] if infl else 5.0
        g = gdp["value"] if gdp else 6.8
        cg = credit["value"] if credit else 15.0
        np = nifty["change_pct"] if nifty else 0
        fx = usdinr["change_pct"] if usdinr else 0

        sections = {}
        sections["markets"] = f"Indian equity markets are {'up' if np > 0 else 'down'} {abs(np):.2f}%. USD/INR moved {fx:+.2f}%. Global cues remain {'supportive' if np > 0 else 'cautious'}."
        sections["economy"] = f"GDP growth at {g}% YoY. CPI inflation at {inf}% remains above the RBI's 4% target. Industrial production shows {'improvement' if g > 6.5 else 'moderation'}."
        sections["credit"] = f"Credit growth at {cg}% indicates {'robust' if cg > 14 else 'moderate'} lending activity. Policy rate stable at {rr}%. {'Accommodative' if rr <= 6.5 else 'Tight'} monetary stance supports {'borrowing' if rr <= 6.5 else 'savings'}."
        sections["lending"] = f"{'Stable' if rr <= 6.5 and inf <= 5 else 'Mixed'} lending environment. {'Lower' if rr <= 6.5 else 'Higher'} rates may {'support' if rr <= 6.5 else 'pressure'} borrower repayment capacity. Credit conditions are {'favorable' if cg > 14 else 'neutral'}."
        sections["watch"] = f"Monitor RBI policy signals, inflation trajectory, and credit growth trends. {'FII flows and currency movements warrant attention.' if abs(fx) > 0.3 else 'External conditions stable.'}"

        summary = f"Today's lending environment remains broadly {'stable' if g > 6 and inf < 5.5 else 'mixed'}. Markets are {'positive' if np > 0 else 'negative'}. Credit conditions are {'supportive' if cg > 14 else 'moderate'}. {'Inflation remains the key risk to monitor.' if inf > 5 else 'Inflation within tolerance band.'}"

        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "summary": summary,
            "sections": sections,
            "key_metrics": {
                "repo_rate": rr, "inflation": inf, "gdp_growth": g,
                "credit_growth": cg, "nifty_change": round(np, 2),
                "usd_inr_change": round(fx, 2),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    finally:
        conn.close()


# ── Sources ──────────────────────────────────────────────────────────────────

@router.get("/sources")
def sources():
    with _live_lock:
        m_mode = _live_status["markets"]
        n_mode = _live_status["news"]
    return {
        "market_data": {"provider": "Yahoo Finance (live)" if m_mode == "live" else "Simulated (seeded)", "status": "active", "mode": m_mode, "last_updated": datetime.utcnow().isoformat(), "coverage": "Indian & Global markets"},
        "news_data": {"provider": "NewsAPI.org (live)" if n_mode == "live" else "Simulated (seeded)", "status": "active", "mode": n_mode, "last_updated": datetime.utcnow().isoformat(), "coverage": "Financial news"},
        "economic_data": {"provider": "Simulated (seeded)", "status": "active", "mode": "seeded", "last_updated": datetime.utcnow().isoformat(), "coverage": "Indian economic indicators"},
        "internal_data": {"provider": "LendSure", "status": "active", "mode": "live", "last_updated": datetime.utcnow().isoformat(), "coverage": "Borrower portfolio"},
    }


# ── Portfolio impact (REAL portfolio × current environment) ──────────────────

@router.get("/portfolio-impact")
def portfolio_impact():
    """What does the current environment mean for YOUR portfolio?
    Computed from real ls_* data only — no fabricated relationships."""
    conn = _conn()
    try:
        cur = conn.cursor()
        try:
            rows = cur.execute(
                "SELECT a.risk_level, a.trust_score, a.decision, "
                "b.avg_debt_6m, b.avg_income_6m, b.requested_amount "
                "FROM ls_analyses a "
                "JOIN (SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x "
                "ON x.borrower_id=a.borrower_id AND x.m=a.id "
                "LEFT JOIN ls_borrowers b ON b.borrower_id=a.borrower_id").fetchall()
        except Exception:
            return {"available": False, "reason": "portfolio tables unavailable"}
        rows = [dict(r) for r in rows]
        by_risk: dict[str, int] = {}
        high_dti = 0
        trusts = []
        manual = 0
        for r in rows:
            rl = r.get("risk_level") or "UNKNOWN"
            by_risk[rl] = by_risk.get(rl, 0) + 1
            inc = r.get("avg_income_6m") or 0
            if inc > 0 and (r.get("avg_debt_6m") or 0) / inc > 0.5:
                high_dti += 1
            if r.get("trust_score") is not None:
                trusts.append(r["trust_score"])
            if r.get("decision") == "MANUAL_REVIEW":
                manual += 1
        econ = {r["indicator"]: r["value"] for r in
                cur.execute("SELECT indicator, value FROM fi_economic_indicators").fetchall()}
        repo = econ.get("repo_rate", 6.5)
        infl = econ.get("inflation_cpi", 5.0)
        pressures = []
        if repo > 6.0:
            pressures.append({"name": "Interest-rate pressure", "level": "high" if repo > 7 else "medium",
                              "detail": f"Repo at {repo}% raises borrowing costs for rate-sensitive borrowers."})
        else:
            pressures.append({"name": "Interest-rate pressure", "level": "low",
                              "detail": f"Repo at {repo}% is accommodative."})
        if infl > 5.0:
            pressures.append({"name": "Inflation pressure", "level": "high" if infl > 6 else "medium",
                              "detail": f"CPI at {infl}% erodes real repayment capacity."})
        else:
            pressures.append({"name": "Inflation pressure", "level": "low",
                              "detail": f"CPI at {infl}% is within tolerance."})
        exposed = (by_risk.get("HIGH", 0) + by_risk.get("MEDIUM", 0) + high_dti)
        return {
            "available": True,
            "borrowers": len(rows),
            "by_risk": by_risk,
            "high_dti_share": round(high_dti / len(rows), 3) if rows else 0,
            "avg_trust": round(sum(trusts) / len(trusts), 1) if trusts else 0,
            "manual_review": manual,
            "pressures": pressures,
            "potentially_affected": exposed,
            "method": "Counts from latest analysis per borrower; high-DTI = debt/income > 0.5. Educational indicator, not advice.",
        }
    finally:
        conn.close()
