import os
import requests
import streamlit as st
import pandas as pd
import pytz
import time
import math
from datetime import datetime, timedelta

# --- CONFIG & SECRETS ---
# Ensure you set FOOTBALL_API_KEY in your Streamlit Cloud Secrets dashboard!
API_KEY = st.secrets["FOOTBALL_API_KEY"]
BASE_URL = 'https://api.football-data.org/v4'
HEADERS = {'X-Auth-Token': API_KEY}
LOCAL_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Prediction Weights
MAX_SCORE = 100
WIN_VALUE, DRAW_VALUE, LOSE_VALUE = 2, 1, -1
WIN_WEIGHT, DRAW_WEIGHT, LOSE_WEIGHT = 2, 1, 2

# --- API RATE LIMITER ---
def call_api(url, params=None):
    """Centralized API caller to prevent 429 errors."""
    # The free tier is VERY strict. 6 seconds between EVERY call is safest.
    time.sleep(6.5) 
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 429:
            st.error("Rate limit hit (429). Waiting 30 seconds...")
            time.sleep(30)
            return call_api(url, params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

# --- HELPER FUNCTIONS ---
def utc_to_local(utc_date_str: str) -> str:
    if not utc_date_str: return "N/A"
    try:
        utc_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        return utc_dt.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except: return "N/A"

def poisson_pmf(k, lambda_val):
    if k < 0: return 0.0
    return (lambda_val**k * math.exp(-lambda_val)) / math.factorial(k)

# (Keeping your core logic functions mostly the same, but removing internal prints)
def calculate_team_points(matches, team_name):
    record = {
        "Home_Win": 0, "Home_Draw": 0, "Home_Lose": 0, "Home_Total": 0,
        "Away_Win": 0, "Away_Draw": 0, "Away_Lose": 0, "Away_Total": 0,
        "Home_Goals": 0, "Away_Goals": 0, "Average_Goals": 0
    }
    for match in matches:
        home_team = match.get('homeTeam', {}).get('shortName')
        away_team = match.get('awayTeam', {}).get('shortName')
        score = match.get('score', {}).get('fullTime')
        if not score or team_name not in [home_team, away_team]: continue
        
        h_g, a_g = score.get('home'), score.get('away')
        if h_g is None or a_g is None: continue
        
        is_home = (home_team == team_name)
        res = "Win" if (is_home and h_g > a_g) or (not is_home and a_g > h_g) else \
              "Draw" if h_g == a_g else "Lose"
        
        prefix = "Home" if is_home else "Away"
        record[f"{prefix}_{res}"] += 1
        record[f"{prefix}_Total"] += 1
        record["Home_Goals"] += h_g if is_home else a_g
        record["Away_Goals"] += a_g if is_home else h_g

    total = record['Home_Total'] + record['Away_Total']
    record['Home_W_Weight'] = record['Home_Win'] / record['Home_Total'] if record['Home_Total'] > 0 else 0
    record['Away_W_Weight'] = record['Away_Win'] / record['Away_Total'] if record['Away_Total'] > 0 else 0
    record['Home_WD_Weight'] = (record['Home_Win'] + record['Home_Draw']) / record['Home_Total'] if record['Home_Total'] > 0 else 0
    record['Away_WD_Weight'] = (record['Away_Win'] + record['Away_Draw']) / record['Away_Total'] if record['Away_Total'] > 0 else 0
    record['Average_Goals'] = (record['Home_Goals'] + record['Away_Goals']) / total if total > 0 else 0
    return record

# --- UI PREDICTION WRAPPERS ---
def find_most_probable_score(total_goals, avg_a, avg_b, result):
    # Logic remains same as your original
    if result == 0 and total_goals % 2 != 0:
        total_goals = 2 if total_goals == 1 else total_goals - 1
    
    best_prob = -1
    best_score = (0, 0)
    for gA in range(total_goals + 1):
        gB = total_goals - gA
        if (result == 0 and gA == gB) or (result == 1 and gA > gB) or (result == 2 and gB > gA):
            prob = poisson_pmf(gA, avg_a) * poisson_pmf(gB, avg_b)
            if prob > best_prob:
                best_prob, best_score = prob, (gA, gB)
    return best_score

# --- MAIN STREAMLIT APP ---
st.set_page_config(page_title="Football Predictor", layout="wide")
st.title("⚽ Soccer Match Predictor")

# Sidebar for League Selection to save API calls
leagues = {
    "Brazil": "BSA", "England": "PL", "France": "FL1", 
    "Germany": "BL1", "Italy": "SA", "Spain": "PD", "Europe": "CL"
}
selected_league = st.sidebar.selectbox("Select League", list(leagues.keys()))

if st.sidebar.button("Run Prediction"):
    comp_code = leagues[selected_league]
    
    with st.status(f"Analyzing {selected_league}...", expanded=True) as status:
        # 1. Fetch Scheduled
        st.write("Fetching upcoming matches...")
        sched_data = call_api(f"{BASE_URL}/competitions/{comp_code}/matches", {"status": "SCHEDULED"})
        
        if not sched_data or not sched_data.get('matches'):
            st.warning("No matches found.")
        else:
            # 2. Fetch Historical for Calculation
            st.write("Fetching historical results...")
            hist_data = call_api(f"{BASE_URL}/competitions/{comp_code}/matches", {"status": "FINISHED"})
            finished_matches = hist_data.get('matches', [])

            predictions = []
            for match in sched_data['matches'][:10]: # Limit to top 10 to avoid excessive processing
                home = match['homeTeam']['shortName']
                away = match['awayTeam']['shortName']
                date = utc_to_local(match['utcDate'])
                
                # Calculate scores
                h_rec = calculate_team_points(finished_matches, home)
                a_rec = calculate_team_points(finished_matches, away)
                
                avg_goals = (h_rec['Average_Goals'] + a_rec['Average_Goals']) / 2
                h_score = MAX_SCORE * h_rec['Home_W_Weight']
                a_score = MAX_SCORE * a_rec['Away_W_Weight']
                
                res_type = 1 if h_score > a_score else 2 if a_score > h_score else 0
                exact = find_most_probable_score(int(round(avg_goals)), h_rec['Average_Goals'], a_rec['Average_Goals'], res_type)
                
                pred_label = "1W" if res_type == 1 else "2W" if res_type == 2 else "X"
                
                predictions.append({
                    "Date": date,
                    "Match": f"{home} vs {away}",
                    "Pred. Score": f"{exact[0]} - {exact[1]}",
                    "Result": pred_label,
                    "Avg Goals": round(avg_goals, 2)
                })
            
            status.update(label="Analysis Complete!", state="complete", expanded=False)
            
            # --- DISPLAY TABLE ---
            st.subheader(f"Predictions for {selected_league}")
            df = pd.DataFrame(predictions)
            st.dataframe(df, use_container_width=True, hide_index=True)
