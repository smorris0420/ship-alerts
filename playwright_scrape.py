#!/usr/bin/env python3
# JS-rendered scrape of VesselFinder "Recent Port Calls" using Playwright (Chromium)
# pip install playwright beautifulsoup4 && python -m playwright install chromium

import os, json, hashlib, sys, traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse, urlunparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup, Tag, NavigableString

REPO_ROOT  = os.path.dirname(__file__)
DOCS_DIR   = os.path.join(REPO_ROOT, "docs")
STATE_PATH = os.path.join(REPO_ROOT, "state.json")
SHIPS_PATH = os.path.join(REPO_ROOT, "ships.json")

# ---- History settings ----
HIST_DIR      = os.path.join(REPO_ROOT, "history")
PER_SHIP_CAP  = 50    # Max events per ship feed
ALL_CAP       = 100   # Max events across all ships

# ---- Port timezone mapping (substring match, case-insensitive) ----
# If no match, we fall back to EST (America/New_York) as requested.
PORT_TZ_MAP = [
    # North America / Caribbean / Bahamas
    ("canaveral", "America/New_York"),
    ("everglades", "America/New_York"),
    ("fort lauderdale", "America/New_York"),
    ("castaway", "America/Nassau"),
    ("lookout cay", "America/Nassau"),
    ("nassau", "America/Nassau"),
    ("cozumel", "America/Cancun"),
    ("progreso", "America/Merida"),
    ("galveston", "America/Chicago"),
    ("san juan", "America/Puerto_Rico"),
    ("tortola", "America/Tortola"),
    ("st. maarten", "America/Lower_Princes"),
    ("st maarten", "America/Lower_Princes"),
    ("basseterre", "America/St_Kitts"),
    ("antigua", "America/Antigua"),
    ("falmouth", "America/Jamaica"),
    ("castries", "America/St_Lucia"),
    ("st. lucia", "America/St_Lucia"),
    ("curaçao", "America/Curacao"),
    ("willemstad", "America/Curacao"),
    ("aruba", "America/Aruba"),
    ("cayman", "America/Cayman"),
    ("roseau", "America/Dominica"),
    ("dominica", "America/Dominica"),

    # Mexico Pacific
    ("cabo", "America/Mazatlan"),
    ("ensenada", "America/Tijuana"),
    ("vallarta", "America/Bahia_Banderas"),

    # Alaska
    ("juneau", "America/Juneau"),
    ("skagway", "America/Juneau"),
    ("ketchikan", "America/Sitka"),
    ("icy strait", "America/Juneau"),
    ("glacier viewing", "America/Juneau"),

    # Hawaii
    ("honolulu", "Pacific/Honolulu"),
    ("kahului", "Pacific/Honolulu"),
    ("nawiliwili", "Pacific/Honolulu"),
    ("hilo", "Pacific/Honolulu"),

    # Oceania
    ("auckland", "Pacific/Auckland"),
    ("wellington", "Pacific/Auckland"),
    ("tauranga", "Pacific/Auckland"),
    ("christchurch", "Pacific/Auckland"),
    ("lyttelton", "Pacific/Auckland"),
    ("eden", "Australia/Sydney"),
    ("hobart", "Australia/Hobart"),
    ("melbourne", "Australia/Melbourne"),
    ("sydney", "Australia/Sydney"),
    ("noumea", "Pacific/Noumea"),
    ("suva", "Pacific/Fiji"),
    ("pago pago", "Pacific/Pago_Pago"),

    # Europe / Med / UK
    ("southampton", "Europe/London"),
    ("liverpool", "Europe/London"),
    ("portland", "Europe/London"),
    ("greenock", "Europe/London"),
    ("amsterdam", "Europe/Amsterdam"),
    ("rotterdam", "Europe/Amsterdam"),
    ("zeebrugge", "Europe/Brussels"),
    ("vigo", "Europe/Madrid"),
    ("bilbao", "Europe/Madrid"),
    ("malaga", "Europe/Madrid"),
    ("barcelona", "Europe/Madrid"),
    ("cadiz", "Europe/Madrid"),
    ("cartagena", "Europe/Madrid"),
    ("alesund", "Europe/Oslo"),
    ("bergen", "Europe/Oslo"),
    ("olden", "Europe/Oslo"),
    ("haugesund", "Europe/Oslo"),
    ("stavanger", "Europe/Oslo"),
    ("mekjarvik", "Europe/Oslo"),
    ("messina", "Europe/Rome"),
    ("civitavecchia", "Europe/Rome"),
    ("rome", "Europe/Rome"),
    ("naples", "Europe/Rome"),
    ("livorno", "Europe/Rome"),
    ("ajaccio", "Europe/Paris"),
    ("la coruna", "Europe/Madrid"),
    ("coruna", "Europe/Madrid"),
    ("chania", "Europe/Athens"),
    ("corfu", "Europe/Athens"),
    ("argostoli", "Europe/Athens"),
    ("santorini", "Europe/Athens"),
    ("mykonos", "Europe/Athens"),
    ("dubrovnik", "Europe/Zagreb"),
    ("athens", "Europe/Athens"),
    ("piraeus", "Europe/Athens"),
    ("valetta", "Europe/Malta"),
    ("malta", "Europe/Malta"),
    ("funchal", "Atlantic/Madeira"),

    # Canada
    ("vancouver", "America/Vancouver"),
    ("victoria", "America/Vancouver"),
]

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_history(slug: str):
    os.makedirs(HIST_DIR, exist_ok=True)
    path = os.path.join(HIST_DIR, f"{slug}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(slug: str, items: list):
    os.makedirs(HIST_DIR, exist_ok=True)
    path = os.path.join(HIST_DIR, f"{slug}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

# ✅ FIXED merge_items — preserves history when there are no new items
def merge_items(existing: list, new_items: list, cap: int):
    # Deduplicate: new events first, then old ones not duplicated
    seen = {it["guid"] for it in new_items}
    merged = list(new_items) + [it for it in existing if it["guid"] not in seen]
    return merged[:cap]

def rss_escape(s: str) -> str:
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def to_rfc2822(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def make_id(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()

def build_rss(channel_title: str, channel_link: str, items: list) -> str:
    xml_items = []
    for it in items:
        xml_items.append(f"""
  <item>
    <title>{rss_escape(it["title"])}</title>
    <link>{rss_escape(it.get("link",""))}</link>
    <guid isPermaLink="false">{rss_escape(it["guid"])}</guid>
    <pubDate>{rss_escape(it["pubDate"])}</pubDate>
    <description>{rss_escape(it.get("description",""))}</description>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{rss_escape(channel_title)}</title>
  <link>{rss_escape(channel_link)}</link>
  <description>{rss_escape(channel_title)} - Auto-generated</description>
  <lastBuildDate>{to_rfc2822(datetime.utcnow())}</lastBuildDate>
  {''.join(xml_items)}
</channel>
</rss>
"""

# ---- Time conversion helpers ----
def _parse_vf_time_utc(raw_time: str):
    """
    Parse strings like 'Nov 3, 22:05' as *UTC* for the current year.
    Returns timezone-aware UTC datetime or None if it can't parse.
    """
    if not raw_time:
        return None
    raw = raw_time.strip()
    fmts = ["%b %d, %H:%M", "%b %d, %H:%M:%S"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(raw, fmt)
            dt = dt.replace(year=datetime.utcnow().year, tzinfo=timezone.utc)
            return dt
        except:
            continue
    return None

def _port_zoneinfo(port_name: str):
    """
    Return local tz if matched, otherwise ALWAYS fall back to EST.
    """
    if not port_name:
        return ZoneInfo("America/New_York")
    name = port_name.lower()
    for needle, tz in PORT_TZ_MAP:
        if needle in name:
            try:
                return ZoneInfo(tz)
            except:
                break
    return ZoneInfo("America/New_York")  # fallback to EST

def format_times_for_notification(port_name: str, when_raw: str):
    """
    Build human-readable strings for EST and port-local time from a VF UTC timestamp.
    Returns (est_str or None, local_str or None).
    """
    dt_utc = _parse_vf_time_utc(when_raw)
    if not dt_utc:
        return None, None

    # EST (America/New_York)
    est = dt_utc.astimezone(ZoneInfo("America/New_York"))
    est_str = est.strftime("%b %d, %I:%M %p EST")

    # Port local (may be same as EST)
    local_tz = _port_zoneinfo(port_name)
    local_dt = dt_utc.astimezone(local_tz)
    tz_abbr = local_dt.tzname() or str(local_tz)
    local_str = local_dt.strftime(f"%b %d, %I:%M %p {tz_abbr}")

    return est_str, local_str

# ---- VesselFinder parsing ----
def _find_root(soup: BeautifulSoup):
    # Prefer header "Recent Port Calls"
    for tag in soup.find_all(lambda t: isinstance(t, Tag) and t.name in ("h1","h2","h3","h4","div")):
        txt = (tag.get_text(strip=True) or "").lower()
        if "recent port calls" in txt:
            nxt = tag.find_next_sibling()
            hops = 0
            while nxt and hops < 6 and (
                isinstance(nxt, NavigableString) or 
                (isinstance(nxt, Tag) and nxt.get_text(strip=True) == "")
            ):
                nxt = nxt.next_sibling; hops += 1
            if isinstance(nxt, Tag):
                return nxt

    # Fallback: find a block containing multiple "Arrival (UTC)"
    lab = soup.find(string=lambda s: isinstance(s, str) and "arrival (utc)" in s.lower())
    if lab:
        node = lab
        for _ in range(6):
            node = lab.parent
            if not isinstance(node, Tag): break
            labels = node.find_all(string=lambda s: isinstance(s, str) and "arrival (utc)" in s.lower())
            if len(labels) >= 2:
                return node
    return None

def _parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    root = _find_root(soup)
    results = []
    if not root:
        return results

    def block_has_labels(block):
        txt = (block.get_text(" ", strip=True) or "").lower()
        return ("arrival (utc)" in txt) or ("departure (utc)" in txt)

    blocks = [c for c in root.find_all(recursive=False) if isinstance(c, Tag)]
    for block in blocks:
        candidates = [block] + [c for c in block.find_all(recursive=False) if isinstance(c, Tag)]
        matched = next((c for c in candidates if block_has_labels(c)), None)
        if not matched:
            continue

        a = matched.find("a")
        port_name = a.get_text(strip=True) if a else "Unknown Port"
        port_link = a["href"] if (a and a.has_attr("href")) else ""

        def value_after(label_substr):
            lab = matched.find(string=lambda s: isinstance(s, str) and label_substr in s.lower())
            if not lab:
                return ""
            try:
                label_parent = lab.parent
                nxt = label_parent.find_next_sibling()
                hops = 0
                while nxt and hops < 6 and (
                    not isinstance(nxt, Tag) or nxt.get_text(strip=True) == ""
                ):
                    nxt = nxt.next_sibling; hops += 1
                if isinstance(nxt, Tag):
                    return nxt.get_text(strip=True)
            except:
                pass
            return ""

        arr = value_after("arrival (utc)")
        dep = value_after("departure (utc)")

        if arr:
            results.append({
                "event": "Arrival",
                "port": port_name,
                "when_raw": arr,
                "link": port_link,
                "detail": f"{port_name} Arrival (UTC) {arr}"
            })
        if dep:
            results.append({
                "event": "Departure",
                "port": port_name,
                "when_raw": dep,
                "link": port_link,
                "detail": f"{port_name} Departure (UTC) {dep}"
            })
    return results

def _rendered_html(url, p, mobile):
    ua = ("Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36") if mobile else \
         ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120 Safari/537.36")

    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=ua, viewport={"width": 1280, "height": 2000})
    page = ctx.new_page()
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        try: page.wait_for_selector("text=Recent Port Calls", timeout=8000)
        except: pass
        return page.content()
    finally:
        ctx.close()
        browser.close()

def _events_for_ship(p, ship):
    base_url = ship["url"]
    # Try desktop
    try:
        html = _rendered_html(base_url, p, mobile=False)
        rows = _parse(html)
        if rows: return rows, base_url
    except: pass

    # Try mobile
    try:
        parsed = urlparse(base_url)
        mobile_url = urlunparse(parsed._replace(netloc="m.vesselfinder.com"))
        html = _rendered_html(mobile_url, p, mobile=True)
        rows = _parse(html)
        if rows: return rows, mobile_url
    except: pass

    return [], base_url

def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    ships = load_json(SHIPS_PATH, [])
    state = load_json(STATE_PATH, {"seen": {}})

    all_items_new = []

    with sync_playwright() as p:
        for s in ships:
            name = s["name"]
            slug = s["slug"]
            url  = s["url"]

            print(f"[info] Fetching {name}: {url}")
            try:
                rows, used = _events_for_ship(p, s)
                print(f"[info] Parsed {name}: {len(rows)} events")
            except Exception as e:
                print(f"[error] failed parsing: {e}")
                rows = []

            # Build new items
            ship_items_new = []
            for r in rows:
                guid_src = f"{slug}|{r['event']}|{r['detail']}"
                guid = make_id(guid_src)
                if guid in state["seen"]:
                    continue

                # Build EST & local time strings
                est_str, local_str = format_times_for_notification(r["port"], r["when_raw"])

                # Choose verbs/prepositions to match your exact phrasing
                if r["event"] == "Arrival":
                    verb_part = "Arrived at"
                else:
                    verb_part = "Departed from"

                # Title exactly as requested
                if est_str and local_str:
                    title = f"{name} {verb_part} {r['port']} at {est_str}. The local time to the port is {local_str}"
                elif est_str:
                    title = f"{name} {verb_part} {r['port']} at {est_str}"
                else:
                    # No time parsed at all; fallback to generic title
                    title = f"{name} — {r['event']} — {r['port']}"

                # Description: keep UTC detail + optional local line
                base_desc = r["detail"].replace(" (UTC) -", " (UTC) (time not yet posted)")
                if est_str and local_str:
                    desc = f"{base_desc} — Local: {local_str}"
                elif est_str:
                    desc = f"{base_desc} — Local (EST): {est_str}"
                else:
                    desc = base_desc

                link  = urljoin(url, r["link"]) if r["link"] else url

                item = {
                    "title": title,
                    "description": desc,
                    "link": link,
                    "guid": guid,
                    "pubDate": to_rfc2822(datetime.utcnow())
                }

                ship_items_new.append(item)
                all_items_new.append(item)
                state["seen"][guid] = True

            # ---- PER SHIP HISTORY ----
            ship_hist = load_history(slug)
            ship_hist = merge_items(ship_hist, ship_items_new, PER_SHIP_CAP)
            save_history(slug, ship_hist)

            # Write per ship feed
            xml_ship = build_rss(f"{name} - Arrivals & Departures", url, ship_hist)
            with open(os.path.join(DOCS_DIR, f"{slug}.xml"), "w", encoding="utf-8") as f:
                f.write(xml_ship)

            # Write per ship latest
            xml_latest = build_rss(f"{name} - Latest Arrival/Departure", url, ship_hist[:1])
            with open(os.path.join(DOCS_DIR, f"{slug}-latest.xml"), "w", encoding="utf-8") as f:
                f.write(xml_latest)

    # ---- COMBINED HISTORY ----
    all_hist = load_history("all")
    all_hist = merge_items(all_hist, all_items_new, ALL_CAP)
    save_history("all", all_hist)

    xml_all = build_rss("DCL Ships - Arrivals & Departures (All)", "https://github.com/", all_hist)
    with open(os.path.join(DOCS_DIR, "all.xml"), "w", encoding="utf-8") as f:
        f.write(xml_all)

    # One latest per ship (works with both old and new title styles)
    latest_by_ship = {}
    for it in all_hist:
        # Extract ship name robustly from our title patterns
        t = it["title"]
        # Prefer split on our custom verbs; fall back to en dash
        for sep in [" Arrived", " Departed", " — "]:
            if sep in t:
                ship_name = t.split(sep, 1)[0]
                break
        else:
            ship_name = t  # worst case: whole title
        if ship_name not in latest_by_ship:
            latest_by_ship[ship_name] = it

    xml_latest_all = build_rss("DCL Ships - Latest (One per Ship)", "https://github.com/", list(latest_by_ship.values()))
    with open(os.path.join(DOCS_DIR, "latest-all.xml"), "w", encoding="utf-8") as f:
        f.write(xml_latest_all)

    save_json(STATE_PATH, state)

if __name__ == "__main__":
    main()
