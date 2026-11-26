import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import BytesIO
import html

st.set_page_config(page_title="EURO PICKS", page_icon="🏀", layout="wide")

# --- EURO PICKS access control (Supabase Auth + database-backed Premium) ---
from supabase import create_client
from datetime import datetime, timezone, timedelta


def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
        return create_client(url, key)
    except Exception:
        st.error("Nedostaju Supabase podešavanja. Proveri Streamlit Settings → Secrets.")
        st.stop()


supabase = get_supabase()
ADMIN_EMAIL = "anjanikolicfakultet@gmail.com"


def current_user_client():
    client = get_supabase()
    access = st.session_state.get("sb_access_token")
    refresh = st.session_state.get("sb_refresh_token")
    if access and refresh:
        try:
            client.auth.set_session(access, refresh)
        except Exception:
            st.session_state.pop("sb_access_token", None)
            st.session_state.pop("sb_refresh_token", None)
            st.session_state.pop("sb_user", None)
            st.rerun()
    return client


def auth_screen():
    st.title("🏀 EURO PICKS")
    st.subheader("Dobro došli")
    st.write("LIGHT pristup omogućava pregled početne stranice i Premium paketa. Analitika je dostupna Premium članovima.")
    login_tab, register_tab = st.tabs(["Prijava", "Napravi nalog"])
    with login_tab:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Lozinka", type="password", key="login_password")
        if st.button("Prijavi se", type="primary", use_container_width=True):
            try:
                result = supabase.auth.sign_in_with_password({"email": email.strip(), "password": password})
                st.session_state["sb_access_token"] = result.session.access_token
                st.session_state["sb_refresh_token"] = result.session.refresh_token
                st.session_state["sb_user"] = {"id": result.user.id, "email": result.user.email}
                st.rerun()
            except Exception as e:
                st.error(f"Prijava nije uspela: {e}")
    with register_tab:
        new_email = st.text_input("Email adresa", key="register_email")
        new_password = st.text_input("Lozinka (najmanje 8 karaktera)", type="password", key="register_password")
        confirm = st.text_input("Ponovi lozinku", type="password", key="register_confirm")
        if st.button("Registruj se", use_container_width=True):
            if not new_email.strip() or len(new_password) < 8:
                st.warning("Unesi ispravnu email adresu i lozinku od najmanje 8 karaktera.")
            elif new_password != confirm:
                st.warning("Lozinke se ne podudaraju.")
            else:
                try:
                    result = supabase.auth.sign_up({"email": new_email.strip(), "password": new_password})
                    if result.session:
                        st.session_state["sb_access_token"] = result.session.access_token
                        st.session_state["sb_refresh_token"] = result.session.refresh_token
                        st.session_state["sb_user"] = {"id": result.user.id, "email": result.user.email}
                        st.rerun()
                    else:
                        st.success("Nalog je napravljen. Proveri email i potvrdi adresu, pa se prijavi.")
                except Exception as e:
                    st.error(f"Registracija nije uspela: {e}")


if not st.session_state.get("sb_access_token"):
    auth_screen()
    st.stop()

sb = current_user_client()
user = st.session_state.get("sb_user") or {}
user_email = (user.get("email") or "").lower()
user_id = user.get("id")
try:
    profile_result = sb.table("profiles").select("role,premium_until,is_blocked").eq("id", user_id).single().execute()
    profile = profile_result.data or {}
except Exception:
    profile = {}

if profile.get("is_blocked"):
    st.error("Ovaj nalog je blokiran. Kontaktiraj EURO PICKS administraciju.")
    if st.button("Odjavi se"):
        st.session_state.clear()
        st.rerun()
    st.stop()

is_admin = profile.get("role") == "admin" and user_email == ADMIN_EMAIL
premium_until = profile.get("premium_until")
try:
    is_premium = bool(premium_until and datetime.fromisoformat(premium_until.replace("Z", "+00:00")) > datetime.now(timezone.utc))
except Exception:
    is_premium = False

with st.sidebar:
    st.caption(f"Prijavljen: {user_email}")
    st.caption("ADMIN" if is_admin else ("PREMIUM" if is_premium else "LIGHT"))
    if st.button("Odjavi se", key="logout_button"):
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        for key in ["sb_access_token", "sb_refresh_token", "sb_user"]:
            st.session_state.pop(key, None)
        st.rerun()

if not is_admin and not is_premium:
    st.title("🏀 EURO PICKS")
    st.subheader("LIGHT članstvo")
    st.write("Dobro došao/la u EURO PICKS. Analitika igrača, utakmica i protivnika dostupna je Premium članovima.")
    st.markdown("### Izaberi Premium paket")
    plans = {
        "Premium – 1 mesec": 30,
        "Premium – 3 meseca": 90,
        "Premium – 12 meseci": 365,
    }
    chosen_plan = st.radio("Trajanje članstva", list(plans), horizontal=True)
    st.info("Nakon slanja zahteva dobićeš instrukcije za uplatu. Premium se aktivira tek kada administracija proveri uplatu.")
    payment_email = st.text_input("Email za kontakt", value=user_email)
    payment_note = st.text_input("Napomena (opciono)", placeholder="Npr. ime uplatioca")
    if st.button("Zatraži Premium pristup", type="primary", use_container_width=True):
        if not payment_email.strip():
            st.warning("Unesi email adresu.")
        else:
            try:
                sb.table("premium_requests").insert({
                    "user_id": user_id,
                    "email": payment_email.strip(),
                    "plan": chosen_plan,
                    "duration_days": plans[chosen_plan],
                    "note": payment_note.strip(),
                    "status": "pending",
                }).execute()
                st.success("Zahtev je poslat. Sačekaj instrukcije za uplatu i potvrdu administracije.")
            except Exception as e:
                st.error(f"Zahtev nije sačuvan. Proveri da li je SQL podešavanje završeno: {e}")
    st.markdown("---")
    st.caption("Premium paketi: 30, 90 ili 365 dana. Pristup se aktivira ručno nakon potvrde uplate.")
    st.stop()

if is_admin:
    with st.expander("⚙️ ADMIN PANEL – Premium zahtevi", expanded=True):
        st.subheader("Zahtevi za Premium")
        try:
            reqs = sb.table("premium_requests").select("id,user_id,email,plan,duration_days,note,status,created_at").order("created_at", desc=True).execute().data or []
        except Exception as e:
            reqs = []
            st.error(f"Ne mogu da učitam zahteve: {e}")
        if not reqs:
            st.info("Trenutno nema Premium zahteva.")
        for req in reqs:
            with st.container(border=True):
                st.write(f"**{req.get('email')}** · {req.get('plan')} · Status: **{req.get('status')}**")
                if req.get("note"):
                    st.caption("Napomena: " + req["note"])
                c1, c2 = st.columns(2)
                if req.get("status") == "pending":
                    if c1.button("Odobri uplatu", key=f"approve_{req['id']}", type="primary"):
                        try:
                            now = datetime.now(timezone.utc)
                            old = sb.table("profiles").select("premium_until").eq("id", req["user_id"]).single().execute().data or {}
                            old_until = old.get("premium_until")
                            try:
                                old_dt = datetime.fromisoformat(old_until.replace("Z", "+00:00")) if old_until else now
                            except Exception:
                                old_dt = now
                            start = max(now, old_dt)
                            until = start + timedelta(days=int(req["duration_days"]))
                            sb.table("profiles").update({"premium_until": until.isoformat(), "is_blocked": False}).eq("id", req["user_id"]).execute()
                            sb.table("premium_requests").update({"status": "approved", "reviewed_at": now.isoformat()}).eq("id", req["id"]).execute()
                            st.success(f"Premium aktiviran do {until.strftime('%d.%m.%Y')}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Odobravanje nije uspelo: {e}")
                    if c2.button("Odbij", key=f"reject_{req['id']}"):
                        try:
                            sb.table("premium_requests").update({"status": "rejected", "reviewed_at": datetime.now(timezone.utc).isoformat()}).eq("id", req["id"]).execute()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Odbijanje nije uspelo: {e}")
        st.markdown("#### Upravljanje korisnikom")
        target_email = st.text_input("Email korisnika za produženje ili blokadu", key="admin_target_email")
        extra_days = st.selectbox("Produži Premium za", [30, 90, 365], format_func=lambda x: {30:"30 dana",90:"90 dana",365:"365 dana"}[x])
        ac1, ac2 = st.columns(2)
        if ac1.button("Produži Premium") and target_email.strip():
            try:
                found = sb.table("profiles").select("id,premium_until").eq("email", target_email.strip().lower()).single().execute().data
                now = datetime.now(timezone.utc)
                try:
                    old_dt = datetime.fromisoformat(found["premium_until"].replace("Z", "+00:00")) if found.get("premium_until") else now
                except Exception:
                    old_dt = now
                until = max(now, old_dt) + timedelta(days=extra_days)
                sb.table("profiles").update({"premium_until": until.isoformat()}).eq("id", found["id"]).execute()
                st.success(f"Premium produžen do {until.strftime('%d.%m.%Y')}.")
                st.rerun()
            except Exception as e:
                st.error(f"Korisnik nije pronađen ili izmena nije uspela: {e}")
        if ac2.button("Blokiraj nalog") and target_email.strip():
            try:
                found = sb.table("profiles").select("id").eq("email", target_email.strip().lower()).single().execute().data
                sb.table("profiles").update({"is_blocked": True, "premium_until": None}).eq("id", found["id"]).execute()
                st.success("Nalog je blokiran.")
                st.rerun()
            except Exception as e:
                st.error(f"Korisnik nije pronađen ili izmena nije uspela: {e}")

if not is_admin and not is_premium:
    st.stop()


st.markdown("""
<style>
.stApp {background: radial-gradient(circle at 12% 0%, #14233d 0%, #080d18 48%, #070b13 100%); color:#eef4ff}
[data-testid="stHeader"] {background:rgba(7,11,19,.92)}
[data-testid="stSidebar"] {background:#0d1728; border-right:1px solid #20334e}
[data-testid="stSidebar"] * {color:#e8f0ff !important}
.stApp h1,.stApp h2,.stApp h3,.stApp h4 {color:#f4f8ff !important}
.stApp p,.stApp label,.stApp [data-testid="stCaptionContainer"] {color:#b7c6dc}
div[data-testid="stMetric"] {background:linear-gradient(145deg,#14243b,#101b2e);padding:16px;border-radius:14px;border:1px solid #263d5b;box-shadow:0 5px 18px rgba(0,0,0,.22)}
div[data-testid="stMetric"] label {color:#9fb4cf !important}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {color:#f4f8ff !important}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {color:#31e69a !important;background:#123b34;border-radius:999px;padding:3px 8px}
.stApp input,.stApp textarea,[data-baseweb="select"] > div {background:#101c2e !important;color:#f4f8ff !important;border-color:#29415f !important}
.stApp [data-baseweb="select"] * {color:#f4f8ff !important}
.stTabs [data-baseweb="tab-list"] {gap:8px;border-bottom:1px solid #263d5b}
.stTabs [data-baseweb="tab"] {background:#122139;border-radius:9px 9px 0 0;color:#c7d5e8}
.stTabs [aria-selected="true"] {background:#183b36 !important;color:#42e6a0 !important}
[data-testid="stDataFrame"] {background:#101b2e}
.stAlert {background:#122139;border:1px solid #29415f;color:#eaf2ff}
button[kind="primary"] {background:#20d995 !important;color:#07130f !important;border:0}
hr {border-color:#263d5b}

/* EURO PICKS visual identity */
.block-container {max-width: 1440px; padding-top: 1.1rem; padding-bottom: 3rem;}
.ep-topbar {display:grid;grid-template-columns:1fr 1.5fr 1fr;align-items:center;gap:12px;
background:linear-gradient(110deg,#08152f,#0c1b3a 55%,#071126);border:1px solid #233b68;
border-radius:20px;padding:17px 24px;margin:0 0 22px;box-shadow:0 12px 35px #0006}
.ep-league {font-size:13px;line-height:1.25;font-weight:900;letter-spacing:.8px;color:#eaf1ff;border-right:1px solid #29436e}
.ep-brand{text-align:center;font-size:clamp(25px,4vw,43px);font-weight:1000;font-style:italic;letter-spacing:-1.8px;color:#fff;line-height:1}
.ep-brand span{color:#21dc91}
.ep-brand small{display:block;font-size:9px;letter-spacing:3px;color:#9fb3d1;font-style:normal;margin-top:7px}
.ep-live{justify-self:end;border:1px solid #285c5a;border-radius:30px;padding:9px 15px;color:#eaf6ff;font-size:12px;font-weight:800}
.ep-live i{display:inline-block;width:9px;height:9px;background:#27e39b;border-radius:50%;margin-right:8px;box-shadow:0 0 12px #27e39b}
.ep-hero{display:grid;grid-template-columns:1.25fr .9fr;gap:20px;align-items:center;
background:radial-gradient(circle at 18% 40%,#183d82 0,#0c1d42 42%,#081126 100%);
border:1px solid #25416f;border-radius:22px;padding:28px 30px;margin:10px 0 18px;min-height:190px}
.ep-player-kicker{font-size:11px;letter-spacing:2px;color:#8faedb;font-weight:800}
.ep-player-name{font-size:clamp(30px,5vw,54px);line-height:.98;font-weight:1000;font-style:italic;letter-spacing:-1.5px;color:#fff;margin:10px 0}
.ep-player-meta{font-size:15px;color:#b8c9e4}
.ep-match{text-align:center;border-left:1px solid #29436e;padding:8px 0 8px 20px}
.ep-scoreline{display:flex;align-items:center;justify-content:center;gap:16px}
.ep-score{width:70px;height:70px;border:2px solid #47618d;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:25px;font-weight:900;color:white}
.ep-vs{color:#9bb1d2;font-weight:900}
.ep-teams{display:flex;justify-content:center;gap:20px;margin-top:10px;font-size:12px;font-weight:900;color:#eaf1ff}
.ep-date{margin-top:12px;color:#b8c9e4;font-size:13px}
.ep-stat-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 18px}
.ep-stat{background:linear-gradient(145deg,#122343,#0c172c);border:1px solid #2a4167;border-radius:15px;padding:13px 8px;text-align:center}
.ep-stat-label{font-size:12px;color:#a9bbd5;font-weight:700}
.ep-stat-value{font-size:27px;color:#fff;font-weight:950;margin-top:2px}
.ep-stat.primary{border:1.5px solid #28dc98;box-shadow:0 0 15px #1edc8c22}
.ep-panel{background:linear-gradient(145deg,#101d36,#0b1427);border:1px solid #263d63;border-radius:17px;padding:17px 19px}
.ep-panel-title{font-size:15px;font-weight:900;color:#f4f8ff;letter-spacing:.3px;margin-bottom:12px}
.ep-panel-title span{color:#28dc98;margin-right:8px}
.ep-insight{padding:9px 0;border-bottom:1px solid #263650;color:#c8d5e8;font-size:13px}
.ep-insight:last-child{border-bottom:0}
.ep-pick{display:grid;grid-template-columns:1fr auto;align-items:center;gap:20px;
background:linear-gradient(110deg,#102a5d,#0b1a3b 65%,#09152c);border:1px solid #31538d;
border-radius:20px;padding:22px 28px;margin:22px 0}
.ep-pick-label{color:#a9c1e7;font-size:11px;letter-spacing:2px;font-weight:900}
.ep-pick-main{font-size:clamp(26px,4vw,42px);font-weight:1000;font-style:italic;color:#fff;line-height:1.1}
.ep-pick-side{text-align:center;border-left:1px solid #35517f;padding-left:24px}
.ep-pick-pct{font-size:42px;font-weight:1000;color:#27dc92;line-height:1}
.ep-muted{color:#9db0cd;font-size:12px}
@media(max-width:700px){.ep-topbar{grid-template-columns:1fr;text-align:center}.ep-league{border:0}.ep-live{justify-self:center}.ep-hero{grid-template-columns:1fr;padding:20px}.ep-match{border-left:0;border-top:1px solid #29436e;padding:18px 0 0}.ep-stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ep-pick{grid-template-columns:1fr}.ep-pick-side{border-left:0;border-top:1px solid #35517f;padding:15px 0 0}}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ep-topbar">
  <div class="ep-league">TURKISH AIRLINES<br>EUROLEAGUE</div>
  <div class="ep-brand"><div>EURO <span>PICKS</span></div><small>ANALYTICS &amp; BETTING INSIGHTS</small></div>
  <div class="ep-live"><i></i> LIVE DATA</div>
</div>
""", unsafe_allow_html=True)
st.caption("EUROLEAGUE ANALYTICS • Podaci se prikazuju prema poslednjem dostupnom ažuriranju izvora.")

# --- GLOBAL PLAYER DATABASE (SportAPI.ai data ingested by GitHub Actions) ---
st.markdown("### 🌍 Globalna baza igrača i statistika")
st.caption("Podaci iz povezanih takmičenja. Baza se puni automatski preko GitHub Actions; ponude kladionica se prikazuju samo ako postoje u bazi.")
try:
    db_players = sb.table("players").select("id,full_name,source").order("full_name").limit(5000).execute().data or []
except Exception as exc:
    db_players = []
    st.info(f"Globalni katalog još nije dostupan: {exc}")
if db_players:
    player_lookup = {p["id"]: p for p in db_players}
    selected_global_id = st.selectbox("Pronađi igrača u globalnoj bazi", list(player_lookup), format_func=lambda pid: player_lookup[pid]["full_name"], key="global_player_select")
    try:
        box_rows = sb.table("player_boxscores").select("game_id,player_id,team_id,minutes,pts,reb,ast,threes_made,stl,blk,tov,pir,updated_at").eq("player_id", selected_global_id).order("updated_at", desc=True).limit(100).execute().data or []
        offers_rows = sb.table("player_prop_offers").select("market,line,bookmaker,over_odds,under_odds,captured_at,source").eq("player_id", selected_global_id).eq("is_current", True).order("captured_at", desc=True).limit(100).execute().data or []
    except Exception as exc:
        box_rows, offers_rows = [], []
        st.warning(f"Ne mogu da učitam profil igrača: {exc}")
    st.subheader(player_lookup[selected_global_id]["full_name"])
    if box_rows:
        bx = pd.DataFrame(box_rows)
        for col in ["pts","reb","ast","threes_made","stl","blk","tov","pir","minutes"]:
            if col in bx: bx[col] = pd.to_numeric(bx[col], errors="coerce")
        kcols = st.columns(5)
        for c, label, field in zip(kcols, ["PTS L10","REB L10","AST L10","3PM L10","PIR L10"], ["pts","reb","ast","threes_made","pir"]):
            c.metric(label, f"{bx[field].head(10).mean():.1f}" if bx[field].notna().any() else "—")
        st.markdown("#### Poslednji evidentirani nastupi")
        st.dataframe(bx.head(20), use_container_width=True, hide_index=True)
    else:
        st.info("Za ovog igrača još nema preuzetih box score nastupa. To nije nula statistike — podaci nisu dostupni u bazi.")
    st.markdown("#### 🎯 Granice kladionica na profilu igrača")
    if offers_rows:
        st.dataframe(pd.DataFrame(offers_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Trenutno nema potvrđenih player-prop ponuda za ovog igrača. Ne prikazujemo izmišljene granice.")
else:
    st.info("Globalna baza je prazna. Kada dodaš besplatan SportAPI ključ u GitHub Secrets i pokreneš workflow, ovde će se pojaviti igrači i utakmice iz takmičenja koja taj izvor pokriva.")

YEARS = list(range(2026, 2006, -1))
BASE = "https://675hoops.com/downloads/player_box-{}.csv.gz"
TEAM_BASE = "https://675hoops.com/downloads/team_games-{}.csv.gz"

@st.cache_data(ttl=900, show_spinner=False)
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

@st.cache_data(ttl=900, show_spinner=False)
def load_data():
    return load_seasons(YEARS)

def safe_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)

def avg(df, col):
    return float(safe_num(df[col]).mean()) if len(df) and col in df else 0.0

def fmt(x):
    return f"{x:.1f}"


def fetch_db_player_offers(player_name):
    """Fetch current offers stored in Supabase for the selected global player."""
    try:
        matches = (sb.table("players").select("id,full_name")
                   .ilike("full_name", player_name).limit(5).execute().data or [])
        ids = [row["id"] for row in matches if row.get("id")]
        if not ids:
            return pd.DataFrame(), "Igrač još nije povezan sa globalnim katalogom igrača."
        offers = (sb.table("player_prop_offers")
                  .select("market,line,bookmaker,over_odds,under_odds,captured_at,game_id,source")
                  .in_("player_id", ids).eq("is_current", True)
                  .order("captured_at", desc=True).limit(100).execute().data or [])
        return pd.DataFrame(offers), None
    except Exception as exc:
        return pd.DataFrame(), f"Ponude iz baze trenutno nisu dostupne: {exc}"


def show_upcoming_database_games():
    """Show upcoming fixtures already ingested into the global Supabase schema."""
    st.markdown("### 🗓️ Predstojeće utakmice")
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        games = (sb.table("games").select(
            "id,start_time,status,home_score,away_score,home_team_id,away_team_id,competition_season_id"
        ).gte("start_time", now_iso).order("start_time").limit(50).execute().data or [])
        if not games:
            st.info("Još nema predstojećih utakmica u globalnoj bazi. Raspored će se prikazati kada se poveže i pokrene izvor za to takmičenje.")
            return
        team_ids = list({x for g in games for x in [g.get("home_team_id"), g.get("away_team_id")] if x})
        teams = sb.table("teams").select("id,name").in_("id", team_ids).execute().data or [] if team_ids else []
        team_map = {t["id"]: t["name"] for t in teams}
        rows = []
        for g in games:
            rows.append({
                "Početak": g.get("start_time"),
                "Domaćin": team_map.get(g.get("home_team_id"), g.get("home_team_id")),
                "Gost": team_map.get(g.get("away_team_id"), g.get("away_team_id")),
                "Status": g.get("status") or "scheduled",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"Raspored iz globalne baze nije dostupan: {exc}")


# Poziv funkcije ide tek nakon njene definicije.
show_upcoming_database_games()

refresh_col1, refresh_col2 = st.columns([3, 1])
with refresh_col1:
    st.caption("Aplikacija proverava izvor na svakih 15 minuta dok se koristi. Novi podaci se pojavljuju tek kada ih izvor objavi.")
with refresh_col2:
    if st.button("🔄 Osveži podatke sada", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

COMPETITIONS = ["EuroLeague", "EuroCup", "ABA liga", "NBA", "WNBA", "NCAA", "Ostale evropske lige"]
with st.sidebar:
    st.header("🏆 Takmičenje")
    chosen_competition = st.selectbox("Izaberi ligu", COMPETITIONS, index=0)

if chosen_competition != "EuroLeague":
    st.title("🏀 EURO PICKS")
    st.subheader(chosen_competition)
    st.info(
        f"Izabrano takmičenje: {chosen_competition}. Ovaj izvor još nije povezan sa bazom rezultata. "
        "Ne prikazujemo podatke druge lige kao da pripadaju ovom takmičenju. "
        "Kada povežemo verifikovan izvor box score podataka, analitika će se automatski pojaviti ovde."
    )
    st.markdown("**Planirana podrška:** raspored, igrači, box score, forma, protivnici i istorijska analiza granica.")
    st.stop()

with st.spinner("Proveravam najnovije objavljene box score podatke..."):
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
st.caption("Provera izvora: na 15 minuta dok se aplikacija koristi. Izvor 6.75 objavljuje dnevne skupove podataka, pa završni box score ne mora biti dostupan odmah po završetku utakmice.")

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
# Season/filtered averages and recent form
last5 = player_df.head(5)
last10 = player_df.head(10)
season_stats = player_df
player_name_html = html.escape(str(chosen_player))
team_html = html.escape(str(latest["team"]))
opp_html = html.escape(str(latest["opponent"]))
date_text = latest["date"].strftime("%d.%m.%Y") if pd.notna(latest["date"]) else "Datum nije dostupan"
st.markdown(f"""
<div class="ep-hero">
  <div><div class="ep-player-kicker">PLAYER PERFORMANCE PROFILE</div>
  <div class="ep-player-name">{player_name_html}</div>
  <div class="ep-player-meta">{team_html} • {latest.get('position','EUROLEAGUE PLAYER') if pd.notna(latest.get('position','EUROLEAGUE PLAYER')) else 'EUROLEAGUE PLAYER'}</div></div>
  <div class="ep-match"><div class="ep-scoreline"><div class="ep-score">—</div><div class="ep-vs">VS</div><div class="ep-score">—</div></div>
  <div class="ep-teams"><span>{team_html}</span><span>{opp_html}</span></div>
  <div class="ep-date">◷ Poslednji evidentirani nastup: {date_text}</div></div>
</div>
""", unsafe_allow_html=True)
stat_values = [
    ("PPG", fmt(avg(season_stats, "pts")), True),
    ("RPG", fmt(avg(season_stats, "reb")), False),
    ("APG", fmt(avg(season_stats, "ast")), False),
    ("UTAKMICE", str(len(player_df)), False),
    ("3PM", fmt(avg(season_stats, "3pm")), False),
]
stats_html = "".join(f'<div class="ep-stat {"primary" if primary else ""}"><div class="ep-stat-label">{label}</div><div class="ep-stat-value">{value}</div></div>' for label,value,primary in stat_values)
st.markdown(f'<div class="ep-stat-grid">{stats_html}</div>', unsafe_allow_html=True)

st.markdown("### 📊 Forma igrača")
a, b, c, d = st.columns(4)
a.metric("Utakmice", len(player_df))
b.metric("Minuta", fmt(avg(player_df, "min")))
c.metric("FG%", fmt(100 * safe_num(player_df["fgm"]).sum() / max(1, safe_num(player_df["fga"]).sum())))
d.metric("3P%", fmt(100 * safe_num(player_df["3pm"]).sum() / max(1, safe_num(player_df["3pa"]).sum())))

tabs = st.tabs(["Pregled", "Poslednje utakmice", "Protivnici", "Odbrana protivnika"])

with tabs[0]:
    chart_stat = st.selectbox("Statistika za grafikon", ["Poeni", "Skokovi", "Asistencije", "Trojke", "PIR"], key="chart_stat")
    stat_map = {"Poeni":"pts", "Skokovi":"reb", "Asistencije":"ast", "Trojke":"3pm", "PIR":"pir"}
    chart_df = player_df.sort_values("date").copy()
    chart_recent = chart_df.tail(10).copy()
    fig = px.bar(chart_recent, x="date", y=stat_map[chart_stat],
                 title=f"{chosen_player} – {chart_stat.upper()} • POSLEDNJIH 10 UTAKMICA",
                 hover_data=["opponent", "team", "min"])
    fig.update_traces(marker_color="#2587f5", marker_line_color="#2587f5",
                      text=chart_recent[stat_map[chart_stat]], textposition="outside")
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0b1020", plot_bgcolor="#0b1020",
                      font_color="#eaf1ff", showlegend=False, margin=dict(l=10,r=10,t=55,b=10))
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



st.markdown("### 📈 Granice kladionica za ovog igrača")
st.caption("Granice se prikazuju direktno na profilu igrača. Prikazujemo samo stvarne podatke iz baze ili CSV uvoza; ne izmišljamo kvote.")
db_offers, offers_error = fetch_db_player_offers(chosen_player)
if offers_error:
    st.info(offers_error)
elif not db_offers.empty:
    st.markdown("#### Aktuelne ponude sačuvane u EURO PICKS bazi")
    db_offers = db_offers.rename(columns={
        "market":"Tržište", "line":"Granica", "bookmaker":"Kladionica",
        "over_odds":"OVER kvota", "under_odds":"UNDER kvota",
        "captured_at":"Vreme preuzimanja", "game_id":"ID utakmice", "source":"Izvor"
    })
    st.dataframe(db_offers, use_container_width=True, hide_index=True)
else:
    st.info("Za ovog igrača trenutno nema sačuvanih ponuda kladionica. Istorijska analiza granice i dalje može da se izračuna ručnim unosom linije ispod.")
with st.expander("📥 Privremeno testiraj granice iz CSV fajla", expanded=False):
    st.write("CSV kolone: player, market, line, bookmaker, over_odds, under_odds. Ovo je samo privremeni prikaz u ovoj sesiji; trajni unos zahteva ovlašćeni importer koji upisuje u Supabase.")
    odds_file = st.file_uploader("Učitaj CSV sa granicama", type=["csv"], key="bookmaker_odds_csv")
    if odds_file is not None:
        try:
            odds_df = pd.read_csv(odds_file)
            required_odds = {"player", "market", "line", "bookmaker"}
            if not required_odds.issubset(odds_df.columns):
                st.error("CSV mora sadržati: player, market, line, bookmaker.")
            else:
                odds_df["line"] = pd.to_numeric(odds_df["line"], errors="coerce")
                odds_df = odds_df.dropna(subset=["line"])
                player_odds = odds_df[odds_df["player"].astype(str).str.casefold() == str(chosen_player).casefold()].copy()
                if not player_odds.empty:
                    st.markdown("**Ponude za izabranog igrača**")
                    display_cols = [c for c in ["bookmaker", "market", "line", "over_odds", "under_odds", "updated_at"] if c in player_odds.columns]
                    st.dataframe(player_odds[display_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("U CSV fajlu nema granica za ovog igrača.")
        except Exception as exc:
            st.error(f"CSV nije moguće učitati: {exc}")
st.caption("Istorijski rezultati se porede sa svakom pojedinačnom linijom.")
prop_label = st.selectbox("Statistika za poređenje", ["Poeni", "Skokovi", "Asistencije", "Trojke", "PIR", "PTS + REB", "PTS + AST", "REB + AST", "PRA"])
combo_cols = {"PTS + REB": ("pts", "reb"), "PTS + AST": ("pts", "ast"), "REB + AST": ("reb", "ast"), "PRA": ("pts", "reb", "ast")}
if prop_label in combo_cols:
    prop_col = "_prop_combo"
    player_df[prop_col] = sum(safe_num(player_df[c]) for c in combo_cols[prop_label])
else:
    prop_col = {"Poeni":"pts", "Skokovi":"reb", "Asistencije":"ast", "Trojke":"3pm", "PIR":"pir"}[prop_label]
line = st.number_input("Granica za istorijsko poređenje", min_value=0.5, max_value=100.5, value=15.5, step=0.5)
sample_choice = st.selectbox("Period", ["Poslednjih 5", "Poslednjih 10", "Poslednjih 20", "Sve utakmice"])
sample_n = {"Poslednjih 5":5, "Poslednjih 10":10, "Poslednjih 20":20}
sample = player_df.head(sample_n[sample_choice]) if sample_choice in sample_n else player_df
over_count = int((safe_num(sample[prop_col]) > line).sum())
under_count = int((safe_num(sample[prop_col]) < line).sum())
pushes = int((safe_num(sample[prop_col]) == line).sum())
n = len(sample)
x1, x2, x3 = st.columns(3)
x1.metric("OVER – prebacio", f"{over_count}/{n}", f"{100*over_count/max(1,n):.0f}%")
x2.metric("UNDER – nije prebacio", f"{under_count}/{n}", f"{100*under_count/max(1,n):.0f}%")
x3.metric("Tačno na granici", pushes)
st.write(f"Prosek u uzorku: **{avg(sample, prop_col):.2f}** | Medijana: **{safe_num(sample[prop_col]).median():.1f}**")
st.dataframe(sample[["date", "opponent", prop_col]].rename(columns={"date":"Datum", "opponent":"Protivnik", prop_col:prop_label}), use_container_width=True, hide_index=True)

# Visual summary inspired by the supplied EURO PICKS reference.
best_side = "OVER" if over_count > under_count else "UNDER" if under_count > over_count else "NEUTRAL"
best_rate = max(over_count, under_count) / max(1, n) * 100
best_count = max(over_count, under_count)
best_line_label = "OVER" if best_side == "OVER" else "UNDER"
insight_lines = [
    f"{best_count} od {n} nastupa je na strani {best_side.lower()} granice {line:g}.",
    f"Prosek u uzorku iznosi {avg(sample, prop_col):.1f}, a medijana {safe_num(sample[prop_col]).median():.1f}.",
    f"Tačno na granici: {pushes} nastupa."
]
insights_html = "".join(f'<div class="ep-insight">✓ &nbsp;{html.escape(x)}</div>' for x in insight_lines)
st.markdown(f"""
<div class="ep-panel" style="margin-top:18px">
  <div class="ep-panel-title"><span>✦</span> KEY INSIGHTS</div>
  {insights_html}
</div>
<div class="ep-pick">
  <div><div class="ep-pick-label">{html.escape(prop_label.upper())} • ISTORIJSKI UČINAK</div>
  <div class="ep-pick-main">{html.escape(str(chosen_player).upper())} – {line:g} {html.escape(prop_label.upper())}</div>
  <div class="ep-pick-main" style="color:#25df95;font-size:clamp(32px,5vw,58px)">{best_line_label}</div>
  <div class="ep-muted">Statistički pregled uzorka, nije garancija ishoda niti automatska opklada.</div></div>
  <div class="ep-pick-side"><div class="ep-muted">PROLAZ • {html.escape(sample_choice.upper())}</div>
  <div class="ep-pick-pct">{best_rate:.0f}%</div><div class="ep-muted">{best_count}/{n} utakmica</div></div>
</div>
""", unsafe_allow_html=True)


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
