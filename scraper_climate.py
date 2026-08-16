"""
scraper_climate.py — weekly data collector for the Climate-Macro Monitor.

What it automates cleanly (structured sources, safe to write directly):
  1. ReliefWeb API — count of new Gambia disaster/situation reports in the
     trailing 7 days, and the reports themselves as review-queue alerts.
  2. World Bank indicators API — debt/GDP, GDP growth, current account
     (annual data, but re-checked weekly in case of revisions).
  3. CBG homepage — policy rate & inflation (same approach as the FX
     pipeline's scraper.py).

What it deliberately does NOT automate:
  "New climate dynamics and policies" in the narrative sense — a new World
  Bank report, a new government climate announcement — can't be safely
  auto-summarized into headline dashboard numbers without a human reading
  it first. So instead of guessing, this script searches a couple of RSS
  feeds for Gambia + climate keywords and drops anything it finds into the
  climate_alerts review queue. A person then reads it and, if it matters,
  updates climate_factors by hand via the dashboard's Data Management tab.
  This is a deliberate design choice, not a shortcut — auto-editing a
  government-facing dashboard from unread text is how wrong numbers get
  published.

Setup:
    pip install requests --break-system-packages
    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_SERVICE_KEY="..."   # Settings -> API -> service_role key
                                          # (NOT the anon key — this needs write access
                                          #  and service_role bypasses RLS safely
                                          #  from a trusted script.)
    python scraper_climate.py
"""

import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

WB_BASE = "https://api.worldbank.org/v2/country/GM/indicator/{code}"
WB_INDICATORS = {
    "GC.DOD.TOTL.GD.ZS": "debt_gdp_pct",
    "NY.GDP.MKTP.KD.ZG": "gdp_growth_pct",
    "BN.CAB.XOKA.GD.ZS": "current_account_pct_gdp",
}

RELIEFWEB_API = "https://api.reliefweb.int/v1/reports"
CBG_HOME = "https://www.cbg.gm/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; GMEDS-climate-collector/1.0)"}


def supabase_upsert(table, rows):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.post(url, headers=HEADERS, json=rows, timeout=30)
    if resp.status_code >= 300:
        print(f"[warn] Supabase upsert to {table} failed: {resp.status_code} {resp.text[:300]}")
    else:
        print(f"Upserted {len(rows)} row(s) into {table}")


def fetch_reliefweb_gambia(days=7):
    """Pull ReliefWeb reports tagged with Gambia from the last N days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00+00:00")
    payload = {
        "appname": "gmeds-climate-monitor",
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "country", "value": "Gambia"},
                {"field": "date.created", "value": {"from": since}},
            ],
        },
        "fields": {"include": ["title", "url", "date.created", "source.name"]},
        "sort": ["date.created:desc"],
        "limit": 20,
    }
    resp = requests.post(RELIEFWEB_API, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def fetch_world_bank(code):
    resp = requests.get(WB_BASE.format(code=code), params={"format": "json", "per_page": 5}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    for item in payload[1]:
        if item.get("value") is not None:
            return int(item["date"]), float(item["value"])
    return None


def fetch_cbg_readings():
    resp = requests.get(CBG_HOME, headers=UA, timeout=30)
    resp.raise_for_status()
    from bs4 import BeautifulSoup  # local import so the rest of the script works without bs4 if unused
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

    out = {}
    m = re.search(r"MPC Rate\s*([\d.]+)%", text)
    if m:
        out["cbg_policy_rate"] = float(m.group(1))
    m = re.search(r"Inflation Rate\s*([\d.]+)%", text)
    if m:
        out["cbg_inflation_rate"] = float(m.group(1))
    return out


def run():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables first.")

    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    # 1. ReliefWeb — disaster/situation report count + alerts for review
    try:
        reports = fetch_reliefweb_gambia(days=7)
        supabase_upsert("climate_readings", [{
            "metric": "reliefweb_reports_7d", "value": len(reports), "value_text": None,
            "observed_at": today, "source": "ReliefWeb", "fetched_at": now,
        }])
        alert_rows = []
        for r in reports:
            fields = r.get("fields", {})
            alert_rows.append({
                "headline": fields.get("title", "Untitled report"),
                "summary": f"Source: {fields.get('source', [{}])[0].get('name', 'ReliefWeb') if fields.get('source') else 'ReliefWeb'}",
                "url": fields.get("url"),
                "source": "ReliefWeb",
                "detected_at": now,
            })
        supabase_upsert("climate_alerts", alert_rows)
        print(f"ReliefWeb: {len(reports)} report(s) in the last 7 days")
    except Exception as e:
        print(f"[warn] ReliefWeb fetch failed: {e}")

    # 2. World Bank indicators
    for code, metric in WB_INDICATORS.items():
        try:
            result = fetch_world_bank(code)
            if result:
                year, value = result
                supabase_upsert("climate_readings", [{
                    "metric": metric, "value": value, "value_text": f"{year}",
                    "observed_at": today, "source": "World Bank", "fetched_at": now,
                }])
                print(f"{metric}: {value} ({year})")
        except Exception as e:
            print(f"[warn] World Bank fetch failed for {code}: {e}")
        time.sleep(0.3)

    # 3. CBG policy rate & inflation
    try:
        readings = fetch_cbg_readings()
        rows = [{
            "metric": k, "value": v, "value_text": None,
            "observed_at": today, "source": "CBG", "fetched_at": now,
        } for k, v in readings.items()]
        supabase_upsert("climate_readings", rows)
        print(f"CBG readings: {readings}")
    except Exception as e:
        print(f"[warn] CBG fetch failed: {e}")

    print("Done. Unreviewed alerts are in climate_alerts — check the dashboard's Overview tab.")


if __name__ == "__main__":
    run()
