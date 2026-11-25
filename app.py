import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import BytesIO

st.set_page_config(page_title="EURO PICKS", page_icon="🏀", layout="wide")

st.markdown("""
<style>
.stApp {background:#f4f7fb;color:#172033}
[data-testid="stHeader"] {background:rgba(244,247,251,.96)}
[data-testid="stSidebar"] {background:#e8eef7}
[data-testid="stSidebar"] * {color:#172033 !important}
h1,h2,h3,h4,p,label,span,div {color:inherit}
.stApp h1,.stApp h2,.stApp h3,.stApp h4 {color:#14213d !important}
.stApp p,.stApp label,.stApp [data-testid="stCaptionContainer"] {color:#334155}
div[data-testid="stMetric"] {background:#ffffff;padding:14px;border-radius:12px;border:1px solid #d6deea;box-shadow:0 2px 8px rgba(20,33,61,.06)}
div[data-testid="stMetric"] label,
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    color:#172033 !important;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    background:#e8edf5 !important;
    border:1px solid #cbd5e1 !important;
    border-radius:999px !important;
    padding:4px 9px !important;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
    fill:#334155 !important;
}
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {
    background:#ffffff !important;
    color:#172033 !important;
    border-color:#cbd5e1 !important;
}
.stApp input::placeholder, .stApp textarea::placeholder {
    color:#64748b !important;
}
.stApp [data-baseweb="select"] * {
    color:#172033 !important;
}
.stTabs [data-baseweb="tab-list"] {gap:8px}
.stTabs [data-baseweb="tab"] {background:#e7edf6;border-radius:8px;color:#172033}
.stTabs [aria-selected="true"] {background:#cbdcf2 !important;color:#102a43 !important}
[data-testid="stDataFrame"] {background:#fff}
.stAlert {background:#fff;border:1px solid #d6deea}
</style>
""", unsafe_allow_html=True)

st.title("🏀 EURO PICKS")
st.caption("Basketball player analytics • EuroLeague historical box scores")

YEARS = list(range(2026, 2006, -1))
BASE = "https://675hoops.com/downloads/player_box-{}.csv.gz"
TEAM_BASE = "https://675hoops.com/downloads/team_games-{}.csv.gz"

@st.cache_data(ttl=3600, show_spinner=False)
def load_seasons(years):
    frames, team_frames, errors = [], [], []
    for year in years:
        try:
            r = requests.get(BASE.format(year), timeout=25)
            r.raise_for_status()
            df = pd.read_csv(BytesIO(r.content), compression="gzip")
            if not df.empty:
                frames.append(df)
        except Exception as e:
            errors.append(f"Player box {year}: {e}")
        try:
            tr = requests.get(TEAM_BASE.format(year), timeout=25)
            tr.raise_for_status()
            tdf = pd.read_csv(BytesIO(tr.content), compression="gzip")
            if not tdf.empty:
                team_frames.append(tdf)
        except Exception as e:
            errors.append(f"Team games {year}: {e}")
    if not frames:
        raise RuntimeError("Nijedna sezona igrača nije mogla da se preuzme. Proveri internet konekciju.")
    data = pd.concat(frames, ignore_index=True)
    team_data = pd.concat(team_frames, ignore_index=True) if team_frames else pd.DataFrame()
    return data, team_data, errors

@st.cache_data(ttl=3600, show_spinner=False)
def load_data():
    return load_seasons(YEARS)

def safe_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)

def avg(df, col):
    return float(safe_num(df[col]).mean()) if len(df) and col in df else 0.0

def fmt(x):
    return f"{x:.1f}"

with st.spinner("Preuzimam istorijske box score podatke..."):
    try:
        all_data, team_data, load_errors = load_data()
    except Exception as e:
        st.error(str(e))
        st.stop()

required = ["season", "season_label", "date", "team", "opponent", "venue",
            "player_id", "player", "sec", "pts", "fg2m", "fg2a", "fg3m",
            "fg3a", "ftm", "fta", "oreb", "dreb", "ast", "stl", "tov",
            "blk", "pir"]
missing = [c for c in required if c not in all_data.columns]
if missing:
    st.error("Podaci nemaju očekivane kolone: " + ", ".join(missing))
    st.stop()

for c in ["season", "sec", "pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm",
          "fta", "oreb", "dreb", "ast", "stl", "tov", "blk", "pir"]:
    all_data[c] = safe_num(all_data[c])
all_data["date"] = pd.to_datetime(all_data["date"], errors="coerce")
all_data["min"] = all_data["sec"] / 60
all_data["reb"] = all_data["oreb"] + all_data["dreb"]
all_data["fgm"] = all_data["fg2m"] + all_data["fg3m"]
all_data["fga"] = all_data["fg2a"] + all_data["fg3a"]
all_data["3pm"] = all_data["fg3m"]
all_data["3pa"] = all_data["fg3a"]
all_data["season_label"] = all_data["season_label"].fillna(all_data["season"].astype(int).astype(str))
all_data = all_data.dropna(subset=["date", "player"])
all_data = all_data.sort_values("date", ascending=False)

if not team_data.empty:
    team_data["date"] = pd.to_datetime(team_data["date"], errors="coerce")
    team_numeric = ["season", "poss", "pts", "fg2m", "fg2a", "fg3m", "fg3a",
                    "ftm", "fta", "oreb", "dreb", "ast", "stl", "tov", "blk",
                    "blka", "pf", "fd", "pir"]
    for c in team_numeric:
        if c in team_data.columns:
            team_data[c] = safe_num(team_data[c])
    team_data = team_data.dropna(subset=["date", "team", "opponent"])

st.success(f"Podaci učitani: {len(all_data):,} nastupa • {all_data['player'].nunique():,} igrača • {all_data['season_label'].nunique()} sezona")

with st.sidebar:
    st.header("🔎 Filteri")
    seasons = sorted(all_data["season_label"].dropna().unique(), reverse=True)
    chosen_season = st.selectbox("Sezona", ["Sve sezone"] + seasons, index=1 if seasons else 0)
    season_df = all_data if chosen_season == "Sve sezone" else all_data[all_data["season_label"] == chosen_season]

    teams = sorted(season_df["team"].dropna().unique())
    chosen_team = st.selectbox("Tim", ["Svi timovi"] + teams)
    team_df = season_df if chosen_team == "Svi timovi" else season_df[season_df["team"] == chosen_team]

    players = sorted(team_df["player"].dropna().unique())
    if not players:
        st.warning("Nema igrača za izabrane filtere.")
        st.stop()
    chosen_player = st.selectbox("Igrač", players)
    venue_filter = st.selectbox("Domaćin/gost", ["Sve", "home", "away", "neutral"])

player_df = team_df[team_df["player"] == chosen_player].copy()
if venue_filter != "Sve":
    player_df = player_df[player_df["venue"].str.lower() == venue_filter]
player_df = player_df.sort_values("date", ascending=False)

if player_df.empty:
    st.warning("Nema utakmica za ovu kombinaciju filtera.")
    st.stop()

latest = player_df.iloc[0]
st.subheader(f"{chosen_player}")
st.caption(f"Tim u izabranom filteru: {latest['team']} • Poslednja utakmica: {latest['date'].date()} • Protiv: {latest['opponent']}")

# Season/filtered averages and recent form
last5 = player_df.head(5)
last10 = player_df.head(10)
season_stats = player_df

metric_cols = st.columns(5)
for col, label, key in zip(metric_cols, ["PTS", "REB", "AST", "3PM", "PIR"],
                           ["pts", "reb", "ast", "3pm", "pir"]):
    col.metric(label, fmt(avg(season_stats, key)), f"L5 {fmt(avg(last5,key))} | L10 {fmt(avg(last10,key))}")

st.markdown("### 📊 Forma igrača")
a, b, c, d = st.columns(4)
a.metric("Utakmice", len(player_df))
b.metric("Minuta", fmt(avg(player_df, "min")))
c.metric("FG%", fmt(100 * safe_num(player_df["fgm"]).sum() / max(1, safe_num(player_df["fga"]).sum())))
d.metric("3P%", fmt(100 * safe_num(player_df["3pm"]).sum() / max(1, safe_num(player_df["3pa"]).sum())))

tabs = st.tabs(["Pregled", "Poslednje utakmice", "Protivnici", "Odbrana protivnika", "Granice / prop analiza"])

with tabs[0]:
    chart_stat = st.selectbox("Statistika za grafikon", ["Poeni", "Skokovi", "Asistencije", "Trojke", "PIR"], key="chart_stat")
    stat_map = {"Poeni":"pts", "Skokovi":"reb", "Asistencije":"ast", "Trojke":"3pm", "PIR":"pir"}
    chart_df = player_df.sort_values("date").copy()
    fig = px.line(chart_df, x="date", y=stat_map[chart_stat], markers=True,
                  title=f"{chosen_player} – {chart_stat} po utakmicama",
                  hover_data=["opponent", "team", "min"])
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0b1020", plot_bgcolor="#0b1020")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Prosek po lokaciji")
    venue_table = player_df.groupby("venue").agg(
        utakmice=("player", "count"), PTS=("pts", "mean"), REB=("reb", "mean"),
        AST=("ast", "mean"), **{"3PM": ("3pm", "mean"), "PIR": ("pir", "mean")}
    ).round(2)
    st.dataframe(venue_table, use_container_width=True)

with tabs[1]:
    show = player_df.head(20).copy()
    show["Datum"] = show["date"].dt.strftime("%d.%m.%Y")
    show["Min"] = show["min"].round(1)
    st.dataframe(show[["Datum","team","opponent","venue","Min","pts","reb","ast","3pm","3pa","stl","tov","blk","pir"]]
                 .rename(columns={"team":"Tim","opponent":"Protivnik","venue":"Lokacija","pts":"PTS",
                                  "reb":"REB","ast":"AST","3pm":"3PM","3pa":"3PA","stl":"STL",
                                  "tov":"TOV","blk":"BLK","pir":"PIR"}),
                 use_container_width=True, hide_index=True)

with tabs[2]:
    opp_stats = player_df.groupby("opponent").agg(
        utakmice=("player","count"), PTS=("pts","mean"), REB=("reb","mean"),
        AST=("ast","mean"), **{"3PM": ("3pm", "mean"), "PIR": ("pir", "mean")}
    ).round(2).sort_values("utakmice", ascending=False)
    st.dataframe(opp_stats, use_container_width=True)
    opp_options = sorted(player_df["opponent"].dropna().unique())
    selected_opp = st.selectbox("Detaljna istorija protiv tima", opp_options)
    vs = player_df[player_df["opponent"] == selected_opp]
    st.write(f"**{chosen_player} protiv {selected_opp}:** {len(vs)} utakmica")
    st.dataframe(vs[["date","pts","reb","ast","3pm","pir","min"]].rename(
        columns={"date":"Datum","pts":"PTS","reb":"REB","ast":"AST","3pm":"3PM","pir":"PIR","min":"Min"}),
        use_container_width=True, hide_index=True)


with tabs[3]:
    st.subheader("🛡️ Šta protivnik dozvoljava")
    st.caption(
        "Analiza je zasnovana na stvarnim timskim box-score podacima. "
        "Pokazuje šta protivnik dozvoljava u proseku; ne tvrdi da zna da li igra čoveka, zonu, switch ili drop."
    )
    if team_data.empty:
        st.warning("Timski box-score podaci nisu dostupni za ovu sezonu.")
    else:
        defense_teams = sorted(team_data["team"].dropna().unique())
        current_opp = str(latest["opponent"])
        default_idx = defense_teams.index(current_opp) if current_opp in defense_teams else 0
        defense_team = st.selectbox("Izaberi protivničku ekipu", defense_teams, index=default_idx)

        # Defensive team's row identifies the opponent; opponent's row in the same game
        # supplies the actual production allowed by that defense.
        defensive_rows = team_data[team_data["team"] == defense_team].copy()
        allowed_cols = ["pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta",
                        "oreb", "dreb", "ast", "tov", "pir"]
        scoring_rows = team_data[["game_id", "team"] + allowed_cols].copy()
        scoring_rows = scoring_rows.rename(columns={"team": "scoring_team"})
        defense_games = defensive_rows.merge(
            scoring_rows,
            left_on=["game_id", "opponent"],
            right_on=["game_id", "scoring_team"],
            suffixes=("_def", "_allowed"),
            how="inner"
        ).sort_values("date", ascending=False)

        if defense_games.empty:
            st.info("Nema dovoljno zajedničkih utakmica za izračun odbrane ove ekipe.")
        else:
            recent_n = st.selectbox("Period odbrane", ["Poslednjih 5", "Poslednjih 10", "Cela sezona"], index=1)
            if recent_n == "Poslednjih 5":
                defense_sample = defense_games.head(5)
            elif recent_n == "Poslednjih 10":
                defense_sample = defense_games.head(10)
            else:
                season_num = int(latest["season"])
                defense_sample = defense_games[defense_games["season"] == season_num]

            if defense_sample.empty:
                defense_sample = defense_games.head(10)

            games_n = len(defense_sample)
            allowed = {
                "PTS": "pts_allowed", "2PM": "fg2m_allowed", "2PA": "fg2a_allowed",
                "3PM": "fg3m_allowed", "3PA": "fg3a_allowed", "FTM": "ftm_allowed",
                "FTA": "fta_allowed", "REB": None, "AST": "ast_allowed",
                "TOV": "tov_allowed", "PIR": "pir_allowed"
            }
            defense_sample["reb_allowed"] = defense_sample["oreb_allowed"] + defense_sample["dreb_allowed"]
            defense_sample["fg_pct_allowed"] = (
                (defense_sample["fg2m_allowed"] + defense_sample["fg3m_allowed"]) /
                (defense_sample["fg2a_allowed"] + defense_sample["fg3a_allowed"]).replace(0, pd.NA) * 100
            )
            defense_sample["3p_pct_allowed"] = (
                defense_sample["fg3m_allowed"] /
                defense_sample["fg3a_allowed"].replace(0, pd.NA) * 100
            )
            defense_sample["3pa_rate_allowed"] = (
                defense_sample["fg3a_allowed"] /
                (defense_sample["fg2a_allowed"] + defense_sample["fg3a_allowed"]).replace(0, pd.NA) * 100
            )

            stat_cards = [
                ("Poeni dozvoljeni", "pts_allowed"),
                ("Skokovi dozvoljeni", "reb_allowed"),
                ("Asistencije dozvoljene", "ast_allowed"),
                ("Trojke dozvoljene", "fg3m_allowed"),
                ("Izgubljene lopte rivala", "tov_allowed"),
            ]
            cards = st.columns(5)
            for card, (label, colname) in zip(cards, stat_cards):
                card.metric(label, f"{defense_sample[colname].mean():.1f}")

            st.markdown("#### Šuterski učinak protivnika")
            shot_cols = st.columns(3)
            shot_cols[0].metric("FG% dozvoljen", f"{defense_sample['fg_pct_allowed'].mean():.1f}%")
            shot_cols[1].metric("3P% dozvoljen", f"{defense_sample['3p_pct_allowed'].mean():.1f}%")
            shot_cols[2].metric("Udeo pokušaja za 3", f"{defense_sample['3pa_rate_allowed'].mean():.1f}%")

            st.markdown("#### Profil odbrane — merljivi pokazatelji")
            league_base = team_data[team_data["season"] == int(defense_sample["season"].iloc[0])].copy()
            league_base = league_base.merge(
                league_base[["game_id", "team"] + allowed_cols].rename(columns={"team":"scoring_team"}),
                left_on=["game_id", "opponent"], right_on=["game_id", "scoring_team"],
                suffixes=("_def", "_allowed")
            )
            league_base["reb_allowed"] = league_base["oreb_allowed"] + league_base["dreb_allowed"]
            comparisons = [
                ("Poeni dozvoljeni", "pts_allowed"),
                ("Skokovi dozvoljeni", "reb_allowed"),
                ("Asistencije dozvoljene", "ast_allowed"),
                ("Trojke dozvoljene", "fg3m_allowed"),
                ("FG% dozvoljen", None),
                ("Udeo pokušaja za 3", None),
            ]
            league_base["fg_pct_allowed"] = (
                (league_base["fg2m_allowed"] + league_base["fg3m_allowed"]) /
                (league_base["fg2a_allowed"] + league_base["fg3a_allowed"]).replace(0, pd.NA) * 100
            )
            league_base["3pa_rate_allowed"] = (
                league_base["fg3a_allowed"] /
                (league_base["fg2a_allowed"] + league_base["fg3a_allowed"]).replace(0, pd.NA) * 100
            )
            compare_cols = [
                ("Poeni dozvoljeni", "pts_allowed"),
                ("Skokovi dozvoljeni", "reb_allowed"),
                ("Asistencije dozvoljene", "ast_allowed"),
                ("Trojke dozvoljene", "fg3m_allowed"),
                ("FG% dozvoljen", "fg_pct_allowed"),
                ("Udeo pokušaja za 3", "3pa_rate_allowed"),
            ]
            rows = []
            for label, metric in compare_cols:
                team_value = float(defense_sample[metric].mean())
                league_value = float(league_base[metric].mean())
                diff = team_value - league_value
                if diff > 0.05:
                    interpretation = "Dozvoljava više od proseka"
                elif diff < -0.05:
                    interpretation = "Dozvoljava manje od proseka"
                else:
                    interpretation = "Oko proseka lige"
                rows.append({"Pokazatelj": label, "Protivnik": round(team_value, 2),
                             "Prosek lige": round(league_value, 2), "Tumačenje": interpretation})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.markdown("#### Kakvu odbranu pokazuju brojke?")
            style_notes = []
            pts_diff = defense_sample["pts_allowed"].mean() - league_base["pts_allowed"].mean()
            reb_diff = defense_sample["reb_allowed"].mean() - league_base["reb_allowed"].mean()
            ast_diff = defense_sample["ast_allowed"].mean() - league_base["ast_allowed"].mean()
            three_rate_diff = defense_sample["3pa_rate_allowed"].mean() - league_base["3pa_rate_allowed"].mean()
            fg_diff = defense_sample["fg_pct_allowed"].mean() - league_base["fg_pct_allowed"].mean()

            if pts_diff <= -2:
                style_notes.append("Čvrsta odbrana po broju primljenih poena.")
            elif pts_diff >= 2:
                style_notes.append("Rivalima dopušta iznadprosečan broj poena.")
            if three_rate_diff >= 3:
                style_notes.append("Protivnici protiv nje uzimaju veći udeo šuteva za tri — spolja im ostavlja više pokušaja.")
            elif three_rate_diff <= -3:
                style_notes.append("Protivnici uzimaju manji udeo šuteva za tri — ograničava volumen šuta spolja.")
            if fg_diff <= -2:
                style_notes.append("Snižava procenat šuta protivnika; pokazatelj otežanih pokušaja, ne dokaz konkretne šeme.")
            elif fg_diff >= 2:
                style_notes.append("Protivnici protiv nje šutiraju efikasnije od proseka lige.")
            if reb_diff >= 1.5:
                style_notes.append("Dopušta više skokova protivniku, što može ukazivati na problem u zatvaranju skoka.")
            elif reb_diff <= -1.5:
                style_notes.append("Dobro ograničava protivnički skok.")
            if ast_diff <= -1.0:
                style_notes.append("Protivnici beleže manje asistencija — moguće otežava kreiranje otvorenih šuteva.")
            elif ast_diff >= 1.0:
                style_notes.append("Protivnici beleže više asistencija — češće dolaze do timskog protoka lopte.")
            if not style_notes:
                style_notes.append("Brojke su blizu proseka lige; nema izrazitog statističkog odstupanja u ovom uzorku.")
            for note in style_notes:
                st.write("• " + note)

            st.caption(
                f"Uzorak: {games_n} utakmica. Ovo opisuje rezultate odbrane (šta dozvoljava), "
                "ali box score ne otkriva pouzdano taktičku šemu kao što su zona 2-3, switch, drop ili blitz."
            )


with tabs[4]:
    st.caption("Ovo su istorijske frekvencije, ne garantovana prognoza. Linija se poredi sa stvarnim rezultatima u izabranom uzorku.")
    prop_label = st.selectbox("Tržište", ["Poeni","Skokovi","Asistencije","Trojke","PIR"])
    prop_col = {"Poeni":"pts","Skokovi":"reb","Asistencije":"ast","Trojke":"3pm","PIR":"pir"}[prop_label]
    line = st.number_input("Granica", min_value=0.5, max_value=100.5, value=15.5, step=0.5)
    sample_choice = st.selectbox("Uzorak", ["Poslednjih 5","Poslednjih 10","Sve utakmice"])
    sample = player_df.head(5 if sample_choice=="Poslednjih 5" else 10) if sample_choice!="Sve utakmice" else player_df
    over_count = int((safe_num(sample[prop_col]) > line).sum())
    under_count = int((safe_num(sample[prop_col]) < line).sum())
    pushes = int((safe_num(sample[prop_col]) == line).sum())
    n = len(sample)
    x1, x2, x3 = st.columns(3)
    x1.metric("Over", f"{over_count}/{n}", f"{100*over_count/max(1,n):.0f}%")
    x2.metric("Under", f"{under_count}/{n}", f"{100*under_count/max(1,n):.0f}%")
    x3.metric("Jednako", pushes)
    st.write(f"Prosek u uzorku: **{avg(sample,prop_col):.2f}** | Medijana: **{safe_num(sample[prop_col]).median():.1f}**")
    st.dataframe(sample[["date","opponent",prop_col]].rename(
        columns={"date":"Datum","opponent":"Protivnik",prop_col:prop_label}),
        use_container_width=True, hide_index=True)



st.markdown("---")
st.header("🧠 EURO PICKS MODEL — igrači koji nedostaju")
st.write(
    "Ovaj modul pravi sopstvenu procenu za igrača kog nema u bazi. "
    "Unesi njegove proseke iz prethodne lige ili ranijeg perioda; model ih prilagođava "
    "očekivanoj minutaži i nivou takmičenja. Ako nemaš statistiku, prikazuje samo grubi "
    "ligaški reper i jasno označava nisku pouzdanost."
)

with st.expander("Otvori procenu igrača koji nedostaje", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        missing_name = st.text_input("Ime igrača", value="Novi igrač")
        missing_position = st.selectbox("Pozicija", ["PG", "SG", "SF", "PF", "C"], key="missing_pos")
    with c2:
        expected_minutes = st.slider("Očekivana minutaža", 5, 40, 24)
        source_level = st.selectbox(
            "Liga iz koje dolaze proseci",
            ["EuroLeague", "EuroCup", "ABA", "Ostala evropska liga", "NBA", "Nema prethodnih podataka"],
            key="source_level"
        )
    with c3:
        target_level = st.selectbox(
            "Takmičenje u kom prognoziramo", ["EuroLeague", "EuroCup", "ABA"],
            key="target_level"
        )
        role = st.selectbox(
            "Uloga", ["Starter / glavna opcija", "Starter / sporedna opcija",
                      "Klupa / rotacija", "Klupa / ograničena uloga"]
        )

    st.caption("Unesi proseke po utakmici iz prethodne lige. Ako ih nemaš, ostavi nule.")
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        input_pts = st.number_input("PTS prosek", 0.0, 60.0, 0.0, 0.5)
    with s2:
        input_reb = st.number_input("REB prosek", 0.0, 30.0, 0.0, 0.5)
    with s3:
        input_ast = st.number_input("AST prosek", 0.0, 25.0, 0.0, 0.5)
    with s4:
        input_3pm = st.number_input("3PM prosek", 0.0, 15.0, 0.0, 0.5)
    with s5:
        input_pir = st.number_input("PIR prosek", 0.0, 80.0, 0.0, 0.5)

    d1, d2 = st.columns(2)
    with d1:
        source_games = st.number_input("Broj utakmica u uzorku", 0, 100, 0, 1)
    with d2:
        source_minutes = st.number_input("Prosečna minutaža u izvornoj ligi", 1.0, 40.0, 25.0, 0.5)

    league_factor = {
        "EuroLeague": 1.00, "EuroCup": 0.94, "ABA": 0.90,
        "Ostala evropska liga": 0.86, "NBA": 0.92,
        "Nema prethodnih podataka": 1.00,
    }
    target_factor = {"EuroLeague": 1.00, "EuroCup": 0.94, "ABA": 0.90}
    role_factor = {
        "Starter / glavna opcija": 1.08,
        "Starter / sporedna opcija": 1.00,
        "Klupa / rotacija": 0.90,
        "Klupa / ograničena uloga": 0.78,
    }
    level_adjustment = target_factor[target_level] / league_factor[source_level]
    role_adjustment = role_factor[role]
    minutes_adjustment = expected_minutes / source_minutes

    reference = {}
    for stat in ["pts", "reb", "ast", "3pm", "pir"]:
        eligible = all_data[all_data["min"] >= 5]
        per30 = safe_num(eligible[stat]) / eligible["min"] * 30
        reference[stat] = float(per30.mean()) if len(per30) else 0.0

    input_stats = {"pts": input_pts, "reb": input_reb, "ast": input_ast,
                   "3pm": input_3pm, "pir": input_pir}
    have_history = any(v > 0 for v in input_stats.values())

    if st.button("Izračunaj procenu igrača", type="primary", key="estimate_missing"):
        estimates = {}
        for stat, supplied in input_stats.items():
            prior_per30 = reference[stat]
            if have_history and supplied > 0:
                source_per30 = supplied / source_minutes * 30
                sample_weight = min(0.85, source_games / (source_games + 8.0)) if source_games > 0 else 0.50
                adjusted_per30 = sample_weight * source_per30 + (1.0 - sample_weight) * prior_per30
            else:
                adjusted_per30 = prior_per30
            estimates[stat] = max(
                0.0, adjusted_per30 * (expected_minutes / 30.0) *
                level_adjustment * role_adjustment
            )

        confidence = "NISKA"
        if have_history and source_games >= 15:
            confidence = "SREDNJA"
        elif have_history and source_games >= 5:
            confidence = "NISKA–SREDNJA"

        st.subheader(f"Procena: {missing_name}")
        st.caption(f"{missing_position} • {target_level} • {expected_minutes} očekivanih minuta • Pouzdanost: {confidence}")
        mcols = st.columns(5)
        for col, label, stat in zip(mcols, ["PTS", "REB", "AST", "3PM", "PIR"],
                                    ["pts", "reb", "ast", "3pm", "pir"]):
            col.metric(label, f"{estimates[stat]:.1f}")

        if not have_history:
            st.warning(
                "Nema unetih statistika igrača. Ovo je samo opšti reper iz trenutno učitane baze, "
                "ne individualna prognoza. Ne koristimo poziciju kao da znamo stvarni učinak."
            )
        else:
            st.info(
                "Procena koristi unete proseke, minutažu, broj utakmica i početne korekcije "
                "takmičenja i uloge. Korekcije liga su privremene pretpostavke, a ne zvanični "
                "koeficijenti niti model istreniran na ABA/EuroCup podacima."
            )
        st.write(
            f"**Pretpostavke:** korekcija takmičenja {level_adjustment:.2f}× · "
            f"korekcija uloge {role_adjustment:.2f}× · minutaža {minutes_adjustment:.2f}×"
        )
        st.caption(
            "Procena nije stvarna statistika niti garancija ishoda. Za sledeću iteraciju treba "
            "dodati stvarne box score podatke iz ABA/EuroCup i testirati prognoze na ranijim utakmicama."
        )


if load_errors:
    with st.expander("Upozorenja pri preuzimanju sezona"):
        st.write("\n".join(load_errors))
