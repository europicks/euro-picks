"""EURO PICKS: safe one-call DNP probe; reads Supabase, never writes to it."""
import os
import sys
import requests
from supabase import create_client

API = "https://sportapi.ai/api/basketball"

def main():
    api_key = os.environ.get("SPORTAPI_KEY")
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not all([api_key, sb_url, sb_key]):
        raise SystemExit("Missing SPORTAPI_KEY, SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    sb = create_client(sb_url, sb_key)
    rows = (
        sb.table("games")
        .select("id,start_time,status")
        .in_("status", ["FT", "AOT"])
        .order("start_time", desc=True)
        .limit(30)
        .execute().data or []
    )
    game = next((r for r in rows if str(r.get("id", "")).startswith("sportapi:game:")), None)
    if not game:
        raise SystemExit("No finished SportAPI game found in Supabase.")

    game_id = game["id"].split("sportapi:game:", 1)[1]
    print(f"Checking {game['id']} | {game.get('start_time')}")
    print("SportAPI requests used: 1")
    response = requests.get(
        f"{API}/games/{game_id}/players",
        headers={"X-Api-Key": api_key},
        timeout=(10, 45),
    )
    if response.status_code == 429:
        raise SystemExit("SportAPI HTTP 429: quota reached; no retry was attempted.")
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is False:
        raise SystemExit(payload.get("error") or "SportAPI success=false")

    sides = payload.get("data") or {}
    total = dnp_total = 0
    for side in ("home", "away"):
        lines = sides.get(side) or []
        print(f"\n{side.upper()}: {len(lines)} player rows")
        for line in lines:
            total += 1
            reason = line.get("dnp")
            if reason:
                dnp_total += 1
                player = line.get("player") or {}
                name = player.get("name") or player.get("slug") or player.get("id")
                print(f"  DNP | {name} | reason: {reason}")
    print(f"\nTOTAL: {total} player rows; DNP rows: {dnp_total}")
    if dnp_total:
        print("RESULT: DNP data returned. Supabase was not changed.")
    else:
        print("RESULT: This game has no DNP rows; test another game before concluding.")
    print("Supabase database was not modified.")

if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print(f"HTTP/connection error: {exc}", file=sys.stderr)
        sys.exit(1)
