from datetime import datetime
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
GATE_THRESHOLD = 8.0

SHEET_ID = st.secrets["app"]["sheet_id"]
TAB_NAME = st.secrets["app"]["tab_name"]

# --------------------------------------------------
# Lists
# --------------------------------------------------

BET_FACTORS = [1.0, 0.5, 0.25]
SETTLE_OUTCOMES = ["win", "lost", "void"]

LEAGUES = ["2. Bundesliga", "Other"]

TEAMS_2BL = [
    "Hannover 96","Schalke 04","Hertha BSC","Hamburger SV","Fortuna Düsseldorf",
    "Greuther Fürth","Karlsruher SC","1. FC Nürnberg","1. FC Kaiserslautern",
    "SC Paderborn","Eintracht Braunschweig","Magdeburg","Darmstadt",
    "Holstein Kiel","SV Elversberg","Preußen Münster","Arminia Bielefeld","Dynamo Dresden"
]

BET_TYPES = ["1X2","Over/Under","Asian Handicap","BTTS"]

ONE_X_TWO = ["Home","Draw","Away"]

OU_OPTIONS = [
    "Over 0.5","Over 1.5","Over 2.5","Over 3.5","Over 4.5",
    "Under 0.5","Under 1.5","Under 2.5","Under 3.5","Under 4.5"
]

BTTS_OPTIONS = ["Yes","No"]

AHC_OPTIONS = [
    "Home -2.0","Home -1.75","Home -1.5","Home -1.25","Home -1.0",
    "Home -0.75","Home -0.5","Home -0.25","Home 0",
    "Away 0","Away +0.25","Away +0.5","Away +0.75",
    "Away +1.0","Away +1.25","Away +1.5","Away +1.75","Away +2.0"
]

COLUMNS = [
    "bet_id","ts","league","home","away","structural_score_total",
    "gate_pass","bet_factor","bet_type","bet","odd","stake_pct",
    "stake_amt","result","outcome","pnl","bankroll_after"
]

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

    df = df[COLUMNS]

    numeric = [
        "bet_id","structural_score_total","bet_factor",
        "odd","stake_pct","stake_amt","pnl","bankroll_after"
    ]

    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values("bet_id").reset_index(drop=True)
    return df

# --------------------------------------------------
# Append row
# --------------------------------------------------

def append(row):
    sheet().append_row([row.get(c,"") for c in COLUMNS])

# --------------------------------------------------
# Update row
# --------------------------------------------------

def update_row(bet_id, updates):

    ws = sheet()
    data = ws.get_all_values()
    header = data[0]

    id_col = header.index("bet_id")+1

    for i in range(2,len(data)+1):

        val = ws.cell(i,id_col).value

        try:
            if int(float(val)) == bet_id:

                for k,v in updates.items():

                    col = header.index(k)+1
                    ws.update_cell(i,col,v)

                return True
        except:
            pass

    return False

# --------------------------------------------------
# Helper
# --------------------------------------------------

def pnl(outcome,stake,odd):

    if outcome=="win":
        return stake*(odd-1)

    if outcome=="lost":
        return -stake

    return 0

def bet_options(bet_type):

    if bet_type=="1X2":
        return ONE_X_TWO

    if bet_type=="Over/Under":
        return OU_OPTIONS

    if bet_type=="Asian Handicap":
        return AHC_OPTIONS

    if bet_type=="BTTS":
        return BTTS_OPTIONS

# --------------------------------------------------
# Load dataset
# --------------------------------------------------

df = load()

settled = df[df["outcome"].isin(["win","lost","void"])].copy()
openbets = df[df["outcome"]=="open"].copy()

if settled.empty:
    bankroll = STARTING_BANKROLL
else:
    bankroll = settled["bankroll_after"].dropna().iloc[-1]

# --------------------------------------------------
# Sidebar (new bet)
# --------------------------------------------------

with st.sidebar:

    st.header("New Bet")

    league = st.selectbox("League",LEAGUES)

    if league=="2. Bundesliga":

        home = st.selectbox("Home",TEAMS_2BL)
        away = st.selectbox("Away",TEAMS_2BL)

    else:

        home = st.text_input("Home")
        away = st.text_input("Away")

    score = st.number_input("Structural Score",0.0,20.0,8.0,0.5)

    gate = score>=GATE_THRESHOLD

    factor = st.selectbox("Bet Factor",BET_FACTORS)

    bet_type = st.selectbox("Bet Type",BET_TYPES)

    bet = st.selectbox("Bet",bet_options(bet_type))

    odd = st.number_input("Odd",1.01,10.0,1.80,0.01)

    st.caption(f"Gate pass: {'TRUE' if gate else 'FALSE'}")

    save = st.button("Save Bet")

# --------------------------------------------------
# Save new bet
# --------------------------------------------------

if save:

    if home==away or home=="" or away=="":

        st.error("Check teams")

    else:

        next_id = 1 if df.empty else int(df["bet_id"].max())+1

        stake = bankroll*(BASE_STAKE_PCT/100)*factor

        row = {
            "bet_id":next_id,
            "ts":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "league":league,
            "home":home,
            "away":away,
            "structural_score_total":score,
            "gate_pass":gate,
            "bet_factor":factor,
            "bet_type":bet_type,
            "bet":bet,
            "odd":odd,
            "stake_pct":BASE_STAKE_PCT,
            "stake_amt":round(stake,2),
            "result":"",
            "outcome":"open",
            "pnl":"",
            "bankroll_after":""
        }

        append(row)

        st.success("Bet saved")
        st.rerun()

# --------------------------------------------------
# KPIs
# --------------------------------------------------

bets=len(settled)

total_pnl=settled["pnl"].sum() if not settled.empty else 0

roi=(total_pnl/settled["stake_amt"].sum()*100) if bets>0 else 0

avg_odds=settled["odd"].mean() if bets>0 else 0

winrate=(settled["outcome"]=="win").mean()*100 if bets>0 else 0

st.title("Bet Tracker")

c1,c2,c3,c4,c5,c6=st.columns(6)

c1.metric("Bankroll",f"{bankroll:.2f}")
c2.metric("PnL",f"{total_pnl:+.2f}")
c3.metric("ROI",f"{roi:.2f}%")
c4.metric("Win Rate",f"{winrate:.1f}%")
c5.metric("Bets",bets)
c6.metric("Avg Odds",f"{avg_odds:.2f}")

# --------------------------------------------------
# Chart
# --------------------------------------------------

st.subheader("Bankroll")

if not settled.empty:

    chart=settled[["bet_id","bankroll_after"]].dropna()

    chart=chart.set_index("bet_id")

    st.line_chart(chart)

# --------------------------------------------------
# Open bets
# --------------------------------------------------

st.subheader("Open Bets")

if openbets.empty:

    st.write("No open bets")

else:

    openbets["Match"]=openbets["home"]+" - "+openbets["away"]

    st.dataframe(openbets[["bet_id","Match","bet","odd","stake_amt"]])

    options={f"{r.bet_id} {r.home}-{r.away}":r.bet_id for _,r in openbets.iterrows()}

    pick=st.selectbox("Select bet to settle",list(options.keys()))

    bet_id=options[pick]

    result=st.text_input("Result")

    outcome=st.selectbox("Outcome",SETTLE_OUTCOMES)

    settle=st.button("Settle Bet")

    if settle:

        row=openbets[openbets["bet_id"]==bet_id].iloc[0]

        p=pnl(outcome,row["stake_amt"],row["odd"])

        new_bankroll=bankroll+p

        update_row(bet_id,{
            "result":result,
            "outcome":outcome,
            "pnl":round(p,2),
            "bankroll_after":round(new_bankroll,2)
        })

        st.success("Bet settled")
        st.rerun()

# --------------------------------------------------
# History
# --------------------------------------------------

st.subheader("History")

if settled.empty:

    st.write("No history")

else:

    hist=settled.copy()

    hist["Match"]=hist["home"]+" - "+hist["away"]

    hist["Date"]=pd.to_datetime(hist["ts"]).dt.date

    st.dataframe(
        hist[[
            "bet_id","Date","Match","bet",
            "odd","stake_amt","outcome","pnl","bankroll_after"
        ]],
        use_container_width=True
    )
