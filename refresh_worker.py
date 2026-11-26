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
