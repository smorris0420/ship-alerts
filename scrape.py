#!/usr/bin/env python3
# DCL Ship Alerts — scraper + RSS generator (GitHub Pages compatible)
# Requires: requests, beautifulsoup4
import os, re, json, hashlib, sys
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(__file__)
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
STATE_PATH = os.path.join(REPO_ROOT, "state.json")
SHIPS_PATH = os.path.join(REPO_ROOT, "ships.json")

USER_AGENT = "Mozilla/5.0 (compatible; DCL-Ship-Alerts/1.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def rss_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def make_id(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()

def find_port_calls_section(soup: BeautifulSoup):
    # Try common headings then fallback to any table containing keywords.
    keywords = ("port call", "arrivals", "departures")
    for tag in soup.find_all(["h2","h3","h4","div"]):
        t = (tag.get_text(strip=True) or "").lower()
        if any(k in t for k in keywords):
            table = tag.find_next("table")
            if table:
                return table
    for tbl in soup.find_all("table"):
        head = (tbl.get_text(" ", strip=True) or "").lower()
        if any(k in head for k in keywords):
            return tbl
    return None

def parse_port_calls(html: str):
    soup = BeautifulSoup(html, "html.parser")

    # Find the Recent Port Calls section
    header = soup.find(lambda tag: tag.name in ["h2","h3","div"]
                       and "recent port calls" in tag.get_text(strip=True).lower())

    if not header:
        return []

    # The container is just below the header
    container = header.find_next("div")

    if not container:
        return []

    rows = []

    # Each port call entry is inside a <div> with multiple sub-divs
    for entry in container.find_all("div", recursive=False):

        text = entry.get_text(" ", strip=True).lower()
        if "arrival (utc)" not in text:
            continue  # skip non-port-call rows

        # Extract port name
        port_tag = entry.find("a")
        port_name = port_tag.get_text(strip=True) if port_tag else "Unknown Port"
        port_link = port_tag["href"] if port_tag and port_tag.has_attr("href") else ""

        # Extract arrival & departure
        arrival = ""
        departure = ""

        # Arrival
        arrival_tag = entry.find(string=lambda s: s and "arrival (utc)" in s.lower())
        if arrival_tag:
            arrival_value = arrival_tag.parent.find_next("div")
            if arrival_value:
                arrival = arrival_value.get_text(strip=True)

        # Departure
        departure_tag = entry.find(string=lambda s: s and "departure" in s.lower())
        if departure_tag:
            departure_value = departure_tag.parent.find_next("div")
            if departure_value:
                departure = departure_value.get_text(strip=True)

        # Determine if this is an arrival or departure event
        if arrival:
            rows.append({
                "event": "Arrival",
                "port": port_name,
                "when_raw": arrival,
                "link": port_link,
                "detail": f"{port_name} Arrival UTC {arrival}"
            })

        if departure:
            rows.append({
                "event": "Departure",
                "port": port_name,
                "when_raw": departure,
                "link": port_link,
                "detail": f"{port_name} Departure UTC {departure}"
            })

    return rows


def to_rfc2822(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def build_rss(channel_title: str, channel_link: str, items: list) -> str:
    xml_items = []
    for it in items:
        title = rss_escape(it["title"])
        desc  = rss_escape(it.get("description",""))
        link  = rss_escape(it.get("link",""))
        guid  = rss_escape(it["guid"])
        pub   = rss_escape(it["pubDate"])
        xml_items.append(f"""
  <item>
    <title>{title}</title>
    <link>{link}</link>
    <guid isPermaLink="false">{guid}</guid>
    <pubDate>{pub}</pubDate>
    <description>{desc}</description>
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

def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    ships = load_json(SHIPS_PATH, [])
    state = load_json(STATE_PATH, {"seen": {}})
    all_items = []

    for s in ships:
        name = s["name"]
        slug = s["slug"]
        url  = s["url"]

        try:
            resp = SESSION.get(url, timeout=40)
            resp.raise_for_status()
        except Exception as e:
            print(f"[warn] fetch failed for {name}: {e}", file=sys.stderr)
            continue

        rows = parse_port_calls(resp.text)
        ship_items = []
        for r in rows:
            guid_src = f"{slug}|{r['event']}|{r['detail']}"
            guid = make_id(guid_src)
            if state["seen"].get(guid):
                continue
            pub_dt = datetime.utcnow()
            title = f"{name} — {r['event']} — {r['port'] or 'Unknown Port'}"
            desc  = r["detail"]
            link  = urljoin(url, r["link"]) if r["link"] else url
            item = {
                "title": title,
                "description": desc,
                "link": link,
                "guid": guid,
                "pubDate": to_rfc2822(pub_dt)
            }
            ship_items.append(item)
            all_items.append(item)
            state["seen"][guid] = True

        feed_xml = build_rss(f"{name} - Arrivals & Departures", url, ship_items[:50])
        with open(os.path.join(DOCS_DIR, f"{slug}.xml"), "w", encoding="utf-8") as f:
            f.write(feed_xml)

    # combined
    all_items_sorted = all_items[::-1]
    all_xml = build_rss("DCL Ships - Arrivals & Departures (All)", "https://github.com/", all_items_sorted[:100])
    with open(os.path.join(DOCS_DIR, "all.xml"), "w", encoding="utf-8") as f:
        f.write(all_xml)

    save_json(STATE_PATH, state)

if __name__ == "__main__":
    main()
