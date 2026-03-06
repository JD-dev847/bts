from datetime import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Bet Tracker", layout="wide")

SHEET_ID = st.secrets["app"]["sheet_id"]
TAB_NAME = st.secrets["app"]["tab_name"]

COLUMNS = [
    "bet_id",
    "ts",
    "league",
    "home",
    "away",
    "structural_score_total",
    "gate_pass",
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

@st.cache_resource
def gs_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(creds)

def get_worksheet():
    return gs_client().open_by_key(SHEET_ID).worksheet(TAB_NAME)

def load_data():
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
        "odd",
        "stake_pct",
        "stake_amt",
        "pnl",
        "bankroll_after",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

def append_row(row):
    ws = get_worksheet()
    ws.append_row([row.get(col, "") for col in COLUMNS], value_input_option="USER_ENTERED")

def calc_pnl(outcome, stake_amt, odd):
    outcome = outcome.lower().strip()
    if outcome == "win":
        return stake_amt * (odd - 1.0)
    if outcome == "lost":
        return -stake_amt
    return 0.0

st.title("Bankroll Tracking")

df = load_data()

starting_bankroll = st.sidebar.number_input(
    "Starting bankroll",
    min_value=0.0,
    value=1000.0,
    step=50.0
)

if df.empty or df["bankroll_after"].dropna().empty:
    current_bankroll = float(starting_bankroll)
else:
    current_bankroll = float(df["bankroll_after"].dropna().iloc[-1])

bets_count = 0 if df.empty else len(df)
total_pnl = 0.0 if df.empty else float(df["pnl"].fillna(0).sum())
win_rate = 0.0
if not df.empty and "outcome" in df.columns:
    settled = df["outcome"].fillna("").str.lower().isin(["win", "lost"])
    if settled.sum() > 0:
        win_rate = (df.loc[settled, "outcome"].str.lower() == "win").mean() * 100

st.subheader("Key figures")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Bankroll", f"{current_bankroll:,.2f}")
c2.metric("PnL", f"{total_pnl:+,.2f}")
c3.metric("Win rate", f"{win_rate:,.1f}%")
c4.metric("Bets", f"{bets_count}")

st.subheader("Bankroll over time")
if df.empty:
    st.info("No bets available yet.")
else:
    chart_df = df.copy()
    chart_df = chart_df[chart_df["bankroll_after"].notna()].copy()
    chart_df["bet_id"] = pd.to_numeric(chart_df["bet_id"], errors="coerce")
    chart_df = chart_df.sort_values("bet_id")
    st.line_chart(chart_df.set_index("bet_id")["bankroll_after"])

st.subheader("History")
if df.empty:
    st.write("No history yet.")
else:
    display_cols = [
        "bet_id",
        "ts",
        "league",
        "home",
        "away",
        "structural_score_total",
        "gate_pass",
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
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

st.subheader("Add bet")

with st.form("add_bet_form", clear_on_submit=True):
    a, b, c, d = st.columns(4)

    with a:
        league = st.text_input("League")
        home = st.text_input("Home")
        away = st.text_input("Away")

    with b:
        structural_score_total = st.number_input("Structural score", min_value=0.0, value=8.0, step=0.5)
        gate_pass = st.selectbox("Gate pass", ["TRUE", "FALSE"])
        bet_type = st.selectbox("Bet type", ["1X2", "Over/Under", "Asian Handicap", "BTTS", "Other"])

    with c:
        bet = st.text_input("Bet")
        odd = st.number_input("Odd", min_value=1.01, value=1.80, step=0.01)
        stake_pct = st.number_input("Stake %", min_value=0.0, value=1.0, step=0.1)

    with d:
        result = st.text_input("Result")
        outcome = st.selectbox("Outcome", ["win", "lost", "draw", "void"])

    submitted = st.form_submit_button("Save")

    if submitted:
        if not league.strip() or not home.strip() or not away.strip() or not bet.strip():
            st.error("Please fill League, Home, Away and Bet.")
        else:
            next_bet_id = 1 if df.empty else int(df["bet_id"].fillna(0).max()) + 1
            stake_amt = current_bankroll * (float(stake_pct) / 100.0)
            pnl = calc_pnl(outcome, stake_amt, float(odd))
            bankroll_after = current_bankroll + pnl

            row = {
                "bet_id": next_bet_id,
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "league": league.strip(),
                "home": home.strip(),
                "away": away.strip(),
                "structural_score_total": float(structural_score_total),
                "gate_pass": gate_pass,
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
