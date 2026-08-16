# SARS Vehicle Logbook

A SARS-compliant business vehicle mileage logbook, delivered as an
installable PWA (progressive web app). Log trips with your phone's own
GPS, classify each one as business or private, and export a
SARS-eLogbook-style report (print-to-PDF, or Excel) for the current tax
year or any custom date range.

Single-user, single-vehicle by design. Runs as its own fully separate
Docker stack — no dependency on any other app on the host.

## Why not just pull my Google Maps Timeline history?

Google deprecated third-party access to Location History/Timeline — since
a 2024 privacy change, that data lives **on-device only**, not in your
Google account, so there's nothing for a server-side API to fetch. The
only official export path left is Google Takeout (manual or scheduled),
not a live API.

So this app captures trips directly from your phone's own GPS instead
(the same approach real mileage-logbook apps use), and uses the **Google
Maps Platform Geocoding API** server-side just to turn a trip's start/end
coordinates into a readable address — a narrower, but real, use of
"Google Maps API access."

There's also a second, proof-of-concept way in: **Import from Google
Timeline** (`/import/google-timeline`) reads the on-device `Timeline.json`
export the Google Maps app itself can produce (Android: Settings →
Location → Location services → Timeline → Export Timeline data; iPhone:
Google Maps → profile → Settings → Location & privacy → Export Timeline
data). Since Google's own Maps app has real OS-granted background-location
permission — something a PWA can never get — it already tracks your
movement all day with zero manual button presses, which is exactly the
low-friction behavior a genuinely automatic version of this app would
need. This import path is how that gets tested: upload the file (monthly,
or whenever), and any driving segment it finds becomes a trip waiting to
be classified, same as one captured via Start/End Trip. Re-uploading an
overlapping export never creates duplicates (each segment gets a stable
id derived from its own start/end time). **Caveat, called out again in
`app/timeline_import.py`'s own docstring**: Google's current export
format ("semanticSegments") is real and confirmed via research, but the
exact field names inside a *driving* segment specifically weren't
verifiable against a real sample file while building this — the import
summary reports exactly what it could and couldn't parse, so the first
real upload is the actual test of whether that guess holds.

If this proves the concept out, the natural next step (a genuinely
low-friction, always-on version) needs a **real native app** with OS
background-location permission and motion/activity detection to
auto-detect drives with no manual step at all — a separate fork from this
PWA/Takeout-testing codebase, not a change to this one.

## How trip capture works

- Tap **Start Trip** — GPS tracking runs only while a trip is open (no
  background tracking, which sidesteps iOS Safari's well-known background
  geolocation limitations entirely, and matches how SARS actually wants
  deliberate trip records rather than passive full-time tracking).
- Tap **End Trip** — distance is computed from the recorded GPS track
  (server-side, with a jitter/accuracy filter so GPS drift while
  stationary doesn't inflate distance).
- Classify the trip as Business or Private, add a purpose/destination
  note. A repeat trip between the same two places is suggested
  automatically from your last matching trip.
- Works offline: a trip started or ended without a connection is queued
  in the browser (IndexedDB) and synced automatically on the next app
  load, or via the "Sync offline trips" button on the dashboard.

SARS wants literal odometer readings; the phone can only reliably give
GPS-derived distance. `app/export_sars.py`'s `compute_odometer_ledger()`
reconciles the two: it runs a computed odometer forward from your
tax-year opening reading through every trip's GPS distance, but if you
ever type in a *real* odometer reading on a trip (optional, in the
"Enter real odometer reading" section when classifying, or later when
editing a trip), that real value re-anchors the running total from that
point forward. Never entering one still gives you a fully GPS-derived
logbook — a widely accepted proxy — that gets more precise the more real
readings you add.

## Setup

### 1. First-time deploy

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD and APP_SECRET_KEY to real random values
bash deploy.sh
docker exec -it sars-logbook-web python -m scripts.set_password
```

Then open `http://<your-server>:8090`, log in, and go to **Settings** to
set up your vehicle (registration, tax year start date, opening
odometer).

### 2. Google Maps Geocoding API (optional but recommended)

Trip addresses are a nice-to-have — SARS only requires the
odometer/km/purpose, which work fine with no API key at all. To also get
readable addresses on each trip:

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com).
2. Enable the **Geocoding API** (Maps Platform → APIs & Services).
3. Create an API key, and **restrict it** to your server's public IP
   address (Credentials → your key → Application restrictions → IP
   addresses). Google requires billing enabled on the project even though
   usage at this single-vehicle scale will be a few cents at most.
4. Set `GOOGLE_MAPS_API_KEY` in `.env`, then `bash deploy.sh` again.

### 3. Making it reachable at a real hostname

`deploy.sh` binds the app to `localhost:8090` on the host (configurable
via `HOST_PORT` in `.env`) but does **not** wire up any public routing —
that needs to be done manually on the host:

- **If you already run a Cloudflare Tunnel** for another app on this box,
  the simplest option is adding a second **public hostname** to that same
  tunnel (Cloudflare Zero Trust dashboard → Networks → Tunnels → your
  tunnel → Public Hostname → Add), pointing it at
  `http://localhost:8090` (or whatever `HOST_PORT` you chose).
- Otherwise, run a second `cloudflared` container with its own tunnel
  token, the same way the tunnel is set up for the existing app on this
  host — see that app's own `deploy.sh` for the exact `docker run`
  invocation to mirror.

## Local development / verification

```bash
docker compose -f docker-compose.dev.yml up --build
```

This is a **dev-only** compose file (the real deploy path is `deploy.sh`,
matching this project's own convention of plain `docker build`/`docker
run`, no compose, since Unraid doesn't ship docker-compose by default).

Running tests locally (needs `DATABASE_URL` pointing at a real, empty
Postgres — the dev compose file's own DB on `localhost:55432` works):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql://sars_logbook:devpassword@localhost:55432/sars_logbook pytest
```

## What's verified vs. not

Verified in this repo's own test suite / local Docker build: the
haversine + GPS jitter-filtering distance logic, the odometer
reconciliation/re-anchoring logic, the full trip-capture API round trip
(start → points → end → classify), the offline-sync upsert-by-UUID
idempotency, the repeat-trip suggestion matching, and that the HTML and
Excel export outputs reconcile arithmetically against each other.

**Not verifiable without a real deployment** — worth checking once this
is actually running on a real phone:
- Real phone GPS accuracy/behavior (iOS Safari vs. Android Chrome).
- The real Google Geocoding API integration (needs a real, billed key).
- The real "Add to Home Screen" install flow and iOS-specific PWA
  rendering quirks.
- Real offline behavior — killing the network mid-trip on an actual
  phone, confirming the IndexedDB queue survives closing/reopening the
  app, confirming "Sync now" recovers it.
- The Cloudflare Tunnel routing to a real public hostname.

## A note on SARS compliance

The exported logbook's column layout (opening/closing odometer per trip,
business/private km, purpose) is built from published SARS guidance
(the SA Revenue Service's own travel e-logbook requirements: opening/
closing odometer for the tax year, per-trip date/odometer-or-km/purpose,
a separate logbook per vehicle if more than one is used). **Cross-check
the exported report's exact column wording against the current-year
official SARS eLogbook template** (downloadable from sars.gov.za) before
relying on it for a real tax submission — this repo's format was built
from secondary sources describing that template, not a line-by-line copy
of the official PDF itself.
