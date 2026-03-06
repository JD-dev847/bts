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
# Constants / config
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

BET_TYPES = [
    "1X2",
    "Over/Under",
    "Asian Handicap",
    "BTTS",
    "Other",
]

OUTCOMES = ["win", "lost", "draw", "void"]
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


def format_match(home: str, away: str) -> str:
    return f"{home} – {away}"


# --------------------------------------------------
# Load data
# --------------------------------------------------
df = load_data()

with st.sidebar:
    st.header("Input")

    starting_bankroll = st.number_input(
        "Starting bankroll",
        min_value=0.0,
        value=1000.0,
        step=50.0,
    )

    st.markdown("---")

    league = st.selectbox("League", LEAGUES, index=0)
    home = st.text_input("Home")
    away = st.text_input("Away")

    structural_score_total = st.number_input(
        "Structural score",
        min_value=0.0,
        max_value=20.0,
        value=8.0,
        step=0.5,
    )

    gate_pass = structural_score_total >= GATE_THRESHOLD

    bet_factor = st.selectbox("Bet factor", BET_FACTORS, index=0)
    bet_type = st.selectbox("Bet type", BET_TYPES, index=0)

    bet = st.text_input("Bet")
    odd = st.number_input("Odd", min_value=1.01, value=1.80, step=0.01)
    stake_pct = st.number_input("Stake %", min_value=0.0, value=1.0, step=0.1)

    result = st.text_input("Result")
    outcome = st.selectbox("Outcome", OUTCOMES, index=0)

    save_bet = st.button("Save bet", use_container_width=True)

# --------------------------------------------------
# Current bankroll
# --------------------------------------------------
if df.empty or df["bankroll_after"].dropna().empty:
    current_bankroll = float(starting_bankroll)
else:
    current_bankroll = float(df["bankroll_after"].dropna().iloc[-1])

# --------------------------------------------------
# Save new row
# --------------------------------------------------
if save_bet:
    if not home.strip() or not away.strip() or not bet.strip():
        st.error("Please fill Home, Away and Bet.")
    else:
        next_bet_id = 1 if df.empty else int(df["bet_id"].fillna(0).max()) + 1

        stake_amt = current_bankroll * (float(stake_pct) / 100.0) * float(bet_factor)
        pnl = calc_pnl(outcome, stake_amt, float(odd))
        bankroll_after = current_bankroll + pnl

        row = {
            "bet_id": next_bet_id,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "league": league.strip(),
            "home": home.strip(),
            "away": away.strip(),
            "structural_score_total": float(structural_score_total),
            "gate_pass": "TRUE" if gate_pass else "FALSE",
            "bet_factor": float(bet_factor),
            "bet_type": bet_type,
            "bet": bet.strip(),
            "odd": float(odd),
            "stake_pct": float(stake_pct),
            "stake_amt": round(float(stake_amt), 2),
            "result": result.strip(),
            "outcome": outcome,
            "pnl": round(float(pnl), 2),
            "bankroll_after": round(float(bankroll_after), 2),
        }

        append_row(row)
        st.success(f"Bet saved. New bankroll: {bankroll_after:,.2f}")
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

st.caption(f"Starting bankroll: {starting_bankroll:,.2f} | Gate threshold: {GATE_THRESHOLD:.1f}")

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

    ref_df = pd.DataFrame(
        {
            "bet_id": chart_df["bet_id"],
            "Bankroll": chart_df["bankroll_after"].values,
            "Starting Bankroll": [starting_bankroll] * len(chart_df),
        }
    ).set_index("bet_id")

    st.line_chart(ref_df)

# --------------------------------------------------
# History table (lean display)
# --------------------------------------------------
st.subheader("History")

if df.empty:
    st.write("No history yet.")
else:
    history_df = df.copy()

    history_df["Date"] = pd.to_datetime(history_df["ts"], errors="coerce").dt.strftime("%d-%m-%Y")
    history_df["Match"] = history_df.apply(
        lambda x: format_match(str(x["home"]), str(x["away"])),
        axis=1,
    )
    history_df["Score"] = history_df["structural_score_total"].map(
        lambda x: f"{x:.1f}" if pd.notna(x) else ""
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
            "Score",
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
