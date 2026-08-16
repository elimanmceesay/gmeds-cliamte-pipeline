# Climate-Macro Monitor — weekly automation

Adds a self-updating layer on top of the dashboard you already have.

## What updates itself weekly, automatically
- **Disaster reports** — count of new Gambia-tagged ReliefWeb reports in the trailing 7 days, plus each report dropped into a review queue
- **Macro indicators** — debt/GDP, GDP growth, current account (World Bank API — annual data, re-checked weekly for revisions)
- **CBG policy rate & inflation** — same scrape approach as the FX monitor's pipeline

## What stays human-reviewed, on purpose
"New climate dynamics and policies" — a new World Bank report, a government announcement, an IMF review outcome — get surfaced as **alerts** in the dashboard's Overview tab with a link, not auto-written into your headline stats. A person reads it, and if it actually changes something, updates it via Data Management. This is the difference between a dashboard your central bank can trust and one that quietly drifts wrong.

## Setup (10 minutes, one time)

1. **Add the automation tables.** In the same Supabase project as before: SQL Editor → paste `supabase-setup-automation.sql` → Run.

2. **Get a service_role key.** Supabase → Settings → API → copy the **service_role** key (different from the anon key you used in the HTML file — this one has write access and must never appear in a public HTML file, only in GitHub's secrets).

3. **Put this folder in a GitHub repo** (or add it to the same repo as the FX pipeline).

4. **Add two repo secrets**: Settings → Secrets and variables → Actions →
   - `SUPABASE_URL` — your project URL
   - `SUPABASE_SERVICE_KEY` — the service_role key from step 2

5. **Enable the workflow.** `.github/workflows/weekly-climate-fetch.yml` runs every Monday at 08:00 UTC automatically once it's in the repo — no further setup. You can also trigger it manually from the Actions tab any time (`workflow_dispatch`).

## Test it locally first
```bash
pip install requests beautifulsoup4 --break-system-packages
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_KEY="..."
python scraper_climate.py
```
You should see it print what it found, then check the Supabase table editor for new rows in `climate_readings` and `climate_alerts`.

## Fragility notes
- ReliefWeb's API is public and documented (reliefweb.int/help/api) but the query shape can change; if `reports` comes back empty when you'd expect results, check their docs against the `payload` dict in `fetch_reliefweb_gambia()`.
- The CBG scrape reuses the same regex approach as the FX pipeline — same caveat: it reads homepage text, not a stable API, so a site redesign will break it loudly (the script raises rather than writing garbage).
- World Bank indicators are annual and revise slowly — don't expect weekly movement here, this mainly catches data revisions.
