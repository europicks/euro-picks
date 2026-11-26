"""EURO PICKS free basketball ingestion worker.

Uses SportAPI.ai Free key. Polls yesterday/today/tomorrow/+2 days and ingests
box scores for finished games when the provider exposes them. Never fabricates
missing data.
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

API_KEY = os.environ.get("SPORTAPI_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_SERVICE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not all([API_KEY, SB_URL, SB_SERVICE]):
    raise SystemExit(
        "Missing SPORTAPI_KEY, SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable"
    )

API = "https://sportapi.ai/api/basketball"
HEADERS = {"X-Api-Key": API_KEY}
sb = create_client(SB_URL, SB_SERVICE)


def get(path, params=None, attempts=3):
    """GET with retries for temporary network/provider errors."""
    url = API + path
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=(10, 60),
            )
            if response.status_code == 429:
                logging.warning("SportAPI rate limit reached; stopping this run")
                raise RuntimeError("rate_limited")
            if response.status_code >= 500 and attempt < attempts:
                logging.warning(
                    "SportAPI returned HTTP %s for %s (attempt %s/%s); retrying",
                    response.status_code, path, attempt, attempts,
                )
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            data = response.json()
            if data.get("success") is False:
                raise RuntimeError(data.get("error") or "SportAPI returned success=false")
            return data
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt >= attempts:
                raise
            logging.warning(
                "Temporary SportAPI connection problem for %s (attempt %s/%s): %s",
                path, attempt, attempts, exc,
            )
            time.sleep(2 ** attempt)
    raise RuntimeError(f"SportAPI request failed after {attempts} attempts: {path}")


def _conflict_columns(conflict):
    return [part.strip() for part in conflict.split(",")]


def deduplicate_rows(rows, conflict):
    """Remove duplicate conflict keys before sending a PostgREST upsert.

    Postgres rejects one INSERT ... ON CONFLICT statement if the same target
    row appears more than once. Merge duplicate rows, preferring later
    non-null values while retaining earlier values when later data is null.
    """
    columns = _conflict_columns(conflict)
    unique = {}
    for row in rows or []:
        key = tuple(row.get(column) for column in columns)
        if any(value is None for value in key):
            logging.warning(
                "Skipping row with missing conflict key %s: %s",
                columns, row,
            )
            continue
        if key not in unique:
            unique[key] = dict(row)
        else:
            for field, value in row.items():
                if value is not None:
                    unique[key][field] = value
    removed = len(rows or []) - len(unique)
    if removed:
        logging.info(
            "Removed/merged %d duplicate rows for conflict key %s",
            removed, conflict,
        )
    return list(unique.values())


def upsert(table, rows, conflict):
    if not rows:
        return
    clean_rows = deduplicate_rows(rows, conflict)
    if clean_rows:
        logging.info(
            "Upserting %d rows into %s (received %d before deduplication)",
            len(clean_rows), table, len(rows),
        )
        sb.table(table).upsert(clean_rows, on_conflict=conflict).execute()


def main():
    leagues_data = get("/leagues").get("data", [])
    logging.info("Provider reports %d basketball competitions", len(leagues_data))

    today = datetime.now(timezone.utc).date()
    dates = [(today + timedelta(days=offset)).isoformat() for offset in (-1, 0, 1, 2)]

    games_by_id = {}
    for day in dates:
        payload = get(f"/games/date/{day}", {"tz": "Europe/Belgrade"})
        for game in payload.get("data", []) or []:
            if game.get("id") is not None:
                games_by_id[str(game["id"])] = game

    leagues_by_id = {
        str(league.get("id")): league
        for league in leagues_data
        if league.get("id") is not None
    }

    comp_rows = []
    season_rows = []
    team_rows = []
    game_rows = []

    for league in leagues_data:
        if league.get("id") is None:
            continue
        competition_id = f"sportapi:competition:{league['id']}"
        comp_rows.append({
            "id": competition_id,
            "name": league.get("name") or league.get("slug"),
            "country": league.get("country"),
            "gender": league.get("gender"),
            "level": league.get("type"),
            "source": "sportapi",
            "source_competition_id": str(league["id"]),
            "active": True,
        })

        season = league.get("current_season")
        if season:
            season_rows.append({
                "id": f"sportapi:season:{league['id']}:{season}",
                "competition_id": competition_id,
                "season_name": str(season),
                "source": "sportapi",
            })

    upsert("competitions", comp_rows, "id")
    upsert("competition_seasons", season_rows, "id")

    finished = []
    for game in games_by_id.values():
        league = game.get("league") or {}
        league_id = league.get("id")
        league_info = leagues_by_id.get(str(league_id), {})
        season = game.get("season") or league_info.get("current_season")
        season_id = (
            f"sportapi:season:{league_id}:{season}"
            if league_id is not None and season
            else None
        )

        home = game.get("home") or {}
        away = game.get("away") or {}

        for team in (home, away):
            team_id = team.get("id")
            if team_id is not None:
                team_rows.append({
                    "id": f"sportapi:team:{team_id}",
                    "name": team.get("name") or str(team_id),
                    "country": None,
                    "source": "sportapi",
                    "source_team_id": str(team_id),
                })

        game_id = game.get("id")
        game_rows.append({
            "id": f"sportapi:game:{game_id}",
            "competition_season_id": season_id,
            "start_time": game.get("start"),
            "home_team_id": (
                f"sportapi:team:{home['id']}" if home.get("id") is not None else None
            ),
            "away_team_id": (
                f"sportapi:team:{away['id']}" if away.get("id") is not None else None
            ),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "status": game.get("status"),
            "source": "sportapi",
        })

        if str(game.get("status", "")).upper() in ("FT", "AOT") and game.get("has_boxscore"):
            finished.append(game)

    upsert("teams", team_rows, "id")
    upsert("games", game_rows, "id")
    logging.info(
        "Upserted %d games; %d finished games advertise box scores",
        len(game_rows), len(finished),
    )

    player_rows = []
    box_rows = []

    for game in finished:
        payload = get(f"/games/{game['id']}/players")
        sides = payload.get("data") or {}

        for side in ("home", "away"):
            for line in sides.get(side, []) or []:
                player = line.get("player") or {}
                player_id = player.get("id")
                if player_id is None:
                    continue

                player_key = f"sportapi:player:{player_id}"
                player_rows.append({
                    "id": player_key,
                    "full_name": player.get("name") or player.get("slug") or str(player_id),
                    "source": "sportapi",
                    "source_player_id": str(player_id),
                })

                team_id = (game.get(side) or {}).get("id")
                box_rows.append({
                    "game_id": f"sportapi:game:{game['id']}",
                    "player_id": player_key,
                    "team_id": f"sportapi:team:{team_id}" if team_id is not None else None,
                    "minutes": line.get("minutes"),
                    "pts": line.get("pts"),
                    "reb": line.get("reb"),
                    "ast": line.get("ast"),
                    "threes_made": line.get("tpm"),
                    "stl": line.get("stl"),
                    "blk": line.get("blk"),
                    "tov": line.get("tov"),
                    "pir": None,
                    "source": "sportapi",
                })

    upsert("players", player_rows, "id")
    upsert("player_boxscores", box_rows, "game_id,player_id,source")
    logging.info(
        "Upserted %d players and %d player boxscore lines",
        len(player_rows), len(box_rows),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.exception("Ingestion failed: %s", error)
        sys.exit(1)
