"""EURO PICKS SportAPI worker: EuroLeague only, low-request polling.

Runs once daily around midnight Belgrade time. Existing player box scores are not fetched again.
No data is fabricated; unavailable box scores are simply skipped and retried on the next daily run.
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
API_KEY = os.environ.get("SPORTAPI_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_SERVICE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not all([API_KEY, SB_URL, SB_SERVICE]):
    raise SystemExit("Missing SPORTAPI_KEY, SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

API = "https://sportapi.ai/api/basketball"
HEADERS = {"X-Api-Key": API_KEY}
sb = create_client(SB_URL, SB_SERVICE)


def get(path, params=None, attempts=2):
    """Make a request, retrying only transient connection/5xx errors."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(API + path, headers=HEADERS, params=params, timeout=(10, 45))
            if response.status_code == 429:
                raise RuntimeError("SportAPI rate limit (429); stopping this run")
            if response.status_code >= 500 and attempt < attempts:
                logging.warning("HTTP %s on %s; retrying once", response.status_code, path)
                time.sleep(2)
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("success") is False:
                raise RuntimeError(payload.get("error") or "SportAPI success=false")
            return payload
        except (requests.Timeout, requests.ConnectionError):
            if attempt == attempts:
                raise
            time.sleep(2)
    raise RuntimeError(f"Request failed: {path}")


def deduplicate(rows, conflict):
    columns = [part.strip() for part in conflict.split(",")]
    unique = {}
    for row in rows or []:
        key = tuple(row.get(col) for col in columns)
        if any(value is None for value in key):
            continue
        if key not in unique:
            unique[key] = dict(row)
        else:
            unique[key].update({k: v for k, v in row.items() if v is not None})
    if len(unique) < len(rows or []):
        logging.info("Merged %d duplicate rows for %s", len(rows) - len(unique), conflict)
    return list(unique.values())


def upsert(table, rows, conflict="id"):
    rows = deduplicate(rows, conflict)
    if rows:
        sb.table(table).upsert(rows, on_conflict=conflict).execute()
        logging.info("Upserted %d rows into %s", len(rows), table)


def is_euroleague(league):
    """Match the named EuroLeague competition, not other basketball leagues."""
    name = str((league or {}).get("name") or (league or {}).get("slug") or "").strip().lower()
    return name in {"euroleague", "euro league", "turkish airlines euroleague"} or name.startswith("euroleague ")


def already_has_boxscore(game_id):
    """Avoid repeating the expensive per-game players endpoint once rows exist."""
    result = (sb.table("player_boxscores").select("player_id")
              .eq("game_id", f"sportapi:game:{game_id}").limit(1).execute())
    return bool(result.data)


def main():
    # One competitions request per daily run; only EuroLeague is ingested.
    leagues = get("/leagues").get("data", []) or []
    euro_leagues = [league for league in leagues if is_euroleague(league)]
    euro_ids = {str(league.get("id")) for league in euro_leagues if league.get("id") is not None}
    if not euro_ids:
        logging.warning("SportAPI did not return a recognisable EuroLeague competition; no games ingested")
        logging.info("Available competition names: %s", [x.get("name") for x in leagues])
        return
    logging.info("EuroLeague competitions selected: %s", [x.get("name") for x in euro_leagues])

    today = datetime.now(ZoneInfo("Europe/Belgrade")).date()
    dates = [(today + timedelta(days=offset)).isoformat() for offset in (-1, 0, 1, 2)]
    games_by_id = {}
    # Four date requests per daily run, shared endpoint filtered locally to EuroLeague.
    for day in dates:
        data = get(f"/games/date/{day}", {"tz": "Europe/Belgrade"}).get("data", []) or []
        for game in data:
            league_id = str(((game.get("league") or {}).get("id")))
            if league_id in euro_ids and game.get("id") is not None:
                games_by_id[str(game["id"])] = game

    season_by_league = {str(x.get("id")): x.get("current_season") for x in euro_leagues}
    competition_rows, season_rows, team_rows, game_rows = [], [], [], []
    for league in euro_leagues:
        lid = str(league["id"])
        cid = f"sportapi:competition:{lid}"
        competition_rows.append({
            "id": cid, "name": league.get("name") or league.get("slug"),
            "country": league.get("country"), "gender": league.get("gender"),
            "level": league.get("type"), "source": "sportapi",
            "source_competition_id": lid, "active": True,
        })
        season = league.get("current_season")
        if season:
            season_rows.append({
                "id": f"sportapi:season:{lid}:{season}", "competition_id": cid,
                "season_name": str(season), "source": "sportapi",
            })

    finished = []
    for game in games_by_id.values():
        league = game.get("league") or {}
        lid = str(league.get("id"))
        season = game.get("season") or season_by_league.get(lid)
        season_id = f"sportapi:season:{lid}:{season}" if season else None
        home, away = game.get("home") or {}, game.get("away") or {}
        for team in (home, away):
            if team.get("id") is not None:
                team_rows.append({
                    "id": f"sportapi:team:{team['id']}",
                    "name": team.get("name") or str(team["id"]),
                    "country": None, "source": "sportapi", "source_team_id": str(team["id"]),
                })
        game_rows.append({
            "id": f"sportapi:game:{game['id']}", "competition_season_id": season_id,
            "start_time": game.get("start"),
            "home_team_id": f"sportapi:team:{home['id']}" if home.get("id") is not None else None,
            "away_team_id": f"sportapi:team:{away['id']}" if away.get("id") is not None else None,
            "home_score": home.get("score"), "away_score": away.get("score"),
            "status": game.get("status"), "source": "sportapi",
        })
        if str(game.get("status", "")).upper() in ("FT", "AOT") and game.get("has_boxscore"):
            finished.append(game)

    upsert("competitions", competition_rows)
    upsert("competition_seasons", season_rows)
    upsert("teams", team_rows)
    upsert("games", game_rows)
    logging.info("EuroLeague: %d games; %d finished games advertise box scores", len(game_rows), len(finished))

    player_rows, box_rows = [], []
    fetched_games = 0
    skipped_games = 0
    for game in finished:
        if already_has_boxscore(game["id"]):
            skipped_games += 1
            continue
        payload = get(f"/games/{game['id']}/players")
        sides = payload.get("data") or {}
        game_has_lines = False
        for side in ("home", "away"):
            for line in sides.get(side, []) or []:
                player = line.get("player") or {}
                pid = player.get("id")
                if pid is None:
                    continue
                player_key = f"sportapi:player:{pid}"
                player_rows.append({
                    "id": player_key,
                    "full_name": player.get("name") or player.get("slug") or str(pid),
                    "source": "sportapi", "source_player_id": str(pid),
                })
                team_id = (game.get(side) or {}).get("id")
                box_rows.append({
                    "game_id": f"sportapi:game:{game['id']}", "player_id": player_key,
                    "team_id": f"sportapi:team:{team_id}" if team_id is not None else None,
                    "minutes": line.get("minutes"), "pts": line.get("pts"),
                    "reb": line.get("reb"), "ast": line.get("ast"),
                    "threes_made": line.get("tpm"), "stl": line.get("stl"),
                    "blk": line.get("blk"), "tov": line.get("tov"),
                    "pir": None, "source": "sportapi",
                })
                game_has_lines = True
        if game_has_lines:
            fetched_games += 1
        else:
            logging.warning("No player lines returned for game %s; it may be retried tomorrow", game["id"])

    upsert("players", player_rows)
    upsert("player_boxscores", box_rows, "game_id,player_id,source")
    logging.info("Fetched boxscore endpoints for %d games; skipped %d already stored games", fetched_games, skipped_games)
    logging.info("Upserted %d players and %d player boxscore lines", len(deduplicate(player_rows, "id")), len(deduplicate(box_rows, "game_id,player_id,source")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Ingestion failed: %s", exc)
        sys.exit(1)
