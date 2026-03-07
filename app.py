from datetime import datetime

import altair as alt
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Bet Tracker", layout="wide")

# --------------------------------------------------
# Fixed configuration
# --------------------------------------------------

STARTING_BANKROLL = 100.0
BASE_STAKE_PCT = 1.0

SHEET_ID = st.secrets["app"]["sheet_id"]
TAB_NAME = st.secrets["app"]["tab_name"]

# --------------------------------------------------
# Lists
# --------------------------------------------------

BET_FACTORS = [1.0, 0.5, 0.25]
SETTLE_OUTCOMES = ["win", "lost", "void"]

LEAGUES = ["2. Bundesliga", "Other"]

TEAMS_2BL = [
    "Arminia Bielefeld",
    "Dynamo Dresden",
    "Eintracht Braunschweig",
    "FC Schalke 04",
    "Fortuna Düsseldorf",
    "Greuther Fürth",
    "Hannover 96",
    "Hertha BSC",
    "Holstein Kiel",
    "Karlsruher SC",
    "SC Paderborn",
    "SV Darmstadt 98",
    "SV Elversberg",
    "Preußen Münster",
    "1. FC Kaiserslautern",
    "1. FC Magdeburg",
    "1. FC Nürnberg",
    "VfL Bochum",
]

BET_TYPES = ["1X2", "Over/Under", "Asian Handicap", "BTTS"]

ONE_X_TWO = ["Home", "Draw", "Away"]

OU_OPTIONS = [
    "Over 0.5", "Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5",
    "Under 0.5", "Under 1.5", "Under 2.5", "Under 3.5", "Under 4.5"
]

BTTS_OPTIONS = ["Yes", "No"]

AHC_OPTIONS = [
    "Home -2.0", "Home -1.75", "Home -1.5", "Home -1.25", "Home -1.0",
    "Home -0.75", "Home -0.5", "Home -0.25", "Home 0",
    "Away 0", "Away +0.25", "Away +0.5", "Away +0.75",
    "Away +1.0", "Away +1.25", "Away +1.5", "Away +1.75", "Away +2.0"
]

COLUMNS = [
    "bet_id", "ts", "league", "home", "away", "structural_score_total",
    "gate_pass", "bet_factor", "bet_type", "bet", "odd", "stake_pct",
    "stake_amt", "result", "outcome", "pnl", "bankroll_after"
]

# --------------------------------------------------
# Session state
# --------------------------------------------------

FORM_DEFAULTS = {
    "league": "2. Bundesliga",
    "home": "",
    "away": "",
    "score": 8.0,
    "factor": 1.0,
    "bet_type": "1X2",
    "bet_selection": "Home",
    "odd": 1.80,
}

def init_state():
    for key, value in FORM_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "reset_form" not in st.session_state:
        st.session_state["reset_form"] = False

def apply_form_reset():
    if st.session_state["reset_form"]:
        for key, value in FORM_DEFAULTS.items():
            st.session_state[key] = value
        st.session_state["reset_form"] = False

init_state()
apply_form_reset()

# --------------------------------------------------
# Google connection
# --------------------------------------------------

@st.cache_resource
def connect():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def sheet():
    return connect().open_by_key(SHEET_ID).worksheet(TAB_NAME)

# --------------------------------------------------
# Load data
# --------------------------------------------------

def load():
    records = sheet().get_all_records()
    if not records:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(records)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS].copy()

    numeric = [
        "bet_id", "structural_score_total", "bet_factor",
        "odd", "stake_pct", "stake_amt", "pnl", "bankroll_after"
    ]

    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["bet_id"] = pd.to_numeric(df["bet_id"], errors="coerce")
    df = df.sort_values("bet_id").reset_index(drop=True)
    return df

# --------------------------------------------------
# Data actions
# --------------------------------------------------

def append(row):
    sheet().append_row([row.get(c, "") for c in COLUMNS], value_input_option="USER_ENTERED")

def update_row(bet_id, updates):
    ws = sheet()
    data = ws.get_all_values()
    header = data[0]
    id_col = header.index("bet_id") + 1

    for i in range(2, len(data) + 1):
        val = ws.cell(i, id_col).value
        try:
            if int(float(val)) == int(bet_id):
                for k, v in updates.items():
                    if k in header:
                        col = header.index(k) + 1
                        ws.update_cell(i, col, v)
                return True
        except Exception:
            pass
    return False

def delete_last_row():
    ws = sheet()
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return False
    ws.delete_rows(len(rows))
    return True

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def calc_pnl(outcome, stake, odd):
    if outcome == "win":
        return stake * (odd - 1)
    if outcome == "lost":
        return -stake
    return 0.0

def bet_options(bet_type):
    if bet_type == "1X2":
        return ONE_X_TWO
    if bet_type == "Over/Under":
        return OU_OPTIONS
    if bet_type == "Asian Handicap":
        return AHC_OPTIONS
    if bet_type == "BTTS":
        return BTTS_OPTIONS
    return ["Other"]

# --------------------------------------------------
# Load dataset
# --------------------------------------------------

df = load()

settled = df[df["outcome"].astype(str).isin(["win", "lost", "void"])].copy()
openbets = df[df["outcome"].astype(str) == "open"].copy()

if settled.empty or settled["bankroll_after"].dropna().empty:
    bankroll = STARTING_BANKROLL
else:
    bankroll = float(settled["bankroll_after"].dropna().iloc[-1])

# --------------------------------------------------
# Sidebar (new bet only)
# --------------------------------------------------

with st.sidebar:
    st.header("New Bet")

    league = st.selectbox("League", LEAGUES, key="league")

    if league == "2. Bundesliga":
        home = st.selectbox("Home", [""] + TEAMS_2BL, key="home")
        away = st.selectbox("Away", [""] + TEAMS_2BL, key="away")
    else:
        home = st.text_input("Home", key="home")
        away = st.text_input("Away", key="away")

    score = st.number_input(
        "Structural Score",
        min_value=0.0,
        max_value=20.0,
        step=0.5,
        key="score",
    )

    factor = st.selectbox("Bet Factor", BET_FACTORS, key="factor")
    bet_type = st.selectbox("Bet Type", BET_TYPES, key="bet_type")

    options = bet_options(bet_type)
    if st.session_state["bet_selection"] not in options:
        st.session_state["bet_selection"] = options[0]

    bet_selection = st.selectbox("Bet", options, key="bet_selection")

    odd = st.number_input(
        "Odd",
        min_value=1.01,
        max_value=10.0,
        step=0.01,
        key="odd",
    )

    save = st.button("Save Bet", use_container_width=True)
    delete_last = st.button("Delete Last Bet", use_container_width=True)

# --------------------------------------------------
# Save new bet
# --------------------------------------------------

if save:
    if home == away or home == "" or away == "":
        st.error("Check teams.")
    else:
        next_id = 1 if df.empty else int(df["bet_id"].max()) + 1
        stake = bankroll * (BASE_STAKE_PCT / 100) * factor

        row = {
            "bet_id": next_id,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "league": league,
            "home": home,
            "away": away,
            "structural_score_total": score,
            "gate_pass": score >= 8.0,
            "bet_factor": factor,
            "bet_type": bet_type,
            "bet": bet_selection,
            "odd": odd,
            "stake_pct": BASE_STAKE_PCT,
            "stake_amt": round(stake, 2),
            "result": "",
            "outcome": "open",
            "pnl": "",
            "bankroll_after": ""
        }

        append(row)
        st.session_state["reset_form"] = True
        st.success("Bet saved.")
        st.rerun()

if delete_last:
    deleted = delete_last_row()
    if deleted:
        st.warning("Last bet deleted.")
    else:
        st.info("No row available to delete.")
    st.rerun()

# --------------------------------------------------
# KPIs
# --------------------------------------------------

bets = len(settled)
total_pnl = float(settled["pnl"].sum()) if not settled.empty else 0.0
total_stake = float(settled["stake_amt"].sum()) if not settled.empty else 0.0
roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0.0
avg_odds = float(settled["odd"].mean()) if not settled.empty else 0.0

wins = int((settled["outcome"] == "win").sum()) if not settled.empty else 0
losses = int((settled["outcome"] == "lost").sum()) if not settled.empty else 0
winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

st.title("Bet Tracker")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Bankroll", f"{bankroll:.2f}")
c2.metric("PnL", f"{total_pnl:+.2f}")
c3.metric("ROI", f"{roi:.1f}%")
c4.metric("Win Rate", f"{winrate:.1f}%")
c5.metric("Bets", bets)
c6.metric("Avg Odds", f"{avg_odds:.2f}" if bets > 0 else "—")

st.caption(
    f"Starting bankroll: {STARTING_BANKROLL:.2f} | "
    f"Base stake: {BASE_STAKE_PCT:.1f}%"
)

# --------------------------------------------------
# Chart
# --------------------------------------------------

st.subheader("Bankroll")

if settled.empty:
    st.write("No settled bets yet.")
else:
    chart = settled[["bet_id", "bankroll_after"]].dropna().copy()
    chart["bet_id"] = pd.to_numeric(chart["bet_id"], errors="coerce")
    chart["bankroll_after"] = pd.to_numeric(chart["bankroll_after"], errors="coerce")
    chart = chart.dropna()

    max_bet = int(chart["bet_id"].max())
    x_max = max_bet + 10

    y_min = STARTING_BANKROLL * 0.9
    y_max = STARTING_BANKROLL * 1.1

    # Bankroll line: actual data points only
    line_df = pd.DataFrame({
        "bet_id": chart["bet_id"],
        "value": chart["bankroll_after"],
        "series": ["Bankroll"] * len(chart),
    })

    # Reference line: full span from 1 to x_max
    ref_df = pd.DataFrame({
        "bet_id": list(range(1, x_max + 1)),
        "value": [STARTING_BANKROLL] * x_max,
        "series": ["Start"] * x_max,
    })

    # Chart layers
    bankroll_line = alt.Chart(line_df).mark_line(point=True).encode(
        x=alt.X(
            "bet_id:Q",
            title="Bet #",
            scale=alt.Scale(domain=[1, x_max]),
            axis=alt.Axis(format="d", tickMinStep=1),
        ),
        y=alt.Y(
            "value:Q",
            title="Bankroll",
            scale=alt.Scale(domain=[y_min, y_max]),
        ),
        color=alt.value("#1f77b4"),
        tooltip=["bet_id", "value"],
    )

    start_line = alt.Chart(ref_df).mark_line(strokeDash=[6, 4]).encode(
        x=alt.X(
            "bet_id:Q",
            scale=alt.Scale(domain=[1, x_max]),
            axis=alt.Axis(format="d", tickMinStep=1),
        ),
        y=alt.Y(
            "value:Q",
            scale=alt.Scale(domain=[y_min, y_max]),
        ),
        color=alt.value("#9ca3af"),
        tooltip=["bet_id", "value"],
    )

    bankroll_chart = (start_line + bankroll_line).properties(height=320)

    st.altair_chart(bankroll_chart, use_container_width=True)

# --------------------------------------------------
# Open bets
# --------------------------------------------------

st.subheader("Open Bets")

if openbets.empty:
    st.write("No open bets.")
else:
    open_view = openbets.copy()
    open_view["Date"] = pd.to_datetime(open_view["ts"], errors="coerce").dt.strftime("%Y-%m-%d")
    open_view["Match"] = open_view["home"] + " - " + open_view["away"]
    open_view["Odds"] = open_view["odd"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    open_view["Stake"] = open_view["stake_amt"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")

    st.dataframe(
        open_view[["bet_id", "Date", "Match", "bet", "Odds", "Stake"]].rename(
            columns={
                "bet_id": "Bet#",
                "bet": "Bet",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    options = {
        f"Bet #{int(r.bet_id)} | {r.home} - {r.away} | {r.bet}": int(r.bet_id)
        for _, r in openbets.iterrows()
    }

    pick = st.selectbox("Select bet to settle", list(options.keys()))
    bet_id = options[pick]

    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        result = st.text_input("Result", placeholder="e.g. 2-1")

    with c2:
        outcome = st.selectbox("Outcome", SETTLE_OUTCOMES)

    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        settle = st.button("Settle Bet", use_container_width=True)

    if settle:
        if not result.strip():
            st.error("Please enter a result.")
        else:
            row = openbets[openbets["bet_id"] == bet_id].iloc[0]
            p = calc_pnl(outcome, row["stake_amt"], row["odd"])
            new_bankroll = bankroll + p

            updated = update_row(
                bet_id,
                {
                    "result": result,
                    "outcome": outcome,
                    "pnl": round(p, 2),
                    "bankroll_after": round(new_bankroll, 2),
                },
            )

            if updated:
                st.success("Bet settled.")
                st.rerun()
            else:
                st.error("Could not update selected bet.")

# --------------------------------------------------
# History
# --------------------------------------------------

st.subheader("History")

if settled.empty:
    st.write("No history.")
else:
    hist = settled.copy()
    hist["Date"] = pd.to_datetime(hist["ts"], errors="coerce").dt.strftime("%Y-%m-%d")
    hist["Match"] = hist["home"] + " - " + hist["away"]
    hist["Odds"] = hist["odd"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    hist["Stake"] = hist["stake_amt"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    hist["PnL"] = hist["pnl"].map(lambda x: f"{x:+.2f}" if pd.notna(x) else "")
    hist["Outcome"] = hist["outcome"].astype(str).str.title()

    st.dataframe(
        hist[[
            "bet_id", "Date", "Match", "bet",
            "Odds", "Stake", "result", "Outcome", "PnL"
        ]].rename(
            columns={
                "bet_id": "Bet#",
                "bet": "Bet",
                "result": "Result",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
