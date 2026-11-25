"""EURO PICKS free basketball ingestion worker.
Uses SportAPI.ai Free key. Polls yesterday/today/tomorrow and ingests box scores
for finished games when the provider exposes them. Never fabricates missing data.
"""
import os, sys, logging
from datetime import datetime, timedelta, timezone
import requests
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
API_KEY=os.environ.get("SPORTAPI_KEY")
SB_URL=os.environ.get("SUPABASE_URL")
SB_SERVICE=os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not all([API_KEY, SB_URL, SB_SERVICE]):
    raise SystemExit("Missing SPORTAPI_KEY, SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable")
API="https://sportapi.ai/api/basketball"
HEADERS={"X-Api-Key":API_KEY}
sb=create_client(SB_URL, SB_SERVICE)


def get(path, params=None):
    r=requests.get(API+path, headers=HEADERS, params=params, timeout=25)
    if r.status_code == 429:
        logging.warning("SportAPI rate limit reached; stopping this run")
        raise RuntimeError("rate_limited")
    r.raise_for_status()
    data=r.json()
    if data.get("success") is False:
        raise RuntimeError(data.get("error") or "SportAPI returned success=false")
    return data


def upsert(table, rows, conflict):
    if rows:
        sb.table(table).upsert(rows, on_conflict=conflict).execute()


def main():
    leagues_data=get("/leagues").get("data", [])
    logging.info("Provider reports %d basketball competitions", len(leagues_data))
    today=datetime.now(timezone.utc).date()
    dates=[(today+timedelta(days=d)).isoformat() for d in (-1,0,1,2)]
    games_by_id={}
    for day in dates:
        payload=get(f"/games/date/{day}", {"tz":"Europe/Belgrade"})
        for game in payload.get("data", []):
            games_by_id[str(game["id"])]=game
    comp_rows=[]; season_rows=[]; team_rows=[]; game_rows=[]
    for lg in leagues_data:
        cid=f"sportapi:competition:{lg['id']}"
        comp_rows.append({"id":cid,"name":lg.get("name") or lg.get("slug"),"country":lg.get("country"),"gender":lg.get("gender"),"level":lg.get("type"),"source":"sportapi","source_competition_id":str(lg["id"]),"active":True})
        season=lg.get("current_season")
        if season:
            season_rows.append({"id":f"sportapi:season:{lg['id']}:{season}","competition_id":cid,"season_name":str(season),"source":"sportapi"})
    upsert("competitions",comp_rows,"id")
    upsert("competition_seasons",season_rows,"id")
    finished=[]
    for g in games_by_id.values():
        league=g.get("league") or {}
        league_id=league.get("id")
        lg=next((x for x in leagues_data if str(x.get("id"))==str(league_id)),{})
        season=g.get("season") or lg.get("current_season")
        season_id=f"sportapi:season:{league_id}:{season}" if season else None
        home=g.get("home") or {}; away=g.get("away") or {}
        for team in (home,away):
            if team.get("id") is not None:
                team_rows.append({"id":f"sportapi:team:{team['id']}","name":team.get("name") or str(team['id']),"country":None,"source":"sportapi","source_team_id":str(team['id'])})
        game_rows.append({"id":f"sportapi:game:{g['id']}","competition_season_id":season_id,"start_time":g.get("start"),"home_team_id":f"sportapi:team:{home['id']}" if home.get("id") is not None else None,"away_team_id":f"sportapi:team:{away['id']}" if away.get("id") is not None else None,"home_score":home.get("score"),"away_score":away.get("score"),"status":g.get("status"),"source":"sportapi"})
        if str(g.get("status","")).upper() in ("FT","AOT") and g.get("has_boxscore"):
            finished.append(g)
    upsert("teams",team_rows,"id")
    upsert("games",game_rows,"id")
    logging.info("Upserted %d games; %d finished games advertise box scores",len(game_rows),len(finished))
    player_rows=[]; box_rows=[]
    for g in finished:
        payload=get(f"/games/{g['id']}/players")
        sides=payload.get("data") or {}
        for side in ("home","away"):
            for line in sides.get(side,[]) or []:
                p=line.get("player") or {}
                if p.get("id") is None: continue
                pid=f"sportapi:player:{p['id']}"
                player_rows.append({"id":pid,"full_name":p.get("name") or p.get("slug") or str(p['id']),"source":"sportapi","source_player_id":str(p['id'])})
                game_id=f"sportapi:game:{g['id']}"
                team=(g.get(side) or {}).get("id")
                box_rows.append({"game_id":game_id,"player_id":pid,"team_id":f"sportapi:team:{team}" if team is not None else None,"minutes":line.get("minutes"),"pts":line.get("pts"),"reb":line.get("reb"),"ast":line.get("ast"),"threes_made":line.get("tpm"),"stl":line.get("stl"),"blk":line.get("blk"),"tov":line.get("tov"),"pir":None,"source":"sportapi"})
    upsert("players",player_rows,"id")
    upsert("player_boxscores",box_rows,"game_id,player_id,source")
    logging.info("Upserted %d players and %d player boxscore lines",len(player_rows),len(box_rows))

if __name__=="__main__":
    try: main()
    except Exception as e:
        logging.exception("Ingestion failed: %s",e)
        sys.exit(1)
