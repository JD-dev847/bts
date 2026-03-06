from datetime import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Bankroll Tracking", layout="wide")

# ------------------------------------------------
# CONFIG
# ------------------------------------------------

SHEET_ID = st.secrets["app"]["sheet_id"]
TAB_NAME = st.secrets["app"]["tab_name"]

GATE_THRESHOLD = 8

LEAGUES = [
    "2. Bundesliga",
    "Bundesliga",
    "Premier League",
    "Serie A",
    "La Liga",
    "Championship",
    "Other",
]

BET_TYPES = [
    "1X2",
    "Over/Under",
    "Asian Handicap",
    "BTTS",
    "Other",
]

OUTCOMES = ["open", "win", "lost", "void"]
BET_FACTORS = [1.0, 0.5, 0.25]

COLUMNS = [
    "bet_id",
    "ts",
    "league",
    "home",
    "away",
    "structural_score_total",
    "gate_pass",
    "bet_factor",
    "bet_type",
    "bet",
    "odd",
    "stake_pct",
    "stake_amt",
    "result",
    "outcome",
    "pnl",
    "bankroll_after",
]

# ------------------------------------------------
# GOOGLE SHEETS CONNECTION
# ------------------------------------------------

@st.cache_resource
def gs_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes,
    )
    return gspread.authorize(creds)

def get_worksheet():
    return gs_client().open_by_key(SHEET_ID).worksheet(TAB_NAME)

# ------------------------------------------------
# LOAD DATA
# ------------------------------------------------

def load_data():
    ws = get_worksheet()
    records = ws.get_all_records()

    if not records:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(records)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS]

    numeric_cols = [
        "bet_id",
        "structural_score_total",
        "bet_factor",
        "odd",
        "stake_pct",
        "stake_amt",
        "pnl",
        "bankroll_after",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("bet_id")

    return df

def append_row(row):
    ws = get_worksheet()
    ws.append_row([row.get(col, "") for col in COLUMNS])

def delete_last_row():
    ws = get_worksheet()
    rows = ws.get_all_values()
    ws.delete_rows(len(rows))

# ------------------------------------------------
# BUSINESS LOGIC
# ------------------------------------------------

def calc_pnl(outcome, stake_amt, odd):

    outcome = outcome.lower()

    if outcome == "win":
        return stake_amt * (odd - 1)

    if outcome == "lost":
        return -stake_amt

    return 0

# ------------------------------------------------
# LOAD DATA
# ------------------------------------------------

df = load_data()

# ------------------------------------------------
# SIDEBAR INPUT
# ------------------------------------------------

with st.sidebar:

    st.header("Input")

    starting_bankroll = st.number_input(
        "Starting bankroll",
        value=1000.0,
        step=50.0,
    )

    league = st.selectbox("League", LEAGUES)

    home = st.text_input("Home")

    away = st.text_input("Away")

    structural_score_total = st.number_input(
        "Structural score",
        value=8.0,
        step=0.5,
    )

    gate_pass = structural_score_total >= GATE_THRESHOLD

    bet_factor = st.selectbox("Bet factor", BET_FACTORS)

    bet_type = st.selectbox("Bet type", BET_TYPES)

    bet = st.text_input("Bet")

    odd = st.number_input("Odd", value=1.80, step=0.01)

    stake_pct = st.number_input("Stake %", value=1.0, step=0.1)

    result = st.text_input("Result")

    outcome = st.selectbox("Outcome", OUTCOMES, index=0)

    save = st.button("Save bet")

    clear = st.button("Clear form")

    delete = st.button("Delete last bet")

# ------------------------------------------------
# BANKROLL
# ------------------------------------------------

if df.empty or df["bankroll_after"].dropna().empty:

    current_bankroll = starting_bankroll

else:

    current_bankroll = df["bankroll_after"].dropna().iloc[-1]

# ------------------------------------------------
# SAVE BET
# ------------------------------------------------

if save:

    next_id = 1 if df.empty else int(df["bet_id"].max()) + 1

    stake_amt = current_bankroll * (stake_pct / 100) * bet_factor

    pnl = 0
    bankroll_after = current_bankroll

    if outcome != "open":

        pnl = calc_pnl(outcome, stake_amt, odd)

        bankroll_after = current_bankroll + pnl

    row = {
        "bet_id": next_id,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "league": league,
        "home": home,
        "away": away,
        "structural_score_total": structural_score_total,
        "gate_pass": gate_pass,
        "bet_factor": bet_factor,
        "bet_type": bet_type,
        "bet": bet,
        "odd": odd,
        "stake_pct": stake_pct,
        "stake_amt": round(stake_amt,2),
        "result": result,
        "outcome": outcome,
        "pnl": round(pnl,2),
        "bankroll_after": round(bankroll_after,2),
    }

    append_row(row)

    st.success("Bet saved")

    st.rerun()

# ------------------------------------------------
# DELETE LAST BET
# ------------------------------------------------

if delete:

    delete_last_row()

    st.warning("Last bet deleted")

    st.rerun()

# ------------------------------------------------
# KPI CALCULATIONS
# ------------------------------------------------

bets = len(df)

total_pnl = df["pnl"].fillna(0).sum()

avg_odds = df["odd"].mean()

total_stake = df["stake_amt"].fillna(0).sum()

roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0

wins = df["outcome"].str.lower().eq("win").sum()

loss = df["outcome"].str.lower().eq("lost").sum()

win_rate = (wins / (wins + loss) * 100) if (wins + loss) > 0 else 0

# ------------------------------------------------
# MAIN SCREEN
# ------------------------------------------------

st.title("Bankroll Tracking")

c1,c2,c3,c4,c5,c6 = st.columns(6)

c1.metric("Bankroll", f"{current_bankroll:.2f}")

c2.metric("PnL", f"{total_pnl:+.2f}")

c3.metric("ROI", f"{roi:.2f}%")

c4.metric("Win Rate", f"{win_rate:.1f}%")

c5.metric("Bets", bets)

c6.metric("Avg Odds", f"{avg_odds:.2f}" if pd.notna(avg_odds) else "—")

# ------------------------------------------------
# BANKROLL CHART
# ------------------------------------------------

st.subheader("Bankroll over time")

if not df.empty:

    chart_df = df.dropna(subset=["bankroll_after"])

    chart_df = chart_df.set_index("bet_id")

    st.line_chart(chart_df["bankroll_after"])

# ------------------------------------------------
# HISTORY TABLE
# ------------------------------------------------

st.subheader("History")

if not df.empty:

    history = df.copy()

    history["Match"] = history["home"] + " – " + history["away"]

    display = history[
        [
            "bet_id",
            "ts",
            "Match",
            "bet",
            "odd",
            "stake_pct",
            "bet_factor",
            "outcome",
            "pnl",
            "bankroll_after",
        ]
    ]

    display.columns = [
        "Bet#",
        "Date",
        "Match",
        "Bet",
        "Odds",
        "Stake %",
        "Factor",
        "Outcome",
        "PnL",
        "Bankroll",
    ]

    st.dataframe(display, use_container_width=True)
