# BeatBridge

Sync liked music between YouTube Music and Spotify.

The maintained flow is a two-phase process in both directions: first build a
resumable plan, then apply only the pending entries from that plan. The plan and
sync caches make interrupted runs safe to resume and avoid copying songs back to
the service they originally came from.

## Project Layout

```text
beatbridge/          Maintained Python package and CLI implementation
data/auth/           Local OAuth secrets and token caches, ignored by Git
data/cache/spotify/  Spotify search and liked-track caches, ignored by Git
data/cache/youtube/  YouTube search caches, ignored by Git
data/plans/          Resumable sync plans, ignored by Git
data/sync/           Cross-direction sync history, ignored by Git
data/exports/        CSV exports from YouTube/Spotify, ignored by Git
data/logs/           Local script logs, ignored by Git
data/archive/        Migrated old runtime files, ignored by Git
legacy/              Old all-in-one script kept for reference
scripts/             Local helper scripts/templates
web/extension/       Chrome extension launcher
web/static/          Static OAuth callback pages
main.py              Compatibility CLI wrapper
main-spot-to-yt.py   Compatibility Spotify-to-YouTube wrapper
```

## Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Copy `.example.env` to `.env` and fill in your Spotify app credentials:

```text
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080/
SPOTIFY_MATCH_SCORE_THRESHOLD=0.55
SPOTIFY_ADD_BATCH_SIZE=20
SPOTIFY_SEARCH_WORKERS=2
YOUTUBE_SEARCH_WORKERS=1
YOUTUBE_MATCH_SCORE_THRESHOLD=0.65
```

Put your Google OAuth client file at `data/auth/secrets.json`. YouTube auth
stores its local token at `data/auth/token.json`. Spotify auth stores its local
cache at `data/auth/spotify_cache`.

For Spotify local OAuth, add this exact redirect URI in the Spotify developer
dashboard:

```text
http://127.0.0.1:8080/
```

You can override local state locations in `.env`:

```text
BEATBRIDGE_DATA_DIR=data
YOUTUBE_CLIENT_SECRET_FILE=data/auth/secrets.json
YOUTUBE_TOKEN_FILE=data/auth/token.json
SPOTIFY_AUTH_CACHE_FILE=data/auth/spotify_cache
```

## Discord Notifications

Set `DISCORD_WEBHOOK_URL` in `.env` to send one compact summary when a sync or
saved-plan apply finishes:

```text
DISCORD_WEBHOOK_URL=
NOTIFY_ON_PLAN_ONLY=false
```

Auth checks do not send notifications. Plan-only runs also stay quiet by
default so scheduled `plan-only` plus `apply-plan` flows only notify once, after
the apply step.

## Commands

Validate cached auth for unattended runs:

```powershell
python main.py --check-auth --no-browser
```

Build a YouTube-to-Spotify import plan without adding anything:

```powershell
python main.py --direction yt-to-spotify --plan-only
```

Build a smaller diagnostic plan:

```powershell
python main.py --direction yt-to-spotify --limit 25 --plan-only
```

Inspect/apply the saved plan:

```powershell
python main.py --apply-plan --dry-run
python main.py --apply-plan
```

Build a Spotify-to-YouTube plan without liking anything:

```powershell
python main.py --direction spotify-to-yt --plan-only
```

Build a smaller Spotify-to-YouTube diagnostic plan:

```powershell
python main.py --direction spotify-to-yt --limit 25 --plan-only
```

Inspect/apply the Spotify-to-YouTube plan:

```powershell
python main.py --direction spotify-to-yt --apply-plan --dry-run
python main.py --direction spotify-to-yt --apply-plan
```

`main-spot-to-yt.py` is only a compatibility wrapper around:

```powershell
python main.py --direction spotify-to-yt
```

## YouTube To Spotify

The planner fetches liked YouTube videos, extracts title/artist hints, searches
Spotify, and writes `data/plans/yt_to_spotify_plan.json`.

It avoids unnecessary work by skipping:

- YouTube videos already recorded in `data/sync/yt_to_spotify_sync.json`
- YouTube videos copied from Spotify in `data/sync/spotify_to_yt_sync.json`
- duplicate title/artist candidates in the same run
- tracks already in the local liked cache
- tracks Spotify reports as already saved
- duplicate Spotify track IDs produced by different YouTube matches

Spotify search queries use multiple forms, from most specific to broad fallback:

- raw YouTube title
- `track:"Song Title" artist:"Artist Name"`
- `Song Title Artist Name`
- cleaned title
- title only

The search cache is loaded once during planning and saved once, avoiding repeated
rewrites. It lives at `data/cache/spotify/search_queries.jsonl`.

`--apply-plan` reads `data/plans/yt_to_spotify_plan.json` and adds only pending
tracks. Each successful batch updates:

- `data/plans/yt_to_spotify_plan.json`
- `data/sync/yt_to_spotify_sync.json`
- `data/cache/spotify/liked_track_ids.json`

## Spotify To YouTube

The Spotify-to-YouTube planner fetches Spotify liked songs, searches YouTube,
scores candidate videos, and writes `data/plans/spotify_to_youtube_plan.json`.

It avoids unnecessary work by skipping:

- Spotify tracks already recorded in `data/sync/spotify_to_yt_sync.json`
- Spotify tracks copied from YouTube in `data/sync/yt_to_spotify_sync.json`
- duplicate title/artist candidates in the same run
- duplicate YouTube video IDs produced by different Spotify matches

That second skip is important: a song copied from YouTube to Spotify should not
be copied straight back to YouTube later.

YouTube search queries use multiple forms:

- `Song Title Artist official audio`
- `Song Title Artist official video`
- `"Song Title" "Artist"`
- `Song Title All Artists`
- title only

`--direction spotify-to-yt --apply-plan` reads
`data/plans/spotify_to_youtube_plan.json` and likes only pending YouTube videos.
Each successful like updates:

- `data/plans/spotify_to_youtube_plan.json`
- `data/sync/spotify_to_yt_sync.json`

## Scheduled Runs

For a daily or twice-daily task, run auth preflight first and disable browser
prompts:

```powershell
python main.py --check-auth --no-browser
python main.py --direction yt-to-spotify --plan-only --no-browser
python main.py --direction yt-to-spotify --apply-plan --no-browser
python main.py --direction spotify-to-yt --plan-only --no-browser
python main.py --direction spotify-to-yt --apply-plan --no-browser
```

If `--check-auth --no-browser` fails, run the same command without
`--no-browser` once from an interactive shell to refresh OAuth tokens.

## Runtime Files

Everything under `data/auth/`, `data/cache/`, `data/plans/`, `data/sync/`,
`data/exports/`, `data/logs/`, and `data/archive/` is local runtime state and
ignored by Git. Legacy root-level runtime filenames are also ignored so older
runs do not get checked in accidentally.

Search caches are stored as JSONL, with one query per line:

```text
data/cache/spotify/search_queries.jsonl
data/cache/youtube/search_queries.jsonl
```

Each cached result is compacted to the fields the matcher actually uses. That
keeps the cache inspectable and avoids storing full API response blobs.

To migrate old cache files without losing anything, run:

```powershell
python scripts/migrate_cache_layout.py
```

The migration writes the new cache files and moves old cache files into
`data/archive/cache-layout-.../`.

## Chrome Extension

The Chrome extension is a thin local launcher. Start the Flask server:

```powershell
python web/extension/server.py
```

Then click the extension button. The server runs `python main.py` from the
project root and returns stdout/stderr to the popup.

## Legacy Code

The old all-in-one script lives at `legacy/beat-bridge.py` for reference. Use
`main.py` for maintained sync work.
