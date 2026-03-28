import streamlit as st
import json
import os
import time
import requests
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="IPL Fantasy 2026", page_icon="🏏", layout="wide")

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = st.secrets.get("CRICKET_API_KEY", "")
DATA_FILE = Path("data/teams.json")
DATA_FILE.parent.mkdir(exist_ok=True)

MATCH = {
    "t1": {"id": "RCB", "name": "Royal Challengers Bengaluru", "color": "#C41E3A"},
    "t2": {"id": "SRH", "name": "Sunrisers Hyderabad",          "color": "#F26522"},
}

PLAYERS = [
    # RCB
    {"id":"r1",  "name":"Virat Kohli",       "role":"BAT",  "team":"RCB", "credits":11.0},
    {"id":"r2",  "name":"Rajat Patidar",      "role":"BAT",  "team":"RCB", "credits":9.5},
    {"id":"r3",  "name":"Phil Salt",          "role":"WK",   "team":"RCB", "credits":9.5},
    {"id":"r4",  "name":"Devdutt Padikkal",   "role":"BAT",  "team":"RCB", "credits":8.5},
    {"id":"r5",  "name":"Tim David",          "role":"BAT",  "team":"RCB", "credits":8.5},
    {"id":"r6",  "name":"Krunal Pandya",      "role":"AR",   "team":"RCB", "credits":9.0},
    {"id":"r7",  "name":"Romario Shepherd",   "role":"AR",   "team":"RCB", "credits":8.0},
    {"id":"r8",  "name":"Josh Hazlewood",     "role":"BOWL", "team":"RCB", "credits":9.0},
    {"id":"r9",  "name":"Yash Dayal",         "role":"BOWL", "team":"RCB", "credits":7.5},
    {"id":"r10", "name":"Bhuvneshwar Kumar",  "role":"BOWL", "team":"RCB", "credits":8.0},
    {"id":"r11", "name":"Suyash Sharma",      "role":"BOWL", "team":"RCB", "credits":7.0},
    # SRH
    {"id":"s1",  "name":"Travis Head",        "role":"BAT",  "team":"SRH", "credits":10.5},
    {"id":"s2",  "name":"Abhishek Sharma",    "role":"BAT",  "team":"SRH", "credits":9.5},
    {"id":"s3",  "name":"Ishan Kishan",       "role":"WK",   "team":"SRH", "credits":9.5},
    {"id":"s4",  "name":"Heinrich Klaasen",   "role":"WK",   "team":"SRH", "credits":9.0},
    {"id":"s5",  "name":"Nitish Kumar Reddy", "role":"AR",   "team":"SRH", "credits":9.0},
    {"id":"s6",  "name":"Liam Livingstone",   "role":"AR",   "team":"SRH", "credits":8.5},
    {"id":"s7",  "name":"Harshal Patel",      "role":"BOWL", "team":"SRH", "credits":8.5},
    {"id":"s8",  "name":"Jaydev Unadkat",     "role":"BOWL", "team":"SRH", "credits":7.5},
    {"id":"s9",  "name":"Harsh Dubey",        "role":"BOWL", "team":"SRH", "credits":7.5},
    {"id":"s10", "name":"Zeeshan Ansari",     "role":"BOWL", "team":"SRH", "credits":7.0},
    {"id":"s11", "name":"Kamindu Mendis",     "role":"BAT",  "team":"SRH", "credits":8.0},
]

ROLE_LIMITS = {"WK": (1, 4), "BAT": (3, 6), "AR": (1, 4), "BOWL": (3, 6)}
MAX_CREDITS = 100.0
MAX_PER_TEAM = 7
TEAM_SIZE = 11

# Teams are revealed automatically at this time (IST = UTC+5:30)
REVEAL_HOUR_IST   = 19   # 7 PM
REVEAL_MINUTE_IST = 30   # :30 → 7:30 PM IST

POINTS_SYSTEM = {
    "run": 1, "boundary_bonus": 1, "six_bonus": 2,
    "half_century": 8, "century": 16, "duck": -2,
    "wicket": 25, "three_wicket": 4, "five_wicket": 8,
    "maiden": 4, "catch": 8, "runout": 12, "stumping": 12,
}

# ── Data persistence ─────────────────────────────────────────────────────────
def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except:
            pass
    return {"users": {}, "teams": {}, "match_live": False, "scores": {}}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

def is_past_reveal_time():
    """Returns True if current IST time is 7:30 PM or later."""
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    return (now.hour, now.minute) >= (REVEAL_HOUR_IST, REVEAL_MINUTE_IST)

# ── Live score API ────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def fetch_live_score():
    if not API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.cricapi.com/v1/currentMatches",
            params={"apikey": API_KEY, "offset": 0},
            timeout=8,
        )
        data = r.json()
        if data.get("status") != "success":
            return None
        for match in data.get("data", []):
            name = match.get("name", "")
            if "RCB" in name and "SRH" in name:
                return match
        return None
    except:
        return None

@st.cache_data(ttl=120)
def fetch_player_stats(match_id):
    if not API_KEY or not match_id:
        return {}
    try:
        r = requests.get(
            "https://api.cricapi.com/v1/match_scorecard",
            params={"apikey": API_KEY, "id": match_id},
            timeout=8,
        )
        data = r.json()
        if data.get("status") != "success":
            return {}
        return parse_scorecard(data.get("data", {}))
    except:
        return {}

def parse_scorecard(scorecard):
    stats = {}
    for innings in scorecard.get("scorecard", []):
        for batter in innings.get("batting", []):
            name = batter.get("batsman", {}).get("name", "")
            if not name:
                continue
            pts = 0
            runs = batter.get("r", 0) or 0
            fours = batter.get("4s", 0) or 0
            sixes = batter.get("6s", 0) or 0
            pts += runs * POINTS_SYSTEM["run"]
            pts += fours * POINTS_SYSTEM["boundary_bonus"]
            pts += sixes * POINTS_SYSTEM["six_bonus"]
            if runs >= 100:
                pts += POINTS_SYSTEM["century"]
            elif runs >= 50:
                pts += POINTS_SYSTEM["half_century"]
            if runs == 0 and batter.get("dismissal", ""):
                pts += POINTS_SYSTEM["duck"]
            stats[name] = stats.get(name, 0) + pts

        for bowler in innings.get("bowling", []):
            name = bowler.get("bowler", {}).get("name", "")
            if not name:
                continue
            pts = 0
            wickets = bowler.get("w", 0) or 0
            maidens = bowler.get("m", 0) or 0
            pts += wickets * POINTS_SYSTEM["wicket"]
            pts += maidens * POINTS_SYSTEM["maiden"]
            if wickets >= 5:
                pts += POINTS_SYSTEM["five_wicket"]
            elif wickets >= 3:
                pts += POINTS_SYSTEM["three_wicket"]
            stats[name] = stats.get(name, 0) + pts

        for fielder in innings.get("fielding", []):
            name = fielder.get("fielder", {}).get("name", "")
            if not name:
                continue
            pts = 0
            pts += (fielder.get("catches", 0) or 0) * POINTS_SYSTEM["catch"]
            pts += (fielder.get("runouts", 0) or 0) * POINTS_SYSTEM["runout"]
            pts += (fielder.get("stumpings", 0) or 0) * POINTS_SYSTEM["stumping"]
            stats[name] = stats.get(name, 0) + pts

    return stats

def calc_fantasy_points(team_entry, player_stats):
    total = 0
    for pid in team_entry["players"]:
        p = next((x for x in PLAYERS if x["id"] == pid), None)
        if not p:
            continue
        raw = player_stats.get(p["name"], 0)
        if pid == team_entry["captain"]:
            raw *= 2
        elif pid == team_entry["vice_captain"]:
            raw *= 1.5
        total += raw
    return round(total, 1)

# ── UI helpers ────────────────────────────────────────────────────────────────
def player_by_id(pid):
    return next((p for p in PLAYERS if p["id"] == pid), None)

def role_color(role):
    return {"WK": "🧤", "BAT": "🏏", "AR": "⭐", "BOWL": "🎳"}.get(role, "")

def team_badge(team):
    colors = {"RCB": "🔴", "SRH": "🟠"}
    return colors.get(team, "")

# ════════════════════════════════════════════════════════════════════════════
#  PAGES
# ════════════════════════════════════════════════════════════════════════════

def page_home():
    st.markdown("## 🏏 IPL Fantasy 2026")
    st.markdown(f"### {MATCH['t1']['name']} vs {MATCH['t2']['name']}")
    st.markdown("No login needed — just enter your name and build your team!")

    data = load_data()

    name = st.text_input("Your name (unique, no changes after submit)", max_chars=20, placeholder="e.g. Rahul07")

    if st.button("Continue →", type="primary"):
        name = name.strip()
        if not name:
            st.error("Please enter a name.")
            return
        if len(name) < 2:
            st.error("Name must be at least 2 characters.")
            return
        key = name.lower()
        # Name taken by someone else
        if key in data["users"] and data["users"][key] != name:
            st.error("❌ This name is taken. Try another.")
            return
        # Register name — also add a placeholder leaderboard entry immediately
        if key not in data["users"]:
            data["users"][key] = name
            # Add to leaderboard right away (no team yet)
            if key not in data["teams"]:
                data["teams"][key] = {
                    "user": name,
                    "players": [],
                    "captain": None,
                    "vice_captain": None,
                    "submitted_at": None,
                    "team_complete": False,
                }
            save_data(data)
        st.session_state["username"] = name
        if key in data["teams"] and data["teams"][key].get("team_complete", False):
            st.session_state["page"] = "success"
        else:
            st.session_state["page"] = "builder"
        st.rerun()

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Leaderboard"):
            st.session_state["page"] = "leaderboard"
            st.rerun()
    with col2:
        submitted = len(data["teams"])
        st.metric("Teams submitted", submitted)


def page_builder():
    username = st.session_state.get("username", "")
    if not username:
        st.session_state["page"] = "home"
        st.rerun()

    data = load_data()
    st.markdown(f"## Build your team — {username}")

    # Init session picks
    if "picks" not in st.session_state:
        st.session_state.picks = []
    if "captain" not in st.session_state:
        st.session_state.captain = None
    if "vice_captain" not in st.session_state:
        st.session_state.vice_captain = None

    picks = st.session_state.picks
    captain = st.session_state.captain
    vc = st.session_state.vice_captain

    used_credits = sum(p["credits"] for p in PLAYERS if p["id"] in picks)
    remaining = MAX_CREDITS - used_credits
    rcb_count = sum(1 for pid in picks if player_by_id(pid) and player_by_id(pid)["team"] == "RCB")
    srh_count = len(picks) - rcb_count

    # Stats bar
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Selected", f"{len(picks)}/11")
    c2.metric("Credits left", f"{remaining:.1f}")
    c3.metric("RCB", rcb_count)
    c4.metric("SRH", srh_count)
    role_counts = {r: sum(1 for pid in picks if player_by_id(pid) and player_by_id(pid)["role"] == r) for r in ["WK","BAT","AR","BOWL"]}
    c5.metric("WK/BAT/AR/BOWL", f"{role_counts['WK']}/{role_counts['BAT']}/{role_counts['AR']}/{role_counts['BOWL']}")

    st.divider()

    # Filter
    filter_team = st.radio("Filter by team", ["All", "RCB", "SRH"], horizontal=True)
    filter_role = st.radio("Filter by role", ["All", "WK", "BAT", "AR", "BOWL"], horizontal=True)

    filtered = [p for p in PLAYERS
                if (filter_team == "All" or p["team"] == filter_team)
                and (filter_role == "All" or p["role"] == filter_role)]

    st.markdown("**Select players** — click to pick/unpick. Set C and VC from selected players below.")

    cols = st.columns(3)
    for i, p in enumerate(filtered):
        is_sel = p["id"] in picks
        with cols[i % 3]:
            label = f"{team_badge(p['team'])} {role_color(p['role'])} {p['name']} ({p['credits']}cr)"
            if is_sel:
                label = "✅ " + label
            btn = st.button(label, key=f"p_{p['id']}", use_container_width=True)
            if btn:
                if is_sel:
                    picks.remove(p["id"])
                    if st.session_state.captain == p["id"]:
                        st.session_state.captain = None
                    if st.session_state.vice_captain == p["id"]:
                        st.session_state.vice_captain = None
                else:
                    # Validate
                    if len(picks) >= TEAM_SIZE:
                        st.error("Already selected 11 players.")
                    elif p["team"] == "RCB" and rcb_count >= MAX_PER_TEAM:
                        st.error("Max 7 from RCB.")
                    elif p["team"] == "SRH" and srh_count >= MAX_PER_TEAM:
                        st.error("Max 7 from SRH.")
                    elif remaining < p["credits"]:
                        st.error("Not enough credits!")
                    else:
                        picks.append(p["id"])
                st.session_state.picks = picks
                st.rerun()

    st.divider()
    st.markdown("### Set Captain & Vice-Captain")
    selected_players = [p for p in PLAYERS if p["id"] in picks]
    if selected_players:
        names = [p["name"] for p in selected_players]
        cap_opts = ["— select —"] + names
        vc_opts  = ["— select —"] + names

        cap_idx = 0
        if st.session_state.captain:
            cp = player_by_id(st.session_state.captain)
            if cp and cp["name"] in names:
                cap_idx = names.index(cp["name"]) + 1

        vc_idx = 0
        if st.session_state.vice_captain:
            vp = player_by_id(st.session_state.vice_captain)
            if vp and vp["name"] in names:
                vc_idx = names.index(vp["name"]) + 1

        col_c, col_vc = st.columns(2)
        with col_c:
            c_sel = st.selectbox("Captain (2× points)", cap_opts, index=cap_idx)
            if c_sel != "— select —":
                p = next((x for x in selected_players if x["name"] == c_sel), None)
                if p:
                    st.session_state.captain = p["id"]
        with col_vc:
            vc_sel = st.selectbox("Vice-Captain (1.5× points)", vc_opts, index=vc_idx)
            if vc_sel != "— select —":
                p = next((x for x in selected_players if x["name"] == vc_sel), None)
                if p:
                    st.session_state.vice_captain = p["id"]
    else:
        st.info("Select players first.")

    st.divider()
    if st.button("🚀 Submit Team", type="primary"):
        picks = st.session_state.picks
        captain = st.session_state.captain
        vc = st.session_state.vice_captain

        errors = []
        if len(picks) != TEAM_SIZE:
            errors.append(f"Select exactly 11 players (you have {len(picks)}).")
        if not captain:
            errors.append("Set a Captain.")
        if not vc:
            errors.append("Set a Vice-Captain.")
        if captain and vc and captain == vc:
            errors.append("Captain and Vice-Captain must be different players.")
        # Role limits
        for role, (mn, mx) in ROLE_LIMITS.items():
            cnt = sum(1 for pid in picks if player_by_id(pid) and player_by_id(pid)["role"] == role)
            if cnt < mn or cnt > mx:
                errors.append(f"{role}: need {mn}–{mx}, you have {cnt}.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            data = load_data()
            data["teams"][username.lower()] = {
                "user": username,
                "players": picks,
                "captain": captain,
                "vice_captain": vc,
                "submitted_at": datetime.now().isoformat(),
                "team_complete": True,
            }
            save_data(data)
            st.session_state["page"] = "success"
            st.rerun()

    if st.button("← Back"):
        st.session_state["page"] = "home"
        st.rerun()


def page_success():
    username = st.session_state.get("username", "")
    data = load_data()
    team = data["teams"].get(username.lower())
    if not team or not team.get("team_complete", False):
        st.session_state["page"] = "builder"
        st.rerun()

    st.success("✅ Team submitted and locked!")
    st.markdown(f"### {username}'s team")

    cp = player_by_id(team["captain"])
    vp = player_by_id(team["vice_captain"])
    st.markdown(f"**Captain:** {cp['name']} (2×) &nbsp; | &nbsp; **Vice-Captain:** {vp['name']} (1.5×)")

    players = [player_by_id(pid) for pid in team["players"]]
    for role in ["WK", "BAT", "AR", "BOWL"]:
        rp = [p for p in players if p and p["role"] == role]
        if rp:
            st.markdown(f"**{role_color(role)} {role}:** " + ", ".join(p["name"] for p in rp))

    st.info("🔒 Your team is hidden from others until the match goes live.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Leaderboard"):
            st.session_state["page"] = "leaderboard"
            st.rerun()
    with col2:
        if st.button("🗑️ Delete & redo team", type="secondary"):
            del data["teams"][username.lower()]
            save_data(data)
            st.session_state.picks = []
            st.session_state.captain = None
            st.session_state.vice_captain = None
            st.session_state["page"] = "builder"
            st.rerun()


def page_leaderboard():
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    data = load_data()
    st.markdown("## 📊 Leaderboard")
    st.markdown(f"**{MATCH['t1']['name']} vs {MATCH['t2']['name']}** · IPL 2026")

    # ── Time-based reveal logic ──────────────────────────────────────────────
    teams_revealed = is_past_reveal_time() or data.get("match_live", False)

    now_ist = datetime.now(IST)
    if not teams_revealed:
        reveal_today = now_ist.replace(hour=REVEAL_HOUR_IST, minute=REVEAL_MINUTE_IST, second=0, microsecond=0)
        mins_left = int((reveal_today - now_ist).total_seconds() // 60)
        if mins_left > 0:
            st.info(f"⏳ Teams will be revealed at **7:30 PM IST** — {mins_left} minute(s) to go!")
        else:
            st.info("⏳ Teams will be revealed at **7:30 PM IST**.")
    else:
        st.success("🔓 Teams are now visible! Match has started.")

    # ── Live score ───────────────────────────────────────────────────────────
    live = fetch_live_score()
    if live:
        st.markdown("### 🔴 Live")
        score_text = live.get("status", "Match in progress")
        st.info(score_text)
        scores_raw = live.get("score", [])
        if scores_raw:
            for inn in scores_raw:
                st.markdown(f"**{inn.get('inning','')}:** {inn.get('r',0)}/{inn.get('w',0)} ({inn.get('o',0)} ov)")
    else:
        if API_KEY:
            st.warning("No live data yet — match may not have started.")
        else:
            st.warning("⚠️ Add your CricketData API key in secrets to enable live scores.")

    st.divider()

    all_entries = list(data["teams"].values())

    # Fetch player stats if live
    player_stats = {}
    if live and teams_revealed:
        mid = live.get("id", "")
        player_stats = fetch_player_stats(mid)

    # Build leaderboard rows — include everyone registered, team or not
    rows = []
    for t in all_entries:
        complete = t.get("team_complete", False)
        pts = calc_fantasy_points(t, player_stats) if (teams_revealed and complete) else None
        rows.append({"user": t["user"], "pts": pts, "team": t, "complete": complete})

    # Sort: complete teams first (by pts if revealed), then incomplete
    if teams_revealed:
        rows.sort(key=lambda x: (not x["complete"], -(x["pts"] or 0)))
    else:
        rows.sort(key=lambda x: (not x["complete"], x["user"].lower()))

    if not rows:
        st.info("No participants yet. Be the first!")
    else:
        st.markdown(f"**{len(rows)} participant(s)** · "
                    f"{sum(1 for r in rows if r['complete'])} team(s) submitted")
        st.divider()
        for i, row in enumerate(rows):
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 4, 2, 3])
                col1.markdown(f"**#{i+1}**")

                # Name + status badge
                status = "✅" if row["complete"] else "⏳ No team yet"
                col2.markdown(f"**{row['user']}** {'' if row['complete'] else '— ⏳ picking team'}")

                if not row["complete"]:
                    col3.markdown("—")
                    col4.markdown("—")
                elif teams_revealed:
                    if row["pts"] is not None:
                        col3.markdown(f"🏅 **{row['pts']} pts**")
                    else:
                        col3.markdown("🔒 Points pending")
                    cp = player_by_id(row["team"]["captain"])
                    col4.markdown(f"C: {cp['name'] if cp else '?'}")
                else:
                    col3.markdown("🔒 Hidden")
                    col4.markdown("Revealed at 7:30 PM")

            # Show full team only after reveal time
            if teams_revealed and row["complete"]:
                with st.expander(f"👀 {row['user']}'s team"):
                    players = [player_by_id(pid) for pid in row["team"]["players"]]
                    cp = player_by_id(row["team"]["captain"])
                    vp = player_by_id(row["team"]["vice_captain"])
                    st.markdown(f"**Captain:** {cp['name'] if cp else '?'} (2×) &nbsp;|&nbsp; **VC:** {vp['name'] if vp else '?'} (1.5×)")
                    for role in ["WK", "BAT", "AR", "BOWL"]:
                        rp = [p for p in players if p and p["role"] == role]
                        if rp:
                            st.markdown(f"{role_color(role)} **{role}:** " + ", ".join(p["name"] for p in rp))

    # ── Host controls ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🔑 Host controls")
    host_pw = st.text_input("Host password", type="password", placeholder="set HOST_PASSWORD in secrets")
    real_pw = st.secrets.get("HOST_PASSWORD", "ipl2026host")
    if host_pw == real_pw:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔓 Force reveal now (override time)"):
                data["match_live"] = True
                save_data(data)
                st.success("Teams revealed!")
                st.rerun()
        with c2:
            if st.button("🔒 Lock teams again"):
                data["match_live"] = False
                save_data(data)
                st.rerun()

    st.divider()
    if st.button("← Back"):
        st.session_state["page"] = "home"
        st.rerun()

    if live:
        st.caption("Live scores refresh every 2 minutes. Reload page for latest.")

# ── Router ────────────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state["page"] = "home"

page = st.session_state["page"]

if page == "home":
    page_home()
elif page == "builder":
    page_builder()
elif page == "success":
    page_success()
elif page == "leaderboard":
    page_leaderboard()
