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

BET_FACTORS = [1.0, 0.5, 0.25]
SETTLE_OUTCOMES = ["win", "lost", "void"]

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
}

APP_DEFAULTS = {
    "starting_bankroll": 1000.0,
    "base_stake_pct": 1.0,
}

SETTLEMENT_DEFAULTS = {
    "selected_open_bet_id": None,
    "settle_result": "",
    "settle_outcome": "win",
}


def init_state() -> None:
    for key, value in APP_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    for key, value in FORM_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    for key, value in SETTLEMENT_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "reset_form" not in st.session_state:
        st.session_state["reset_form"] = False


def apply_form_reset() -> None:
    if st.session_state["reset_form"]:
        for key, value in FORM_DEFAULTS.items():
            st.session_state[key] = value
        st.session_state["reset_form"] = False


init_state()
apply_form_reset()

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


def update_row_by_bet_id(bet_id: int, updates: dict) -> bool:
    ws = get_worksheet()
    all_values = ws.get_all_values()

    if len(all_values) < 2:
        return False

    headers = all_values[0]

    bet_id_col = headers.index("bet_id") + 1

    for row_idx in range(2, len(all_values) + 1):
        cell_value = ws.cell(row_idx, bet_id_col).value
        try:
            if int(float(cell_value)) == int(bet_id):
                for key, value in updates.items():
                    if key in headers:
                        col_idx = headers.index(key) + 1
                        ws.update_cell(row_idx, col_idx, value)
                return True
        except Exception:
            continue

    return False

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


def get_current_bankroll_from_settled(df: pd.DataFrame, starting_bankroll: float) -> float:
    if df.empty:
        return float(starting_bankroll)

    settled = df[df["outcome"].astype(str).str.lower().isin(["win", "lost", "void"])].copy()

    if settled.empty or settled["bankroll_after"].dropna().empty:
        return float(starting_bankroll)

    return float(settled["bankroll_after"].dropna().iloc[-1])

# --------------------------------------------------
# Load data
# --------------------------------------------------
df = load_data()

current_bankroll = get_current_bankroll_from_settled(
    df, float(st.session_state["starting_bankroll"])
)

# --------------------------------------------------
# Sidebar: new bet input only
# --------------------------------------------------
with st.sidebar:
    st.header("New Bet")

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

    st.caption(f"Gate pass: {'TRUE' if gate_pass else 'FALSE'}")

    c1, c2 = st.columns(2)
    save_bet = c1.button("Save new bet", use_container_width=True)
    clear_form = c2.button("Clear form", use_container_width=True)

    delete_last = st.button("Delete last bet", use_container_width=True)

# --------------------------------------------------
# Actions: sidebar
# --------------------------------------------------
if clear_form:
    st.session_state["reset_form"] = True
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
        stake_amt = current_bankroll * (stake_pct / 100.0) * bet_factor

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
            "result": "",
            "outcome": "open",
            "pnl": "",
            "bankroll_after": "",
        }

        append_row(row)
        st.session_state["reset_form"] = True
        st.success("New bet saved.")
        st.rerun()

# --------------------------------------------------
# KPI calculations
# --------------------------------------------------
settled_df = df[df["outcome"].astype(str).str.lower().isin(["win", "lost", "void"])].copy()
open_df = df[df["outcome"].astype(str).str.lower().eq("open")].copy()

bets_count = len(settled_df)
total_pnl = float(settled_df["pnl"].fillna(0).sum()) if not settled_df.empty else 0.0
avg_odds = (
    float(settled_df["odd"].dropna().mean())
    if not settled_df.empty and settled_df["odd"].dropna().size
    else 0.0
)
total_stake = float(settled_df["stake_amt"].fillna(0).sum()) if not settled_df.empty else 0.0
roi = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0

win_rate = 0.0
if not settled_df.empty:
    settled_binary = settled_df["outcome"].fillna("").str.lower().isin(["win", "lost"])
    if settled_binary.sum() > 0:
        win_rate = (
            settled_df.loc[settled_binary, "outcome"].str.lower().eq("win").mean() * 100.0
        )

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
# Bankroll chart (settled only)
# --------------------------------------------------
st.subheader("Bankroll over time")

if settled_df.empty:
    st.info("No settled bets available yet.")
else:
    chart_df = settled_df[settled_df["bet_id"].notna() & settled_df["bankroll_after"].notna()].copy()
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
# Open bets section
# --------------------------------------------------
st.subheader("Open Bets")

if open_df.empty:
    st.write("No open bets.")
else:
    open_display = open_df.copy()
    open_display["Date"] = pd.to_datetime(open_display["ts"], errors="coerce").dt.strftime("%Y-%m-%d")
    open_display["Match"] = open_display.apply(
        lambda x: format_match(str(x["home"]), str(x["away"])),
        axis=1,
    )
    open_display["Odds"] = open_display["odd"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    open_display["Stake %"] = open_display["stake_pct"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
    open_display["Factor"] = open_display["bet_factor"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    open_display["Stake"] = open_display["stake_amt"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")

    st.dataframe(
        open_display[
            ["bet_id", "Date", "Match", "bet", "Odds", "Stake %", "Factor", "Stake"]
        ].rename(
            columns={
                "bet_id": "Bet#",
                "bet": "Bet",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    open_options = {
        f"Bet #{int(row['bet_id'])} | {row['home']} – {row['away']} | {row['bet']}": int(row["bet_id"])
        for _, row in open_df.iterrows()
        if pd.notna(row["bet_id"])
    }

    selected_label = st.selectbox(
        "Select open bet to settle",
        options=list(open_options.keys()),
        index=0 if open_options else None,
    )

    selected_bet_id = open_options[selected_label]
    selected_row = open_df[open_df["bet_id"] == selected_bet_id].iloc[0]

    s1, s2, s3 = st.columns([2, 2, 1])
    with s1:
        settle_result = st.text_input("Result", key="settle_result")
    with s2:
        settle_outcome = st.selectbox("Settlement outcome", SETTLE_OUTCOMES, key="settle_outcome")
    with s3:
        st.markdown("<br>", unsafe_allow_html=True)
        settle_button = st.button("Settle bet", use_container_width=True)

    if settle_button:
        if not str(settle_result).strip():
            st.error("Please enter a result.")
        else:
            settle_odd = float(selected_row["odd"])
            settle_stake = float(selected_row["stake_amt"])
            pnl = calc_pnl(settle_outcome, settle_stake, settle_odd)

            previous_settled = settled_df[settled_df["bet_id"] < selected_bet_id].copy()
            if previous_settled.empty or previous_settled["bankroll_after"].dropna().empty:
                bankroll_before = float(st.session_state["starting_bankroll"])
            else:
                bankroll_before = float(previous_settled["bankroll_after"].dropna().iloc[-1])

            bankroll_after = bankroll_before + pnl

            updated = update_row_by_bet_id(
                selected_bet_id,
                {
                    "result": settle_result.strip(),
                    "outcome": settle_outcome,
                    "pnl": round(pnl, 2),
                    "bankroll_after": round(bankroll_after, 2),
                },
            )

            if updated:
                st.session_state["settle_result"] = ""
                st.success("Bet settled.")
                st.rerun()
            else:
                st.error("Could not update the selected bet.")

# --------------------------------------------------
# History table (settled only)
# --------------------------------------------------
st.subheader("History")

if settled_df.empty:
    st.write("No settled history yet.")
else:
    history_df = settled_df.copy()
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
