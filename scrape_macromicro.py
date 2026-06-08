from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except (AttributeError, ValueError):
    pass

import requests
from curl_cffi import requests as cffi_requests

URL = "https://www.macromicro.me/macro/us"
DEFAULT_OUT_DIR = Path(__file__).parent

PROXY = os.environ.get("SCRAPER_PROXY")

_GOOGLEBOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_IMPERSONATIONS = ["chrome120", "chrome110", "safari17_0"]


def _is_blocked(text: str) -> bool:
    return len(text) < 5000 or "Just a moment" in text


def _get_via_googlebot(url: str, timeout: int):
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    verify = not PROXY
    try:
        resp = requests.get(
            url,
            headers=_GOOGLEBOT_HEADERS,
            timeout=timeout,
            proxies=proxies,
            verify=verify,
        )
        if resp.status_code == 200 and not _is_blocked(resp.text):
            return resp
    except Exception:
        pass
    return None


def _get_via_cffi(url: str, timeout: int):
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    verify = not PROXY
    last_exc = None
    for attempt, imp in enumerate(_IMPERSONATIONS):
        try:
            resp = cffi_requests.get(
                url,
                impersonate=imp,
                timeout=timeout,
                proxies=proxies,
                verify=verify,
            )
            if resp.status_code == 200 and not _is_blocked(resp.text):
                return resp
            if resp.status_code == 403:
                last_exc = Exception(f"403 ({imp})")
                if attempt < len(_IMPERSONATIONS) - 1:
                    time.sleep(2**attempt)
                continue
            resp.raise_for_status()
        except Exception as exc:
            last_exc = exc
            if attempt < len(_IMPERSONATIONS) - 1:
                time.sleep(2**attempt)
    raise last_exc or RuntimeError("All strategies failed")


def _fetch(url: str, timeout: int = 60):
    resp = _get_via_googlebot(url, timeout)
    if resp is not None:
        return resp
    return _get_via_cffi(url, timeout)


SCRAPER = type(
    "Scraper",
    (),
    {"get": staticmethod(lambda url, timeout=60: _fetch(url, timeout))},
)()


def fetch_page(url: str = URL) -> str:
    scraper = SCRAPER
    resp = scraper.get(url, timeout=60)
    resp.raise_for_status()
    if "Just a moment" in resp.text:
        raise RuntimeError("Blocked by Cloudflare challenge.")
    return resp.text


def extract_js_value(html_text: str, var_name: str) -> str:
    m = re.search(rf"(?:let|var|const)\s+{re.escape(var_name)}\s*=\s*", html_text)
    if not m:
        raise ValueError(f"Variable {var_name!r} not found in page.")
    start = m.end()
    open_bracket = html_text[start]
    if open_bracket not in "[{":
        raise ValueError(f"{var_name!r} is not an array or object literal.")
    close_bracket = "]" if open_bracket == "[" else "}"
    depth, in_str, escaped, quote = 0, False, False, ""
    for j in range(start, len(html_text)):
        c = html_text[j]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                in_str = False
        else:
            if c in "\"'":
                in_str, quote = True, c
            elif c == open_bracket:
                depth += 1
            elif c == close_bracket:
                depth -= 1
                if depth == 0:
                    return html_text[start : j + 1]
    raise ValueError(f"Unbalanced brackets while reading {var_name!r}.")


def parse_last_rows(raw: str):
    if not raw:
        return None, None, None, None, 0
    try:
        series = json.loads(html.unescape(raw))
    except (json.JSONDecodeError, TypeError):
        return None, None, None, None, 0
    if not series or not series[0]:
        return None, None, None, None, len(series)
    prev_date, prev_val = None, None
    if len(series[0]) >= 2:
        prev_date, prev_val = series[0][-2]
    last_date, last_val = series[0][-1]
    try:
        prev_val = float(prev_val) if prev_val is not None else None
    except (TypeError, ValueError):
        pass
    try:
        last_val = float(last_val)
    except (TypeError, ValueError):
        pass
    return prev_date, prev_val, last_date, last_val, len(series)


CHART_ROW_COLUMNS = [
    "id", "name", "slug", "url", "country", "n_series",
    "prev_date", "prev_value", "latest_date", "latest_value",
    "count_booked", "count_comments", "count_liked", "description",
]


def build_chart_rows(charts: list[dict]) -> list[dict]:
    rows = []
    for c in charts:
        prev_date, prev_val, latest_date, latest_val, n_series = parse_last_rows(
            c.get("series_last_rows")
        )
        rows.append(
            {
                "id": c.get("id"),
                "name": html.unescape(c.get("name", "")),
                "slug": c.get("slug"),
                "url": c.get("url"),
                "country": c.get("country"),
                "n_series": n_series,
                "prev_date": prev_date,
                "prev_value": prev_val,
                "latest_date": latest_date,
                "latest_value": latest_val,
                "count_booked": c.get("count_booked", 0),
                "count_comments": c.get("count_comments", 0),
                "count_liked": c.get("count_liked", 0),
                "description": html.unescape(c.get("description", ""))
                .replace("\n", " ")
                .strip(),
            }
        )
    return rows


def write_chart_rows_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHART_ROW_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


TARGET_MARKET_IDS = {77, 144242, 75, 76, 549, 551, 552, 550, 74, 73}

THEMATIC_COLLECTIONS = {
    "Recession": "global-recession",
    "Spreads": "spreads",
    "Volatility": "volatility",
    "Sentiment": "global-sentiment-indicator",
}

CDS_COUNTRIES = [
    ("US", "https://www.investing.com/rates-bonds/united-states-cds-5-years-usd"),
    ("UK", "https://www.investing.com/rates-bonds/uk-cds-5-years-gbp"),
    ("France", "https://www.investing.com/rates-bonds/france-cds-5-years-usd"),
    ("Japan", "https://www.investing.com/rates-bonds/japan-cds-5-year-usd"),
    ("China", "https://www.investing.com/rates-bonds/china-cds-5-years-usd"),
    ("Italy", "https://www.investing.com/rates-bonds/italy-cds-5-years-usd"),
    ("Spain", "https://www.investing.com/rates-bonds/spain-cds-5-years-usd"),
    ("Mexico", "https://www.investing.com/rates-bonds/mexico-cds-5-years-usd"),
    ("Brazil", "https://www.investing.com/rates-bonds/brazil-cds-5-years-usd"),
    ("Indonesia", "https://www.investing.com/rates-bonds/indonesia-cds-5-years-usd"),
    ("Turkey", "https://www.investing.com/rates-bonds/turkey-cds-5-year-usd"),
]


def extract_cds_data() -> list[dict]:
    scraper = SCRAPER
    result = []
    for code, url in CDS_COUNTRIES:
        try:
            resp = scraper.get(url, timeout=30)
            text = resp.text
            idx = text.find("instrument-price-last")
            if idx >= 0:
                m = re.search(r">(\d{1,3}[.]\d{2})<", text[idx : idx + 100])
                if m:
                    result.append({"code": code, "value": float(m.group(1))})
                    continue
            nums = re.findall(r">(\d{1,3}[.]\d{2})<", text)
            likely = [n for n in nums if 5 < float(n) < 500]
            if likely:
                result.append({"code": code, "value": float(likely[0])})
            else:
                print(f"  [CDS/{code}] no value found")
                result.append({"code": code, "value": None})
        except Exception as e:
            print(f"  [CDS/{code}] error: {e}")
            result.append({"code": code, "value": None})
    return result


def extract_thematic_indicators() -> list[dict]:
    scraper = SCRAPER
    try:
        text = scraper.get(
            "https://www.macromicro.me/trader-insights", timeout=60
        ).text
    except Exception as e:
        print(f"  [thematic] fetch error: {e}")
        return []
    result = []
    for label, slug in THEMATIC_COLLECTIONS.items():
        pat = re.escape("/collections/") + r"\d+/" + re.escape(slug)
        m = re.search(pat, text)
        if not m:
            print(f"  [thematic] {label}: collection not found")
            continue
        full_url = "https://www.macromicro.me" + m.group(0)
        start = text.rfind('<div class="collection"', 0, m.start())
        if start < 0:
            start = m.start()
        end = text.find('</div>', start + 200)
        # find the closing </div> of the .bd section (2nd or 3rd </div> after URL)
        for _ in range(3):
            nxt = text.find('</div>', end + 1)
            if nxt > 0:
                end = nxt
            else:
                break
        block = text[start:end]
        sm = re.search(r'<h6 class="stat-name">(.*?)</h6>', block)
        stat_name = html.unescape(sm.group(1)) if sm else ""
        dm = re.search(r'<time>(.*?)</time>', block)
        date = dm.group(1) if dm else ""
        vm = re.search(r'<span class="val">(.*?)</span>', block)
        value = html.unescape(vm.group(1)) if vm else ""
        um = re.search(r'<span class="unit">(.*?)</span>', block)
        unit = html.unescape(um.group(1)) if um else ""
        result.append(
            {
                "label": label,
                "stat_name": stat_name,
                "date": date,
                "value": value,
                "unit": unit,
                "url": full_url,
            }
        )
    return result


STOCK_INDEX_SOURCES = [
    ("EU", "Europe", "/macro/eu", 0, 0),
    ("JP", "Japan", "/macro/jp", 0, 0),
    ("TW", "Taiwan", "/macro/tw", 0, 0),
    ("CN", "China", "/macro/cn", 0, 0),
]

HANG_SENG_CN_PAGE_IDX = 2


def extract_stock_indices() -> list[dict]:
    scraper = SCRAPER
    result = []
    seen = set()
    for code, label, path, page_idx, item_idx in STOCK_INDEX_SOURCES:
        url = f"https://www.macromicro.me{path}"
        try:
            text = scraper.get(url, timeout=60).text
        except Exception as e:
            print(f"  [{label}] fetch error: {e}")
            continue
        m = re.search(
            r"(?:let|var|const)\s+paged_instants\s*=\s*(.*?)\s*;",
            text,
            re.DOTALL,
        )
        if not m:
            print(f"  [{label}] no paged_instants")
            continue
        instants = json.loads(m.group(1))
        page = instants[page_idx]
        item = page[item_idx]
        chid = item.get("chart_id")
        if chid in seen:
            continue
        seen.add(chid)
        chart_obj = item.get("chart", {})
        result.append(
            {
                "code": code,
                "label": label,
                "chart_id": chid,
                "name": html.unescape(item.get("name", "")),
                "value": item.get("val_num", ""),
                "slug": chart_obj.get("slug", ""),
                "url": f"https://www.macromicro.me/charts/{chid}/{chart_obj.get('slug', '')}",
            }
        )
    # HK from CN page
    try:
        cn_text = scraper.get(
            "https://www.macromicro.me/macro/cn", timeout=60
        ).text
        m_hk = re.search(
            r"(?:let|var|const)\s+paged_instants\s*=\s*(.*?)\s*;",
            cn_text,
            re.DOTALL,
        )
        if m_hk:
            cn_instants = json.loads(m_hk.group(1))
            for page in cn_instants:
                for item in page:
                    if item.get("chart_id") == 283:
                        chart_obj = item.get("chart", {})
                        result.append(
                            {
                                "code": "HK",
                                "label": "Hong Kong",
                                "chart_id": 283,
                                "name": html.unescape(item.get("name", "")),
                                "value": item.get("val_num", ""),
                                "slug": chart_obj.get("slug", ""),
                                "url": f"https://www.macromicro.me/charts/283/{chart_obj.get('slug', '')}",
                            }
                        )
                        break
                else:
                    continue
                break
    except Exception as e:
        print(f"  [HK] fetch error: {e}")
    # BR from collection page ETF data
    try:
        br_text = scraper.get(
            "https://www.macromicro.me/collections/220/ibov-index", timeout=60
        ).text
        m_br = re.search(r"let\s+etf_data\s*=\s*({[^;]+});", br_text)
        if m_br:
            br_etf = json.loads(m_br.group(1))
            for etf in br_etf.get("us_out", []):
                if etf.get("ticker") == "EWZ":
                    result.append(
                        {
                            "code": "BR",
                            "label": "Brazil",
                            "chart_id": 2593,
                            "name": "Bovespa (IBOV)",
                            "value": etf.get("last_close", ""),
                            "slug": "mm-ibov-index",
                            "url": "https://www.macromicro.me/charts/2593/mm-ibov-index",
                        }
                    )
                    break
    except Exception as e:
        print(f"  [BR] fetch error: {e}")
    # IN from collection page ETF data
    try:
        in_text = scraper.get(
            "https://www.macromicro.me/collections/141/mm-india", timeout=60
        ).text
        m_in = re.search(r"let\s+etf_data\s*=\s*({[^;]+});", in_text)
        if m_in:
            in_etf = json.loads(m_in.group(1))
            for etf in in_etf.get("tw_out", []):
                if etf.get("ticker") == "00652":
                    result.append(
                        {
                            "code": "IN",
                            "label": "India",
                            "chart_id": 2195,
                            "name": "Nifty 50",
                            "value": etf.get("last_close", ""),
                            "slug": "mm-india-index",
                            "url": "https://www.macromicro.me/charts/2195/mm-india-index",
                        }
                    )
                    break
    except Exception as e:
        print(f"  [IN] fetch error: {e}")
    return result


def extract_focus_stats(html_text: str) -> list[dict]:
    try:
        raw = extract_js_value(html_text, "paged_focus_stats")
    except ValueError:
        return []
    pages = json.loads(raw)
    seen = set()
    result = []
    for page in pages:
        for item in page:
            sid = item.get("stat_id")
            if sid in seen:
                continue
            seen.add(sid)
            ch = item.get("chart") or {}
            link = ch.get("url") if isinstance(ch, dict) else item.get("chart_link", "")
            result.append(
                {
                    "stat_id": sid,
                    "name": html.unescape(item.get("stat_name", "")),
                    "prev_value": (item.get("pval") or "").strip(),
                    "curr_value": (item.get("xval") or "").strip(),
                    "url": f"https://www.macromicro.me{link}"
                    if link and not link.startswith("http")
                    else link or "",
                }
            )
    return result


def extract_market_indicators(html_text: str) -> list[dict]:
    try:
        raw = extract_js_value(html_text, "paged_instants")
    except ValueError:
        return []
    instants = json.loads(raw)
    result = []
    seen = set()
    for page in instants:
        for item in page:
            chid = item.get("chart_id")
            if chid in TARGET_MARKET_IDS and chid not in seen:
                seen.add(chid)
                chart = item.get("chart", {})
                val_str = item.get("val_str", "")
                if val_str and str(val_str).strip():
                    value = str(val_str).strip()
                    suffix = ""
                else:
                    value = item.get("val_num", "")
                    suffix = item.get("suffix", "")
                    if not suffix:
                        stat = item.get("stat", {})
                        if stat.get("units") == "pct":
                            suffix = "%"
                result.append(
                    {
                        "id": chid,
                        "name": html.unescape(item.get("name", "")),
                        "value": value,
                        "suffix": suffix,
                        "slug": chart.get("slug", ""),
                        "url": f"https://www.macromicro.me/charts/{chid}/{chart.get('slug', '')}",
                    }
                )
    return result


def extract_all_series_data(charts: list[dict]) -> dict:
    data = {}
    for c in charts:
        chart_id = c["id"]
        raw = c.get("series_last_rows")
        if raw:
            try:
                series = json.loads(html.unescape(raw))
                parsed = []
                for s in series:
                    parsed.append([{"date": p[0], "value": p[1]} for p in s])
                data[str(chart_id)] = parsed
            except (json.JSONDecodeError, TypeError):
                data[str(chart_id)] = None
        else:
            data[str(chart_id)] = None
    return data


def enrich_chart_data(charts: list[dict]) -> list[dict]:
    enriched = []
    total = len(charts)
    for i, c in enumerate(charts, 1):
        prev_date, prev_val, latest_date, latest_val, n_series = parse_last_rows(
            c.get("series_last_rows")
        )
        entry = {
            "id": c.get("id"),
            "name": html.unescape(c.get("name", "")),
            "slug": c.get("slug"),
            "url": c.get("url"),
            "country": c.get("country"),
            "prev_date": prev_date,
            "prev_value": prev_val,
            "latest_date": latest_date,
            "latest_value": latest_val,
            "n_series": n_series,
            "count_booked": c.get("count_booked", 0),
            "count_comments": c.get("count_comments", 0),
            "count_liked": c.get("count_liked", 0),
            "description": html.unescape(c.get("description", ""))
            .replace("\n", " ")
            .strip(),
        }
        print(f"  [{i}/{total}] {entry['name']} (id={entry['id']})")
        enriched.append(entry)
    return enriched


def generate_dashboard_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MacroMicro US Top Charts Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:20px}
h1{font-size:1.6rem;margin-bottom:4px}
.subtitle{color:#666;font-size:.9rem;margin-bottom:20px}
.card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.side-section{display:flex;gap:16px;margin-bottom:16px}
.side-section .left{flex:0 0 auto;width:420px}
.side-section .right{flex:1;min-width:0}
.side-section .tbl-wrap{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:14px 16px}
.section-title{font-size:1.1rem;font-weight:700;margin-bottom:10px;color:#333}
.ind-tables{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:24px}
.ind-table{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden}
.ind-table h3{padding:12px 14px 8px;font-size:.85rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#555}
.ind-table table{width:100%;border-collapse:collapse;font-size:.82rem}
.ind-table td{padding:10px 14px}
.ind-table .val{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.ind-table a{color:#1a1a2e;text-decoration:none}
.ind-table a:hover{color:#2563eb}
table.full{width:100%;border-collapse:collapse;font-size:.82rem}
table.full th{text-align:left;padding:8px 10px;color:#555;font-weight:600;white-space:nowrap}
table.full td{padding:8px 10px;vertical-align:top}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.desc{max-width:320px;font-size:.78rem;color:#666;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
@media(max-width:768px){
body{padding:10px}
h1{font-size:1.2rem}
.side-section{flex-direction:column}
.side-section .left,.side-section .right{width:100%!important;flex:none!important}
.ind-tables{grid-template-columns:1fr}
.tbl-wrap{overflow-x:auto}
.desc{display:none}
#tableBody tr td:last-child,.side-section:last-child table.full thead tr th:last-child{display:none}
table.full thead th{font-size:.72rem;padding:6px}
table.full tbody td{padding:6px;font-size:.75rem}
}
@media(prefers-color-scheme:dark){body{background:#0f172a;color:#e2e8f0} .ind-table{background:#1e293b;box-shadow:0 1px 4px rgba(0,0,0,.3)} .tbl-wrap{background:#1e293b} .side-section .tbl-wrap{background:#1e293b;box-shadow:0 1px 4px rgba(0,0,0,.3)} .ind-table h3{color:#94a3b8} .ind-table a{color:#e2e8f0} th{color:#94a3b8} .desc{color:#94a3b8} .subtitle{color:#94a3b8}}
</style>
</head>
<body>
<h1>MacroMicro US &mdash; Top Charts</h1>
<p class="subtitle">Data sourced from macromicro.me &middot; <span id="updateTime"></span></p>

<div class="side-section">
<div class="left">
<div class="tbl-wrap">
<div class="section-title">WORLD STOCK INDICES</div>
<table class="full">
<thead><tr><th>Country</th><th>Index</th><th>Value</th></tr></thead>
<tbody id="stockBody"></tbody>
</table>
</div>
<div class="tbl-wrap" style="margin-top:16px">
<div class="section-title">THEMATIC INDICATORS</div>
<table class="full">
<thead><tr><th>Category</th><th>Indicator</th><th>Value</th></tr></thead>
<tbody id="thematicBody"></tbody>
</table>
</div>
</div>
<div class="right">
<div class="tbl-wrap">
<div class="section-title">RECENT FOCUS DATA</div>
<table class="full">
<thead><tr><th>Indicator</th><th>Previous</th><th>Current</th></tr></thead>
<tbody id="focusBody"></tbody>
</table>
</div>
</div>
</div>

<div id="indTables" class="ind-tables"></div>

<div class="card">
<div class="section-title">KEY INDICATORS</div>
<table class="full">
<thead><tr><th>Name</th><th>Latest</th><th>Previous Value</th><th>Value</th><th>Description</th></tr></thead>
<tbody id="tableBody"></tbody>
</table>
</div>

<script>
const CATS = {
  Fed: {title:'FED', ids:[77,144242]},
  Bonds: {title:'BONDS', ids:[75,76]},
  Stocks: {title:'STOCKS', ids:[549,551,552,550]},
  Commodities: {title:'COMMODITIES', ids:[74,73]},
};
fetch('dashboard_data.json').then(r=>r.json()).then(data=>{
  document.getElementById('updateTime').textContent = 'Updated: ' + (data.fetched_at||'');
  const indicators = data.market_indicators||[];
  document.getElementById('indTables').innerHTML = Object.values(CATS).map(cat=>{
    const items = indicators.filter(i=>cat.ids.includes(i.id));
    if(!items.length) return '';
    return '<div class="ind-table"><h3>'+cat.title+'</h3><table><tbody>'+
      items.map(i=>'<tr><td><a href="'+i.url+'" target="_blank">'+i.name+'</a></td><td class="val">'+(i.value?i.value+(i.suffix?' '+i.suffix:''):'-')+'</td></tr>').join('')+
      '</tbody></table></div>';
  }).join('');
  const focus = data.focus_stats||[];
  document.getElementById('focusBody').innerHTML = focus.map(f=>{
    return '<tr><td>'+(f.url?'<a href="'+f.url+'" target="_blank">'+f.name+'</a>':f.name)+'</td><td>'+(f.prev_value||'-')+'</td><td>'+(f.curr_value||'-')+'</td></tr>';
  }).join('');
  const stocks = data.stock_indices||[];
  document.getElementById('stockBody').innerHTML = stocks.map(s=>{
    return '<tr><td>'+s.label+'</td><td>'+(s.url?'<a href="'+s.url+'" target="_blank">'+s.name+'</a>':s.name)+'</td><td class="val">'+(s.value||'-')+'</td></tr>';
  }).join('');
  const thematic = data.thematic_indicators||[];
  const cds = data.cds_data||[];
  let thematicHtml = thematic.map(t=>{
    const v = t.value+(t.unit?' '+t.unit:'');
    return '<tr><td>'+t.label+'</td><td>'+(t.url?'<a href="'+t.url+'" target="_blank">'+t.stat_name+'</a>':t.stat_name)+'</td><td class="val">'+(v||'-')+'</td></tr>';
  }).join('');
  if(cds.length){
    const cdsVals = cds.filter(d=>d.value!==null).map(d=>'<span style="margin-right:8px"><strong>'+d.code+'</strong> '+d.value+'</span>').join('');
    thematicHtml += '<tr><td>CDS</td><td>Sovereign 5Y CDS (bps)</td><td class="val">'+cdsVals+'</td></tr>';
  }
  document.getElementById('thematicBody').innerHTML = thematicHtml;
  const charts = data.charts;
  document.getElementById('tableBody').innerHTML = charts.map(c=>{
    const fmt = v => v!==null && !isNaN(v) ? Number(v).toFixed(2) : '-';
    const val = fmt(c.latest_value);
    const prev = fmt(c.prev_value);
    const date = c.latest_date||'-';
    return '<tr><td><a href="'+c.url+'" target="_blank">'+c.name+'</a></td><td>'+date+'</td><td>'+prev+'</td><td class="val">'+val+'</td><td><div class="desc">'+(c.description||'')+'</div></td></tr>';
  }).join('');
});
</script>
</body>
</html>"""


def run_scrape() -> dict:
    """Scrape and return the dashboard data dict. Raises on fetch failure."""
    html_text = fetch_page()
    charts = json.loads(extract_js_value(html_text, "top_charts"))

    enriched = enrich_chart_data(charts)
    market_indicators = extract_market_indicators(html_text)
    focus_stats = extract_focus_stats(html_text)
    stock_indices = extract_stock_indices()
    thematic_indicators = extract_thematic_indicators()
    cds_data = extract_cds_data()

    return {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "chart_count": len(enriched),
        "charts": enriched,
        "market_indicators": market_indicators,
        "focus_stats": focus_stats,
        "stock_indices": stock_indices,
        "thematic_indicators": thematic_indicators,
        "cds_data": cds_data,
        "_raw_charts": charts,
    }


def main(out_dir: Path | None = None) -> None:
    out_dir = out_dir or DEFAULT_OUT_DIR
    csv_path = out_dir / "top_charts.csv"
    dashboard_path = out_dir / "dashboard_data.json"
    series_path = out_dir / "series_last_rows.json"

    try:
        dashboard_data = run_scrape()
    except Exception as e:
        print(f"WARNING: Could not fetch page: {e}")
        print("Using previously committed data files (data may be stale).")
        return

    charts = dashboard_data.pop("_raw_charts")

    rows = build_chart_rows(charts)
    write_chart_rows_csv(rows, csv_path)
    print(f"Saved CSV: {csv_path}")

    series_data = extract_all_series_data(charts)
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump(series_data, f, ensure_ascii=False, indent=2)
    print(f"Saved series data: {series_path}")

    with open(dashboard_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)
    print(f"Saved dashboard data: {dashboard_path}")

    print(f"\nDone. {len(rows)} charts processed.")


if __name__ == "__main__":
    main()
