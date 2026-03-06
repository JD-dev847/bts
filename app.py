from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

# --------------------------------------------------
# Page config
# --------------------------------------------------
st.set_page_config(page_title="Bankroll Tracking", layout="wide")

# --------------------------------------------------
# Secrets / constants
# --------------------------------------------------
SHEET_ID = st.secrets["app"]["sheet_id"]
TAB_NAME = st.secrets["app"]["tab_name"]

GATE_THRESHOLD = 8.0

LEAGUES = [
    "2. Bundesliga",
    "Bundesliga",
    "Premier League",
    "Serie A",
    "La Liga",
    "Championship",
    "Other",
]

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

BET_TYPES = [
    "1X2",
    "Over/Under",
    "Asian Handicap",
    "BTTS",
    "Other",
]

OUTCOMES = ["open", "win", "lost", "void"]
BET_FACTORS = [1.0, 0.5, 0.25]

AHC_OPTIONS = [
    "Home -2.0",
    "Home -1.75",
    "Home -1.5",
    "Home -1.25",
    "Home -1.0",
    "Home -0.75",
    "Home -0.5",
    "Home -0.25",
    "Home 0",
    "Away 0",
    "Away +0.25",
    "Away +0.5",
    "Away +0.75",
    "Away +1.0",
    "Away +1.25",
    "Away +1.5",
    "Away +1.75",
    "Away +2.0",
]

OU_OPTIONS = [
    "Over 0.5",
    "Over 1.5",
    "Over 2.5",
    "Over 3.5",
    "Over 4.5",
    "Under 0.5",
    "Under 1.5",
    "Under 2.5",
    "Under 3.5",
    "Under 4.5",
]

ONE_X_TWO_OPTIONS = ["Home", "Draw", "Away"]
BTTS_OPTIONS = ["Yes", "No"]
OTHER_OPTIONS = ["Other"]

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

# --------------------------------------------------
# Session-state defaults
# --------------------------------------------------
FORM_DEFAULTS = {
    "league": "2. Bundesliga",
    "home": "",
    "away": "",
    "structural_score_total": 8.0,
    "bet_factor": 1.0,
    "bet_type": "1X2",
    "bet": "Home",
    "odd": 1.80,
    "result": "",
    "outcome": "open",
}

APP_DEFAULTS = {
    "starting_bankroll": 1000.0,
    "base_stake_pct": 1.0,
}


def init_state():
    for key, value in APP_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for key, value in FORM_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_form():
    for key, value in FORM_DEFAULTS.items():
        st.session_state[key] = value


init_state()

# --------------------------------------------------
# Google Sheets helpers
# --------------------------------------------------
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


def load_data() -> pd.DataFrame:
    ws = get_worksheet()
    records = ws.get_all_records()

    if not records:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(records)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS].copy()

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

    df["bet_id"] = pd.to_numeric(df["bet_id"], errors="coerce")
    df = df.sort_values("bet_id", na_position="last").reset_index(drop=True)

    return df


def append_row(row: dict) -> None:
    ws = get_worksheet()
    ws.append_row([row.get(col, "") for col in COLUMNS], value_input_option="USER_ENTERED")


def delete_last_row() -> bool:
    ws = get_worksheet()
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return False
    ws.delete_rows(len(rows))
    return True

# --------------------------------------------------
# Business logic
# --------------------------------------------------
def calc_pnl(outcome: str, stake_amt: float, odd: float) -> float:
    outcome = outcome.lower().strip()
    if outcome == "win":
        return stake_amt * (odd - 1.0)
    if outcome == "lost":
        return -stake_amt
    return 0.0


def get_bet_options(bet_type: str) -> list[str]:
    if bet_type == "1X2":
        return ONE_X_TWO_OPTIONS
    if bet_type == "Over/Under":
        return OU_OPTIONS
    if bet_type == "Asian Handicap":
        return AHC_OPTIONS
    if bet_type == "BTTS":
        return BTTS_OPTIONS
    return OTHER_OPTIONS


def format_match(home: str, away: str) -> str:
    return f"{home} – {away}"

# --------------------------------------------------
# Load data
# --------------------------------------------------
df = load_data()

if df.empty or df["bankroll_after"].dropna().empty:
    current_bankroll = float(st.session_state["starting_bankroll"])
else:
    current_bankroll = float(df["bankroll_after"].dropna().iloc[-1])

# --------------------------------------------------
# Sidebar inputs
# --------------------------------------------------
with st.sidebar:
    st.header("Input")

    st.number_input(
        "Starting bankroll",
        min_value=0.0,
        step=50.0,
        key="starting_bankroll",
    )

    st.number_input(
        "Base stake %",
        min_value=0.0,
        step=0.1,
        key="base_stake_pct",
    )

    st.markdown("---")

    st.selectbox("League", LEAGUES, key="league")

    if st.session_state["league"] == "2. Bundesliga":
        st.selectbox("Home", [""] + TEAMS_2BL, key="home")
        st.selectbox("Away", [""] + TEAMS_2BL, key="away")
    else:
        st.text_input("Home", key="home")
        st.text_input("Away", key="away")

    st.number_input(
        "Structural score",
        min_value=0.0,
        max_value=20.0,
        step=0.5,
        key="structural_score_total",
    )

    gate_pass = st.session_state["structural_score_total"] >= GATE_THRESHOLD

    st.selectbox("Bet factor", BET_FACTORS, key="bet_factor")
    st.selectbox("Bet type", BET_TYPES, key="bet_type")

    bet_options = get_bet_options(st.session_state["bet_type"])
    if st.session_state["bet"] not in bet_options:
        st.session_state["bet"] = bet_options[0]
    st.selectbox("Bet", bet_options, key="bet")

    st.number_input(
        "Odd",
        min_value=1.01,
        step=0.01,
        key="odd",
    )

    st.text_input("Result", key="result")
    st.selectbox("Outcome", OUTCOMES, key="outcome")

    st.caption(f"Gate pass: {'TRUE' if gate_pass else 'FALSE'}")

    col1, col2 = st.columns(2)
    save_bet = col1.button("Save bet", use_container_width=True)
    clear_bet = col2.button("Clear form", use_container_width=True)

    delete_last = st.button("Delete last bet", use_container_width=True)

# --------------------------------------------------
# Actions
# --------------------------------------------------
if clear_bet:
    clear_form()
    st.rerun()

if delete_last:
    deleted = delete_last_row()
    if deleted:
        st.warning("Last bet deleted.")
    else:
        st.info("No data row available to delete.")
    st.rerun()

if save_bet:
    home = str(st.session_state["home"]).strip()
    away = str(st.session_state["away"]).strip()

    if not home or not away:
        st.error("Please fill Home and Away.")
    elif home == away:
        st.error("Home and Away must be different.")
    else:
        next_bet_id = 1 if df.empty else int(df["bet_id"].fillna(0).max()) + 1

        stake_pct = float(st.session_state["base_stake_pct"])
        bet_factor = float(st.session_state["bet_factor"])
        odd = float(st.session_state["odd"])
        outcome = st.session_state["outcome"]

        stake_amt = current_bankroll * (stake_pct / 100.0) * bet_factor

        pnl = 0.0
        bankroll_after = current_bankroll

        if outcome != "open":
            pnl = calc_pnl(outcome, stake_amt, odd)
            bankroll_after = current_bankroll + pnl

        row = {
            "bet_id": next_bet_id,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "league": st.session_state["league"],
            "home": home,
            "away": away,
            "structural_score_total": float(st.session_state["structural_score_total"]),
            "gate_pass": "TRUE" if gate_pass else "FALSE",
            "bet_factor": bet_factor,
            "bet_type": st.session_state["bet_type"],
            "bet": st.session_state["bet"],
            "odd": odd,
            "stake_pct": stake_pct,
            "stake_amt": round(stake_amt, 2),
            "result": st.session_state["result"].strip(),
            "outcome": outcome,
            "pnl": round(pnl, 2),
            "bankroll_after": round(bankroll_after, 2),
        }

        append_row(row)
        clear_form()
        st.success("Bet saved.")
        st.rerun()

# --------------------------------------------------
# KPI calculations
# --------------------------------------------------
bets_count = 0 if df.empty else len(df)
total_pnl = 0.0 if df.empty else float(df["pnl"].fillna(0).sum())
avg_odds = 0.0 if df.empty else float(df["odd"].dropna().mean()) if df["odd"].dropna().size else 0.0
total_stake = 0.0 if df.empty else float(df["stake_amt"].fillna(0).sum())
roi = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0

win_rate = 0.0
if not df.empty and "outcome" in df.columns:
    settled = df["outcome"].fillna("").str.lower().isin(["win", "lost"])
    if settled.sum() > 0:
        win_rate = (df.loc[settled, "outcome"].str.lower() == "win").mean() * 100.0

# --------------------------------------------------
# Main screen
# --------------------------------------------------
st.title("Bankroll Tracking")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Bankroll", f"{current_bankroll:,.2f}")
k2.metric("PnL", f"{total_pnl:+,.2f}")
k3.metric("ROI", f"{roi:+.2f}%")
k4.metric("Win Rate", f"{win_rate:.1f}%")
k5.metric("Bets", f"{bets_count}")
k6.metric("Avg Odds", f"{avg_odds:.2f}" if avg_odds > 0 else "—")

st.caption(
    f"Starting bankroll: {st.session_state['starting_bankroll']:,.2f} | "
    f"Base stake: {st.session_state['base_stake_pct']:.1f}% | "
    f"Gate threshold: {GATE_THRESHOLD:.1f}"
)

# --------------------------------------------------
# Chart
# --------------------------------------------------
st.subheader("Bankroll over time")

if df.empty:
    st.info("No bets available yet.")
else:
    chart_df = df[df["bet_id"].notna() & df["bankroll_after"].notna()].copy()
    chart_df["bet_id"] = chart_df["bet_id"].astype(int)
    chart_df = chart_df.sort_values("bet_id")

    chart_out = pd.DataFrame(
        {
            "bet_id": chart_df["bet_id"],
            "Bankroll": chart_df["bankroll_after"].values,
            "Starting Bankroll": [st.session_state["starting_bankroll"]] * len(chart_df),
        }
    ).set_index("bet_id")

    st.line_chart(chart_out)

# --------------------------------------------------
# History table
# --------------------------------------------------
st.subheader("History")

if df.empty:
    st.write("No history yet.")
else:
    history_df = df.copy()
    history_df["Date"] = pd.to_datetime(history_df["ts"], errors="coerce").dt.strftime("%Y-%m-%d")
    history_df["Match"] = history_df.apply(
        lambda x: format_match(str(x["home"]), str(x["away"])),
        axis=1,
    )
    history_df["Odds"] = history_df["odd"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    history_df["Stake %"] = history_df["stake_pct"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
    history_df["Factor"] = history_df["bet_factor"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    history_df["PnL"] = history_df["pnl"].map(lambda x: f"{x:+.2f}" if pd.notna(x) else "")
    history_df["Bankroll"] = history_df["bankroll_after"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    history_df["Outcome"] = history_df["outcome"].astype(str).str.title()

    display_df = history_df[
        [
            "bet_id",
            "Date",
            "Match",
            "bet",
            "Odds",
            "Stake %",
            "Factor",
            "Outcome",
            "PnL",
            "Bankroll",
        ]
    ].rename(
        columns={
            "bet_id": "Bet#",
            "bet": "Bet",
        }
    )

    st.dataframe(display_df, use_container_width=True, hide_index=True)
