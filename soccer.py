import streamlit as st
import requests
import pandas as pd
import pytz
import time
import math
from datetime import datetime, timedelta

# --- CONFIGURATION ---
# No more dotenv! We use Streamlit Secrets for security.
API_KEY = st.secrets["FOOTBALL_API_KEY"]
BASE_URL = 'https://api.football-data.org/v4'
HEADERS = {'X-Auth-Token': API_KEY}
LOCAL_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Prediction Constants
MAX_SCORE = 100
WIN_VALUE, DRAW_VALUE, LOSE_VALUE = 2, 1, -1
WIN_WEIGHT, DRAW_WEIGHT, LOSE_WEIGHT = 2, 1, 2

#=====================================
# API HELPER (Prevents 429 Errors)
#=====================================
def call_api(endpoint, params=None):
    """Wait 6.5s before every call to respect the 10-req/min free tier."""
    time.sleep(6.5) 
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 429:
            st.error("Rate limit reached. Waiting 30s...")
            time.sleep(30)
            return call_api(endpoint, params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching {endpoint}: {e}")
        return None

#=====================================
# LOGIC FUNCTIONS
#=====================================
def utc_to_local(utc_date_str: str) -> str:
    if not utc_date_str: return "N/A"
    try:
        utc_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        return utc_dt.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except: return "N/A"

def poisson_pmf(k, lambda_val):
    if k < 0: return 0.0
    return (lambda_val**k * math.exp(-lambda_val)) / math.factorial(k)

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
    record['Average_Goals'] = (record['Home_Goals'] + record['Away_Goals']) / total if total > 0 else 0
    return record

def find_most_probable_score(total_goals, avg_a, avg_b, result):
    if result == 0 and total_goals % 2 != 0:
        total_goals = 2 if total_goals == 1 else max(0, total_goals - 1)
    
    best_prob, best_score = -1.0, (0, 0)
    for gA in range(total_goals + 1):
        gB = total_goals - gA
        if (result == 0 and gA == gB) or (result == 1 and gA > gB) or (result == 2 and gB > gA):
            prob = poisson_pmf(gA, avg_a) * poisson_pmf(gB, avg_b)
            if prob > best_prob:
                best_prob, best_score = prob, (gA, gB)
    return best_score

#=====================================
# STREAMLIT UI
#=====================================
st.set_page_config(page_title="Soccer Match Predictor", layout="wide")
st.title("⚽ Soccer Match Predictor")

# Competition Mapping (Saves API lookups)
country_competitions = {
    "Brazil": "BSA", "England": "PL", "France": "FL1", 
    "Germany": "BL1", "Italy": "SA", "Netherlands": "DED",
    "Portugal": "PPL", "Spain": "PD", "Europe": "CL"
}

selected_country = st.sidebar.selectbox("Select Country/League", list(country_competitions.keys()))

if st.sidebar.button("Run Predictions"):
    comp_code = country_competitions[selected_country]
    
    with st.status(f"Processing {selected_country}...", expanded=True) as status:
        st.write("Getting scheduled matches...")
        sched_data = call_api(f"competitions/{comp_code}/matches", {"status": "SCHEDULED"})
        
        if not sched_data or not sched_data.get('matches'):
            st.warning(f"No upcoming matches for {selected_country}.")
        else:
            st.write("Fetching historical data (this takes a moment)...")
            hist_data = call_api(f"competitions/{comp_code}/matches", {"status": "FINISHED"})
            finished_matches = hist_data.get('matches', []) if hist_data else []

            results = []
            for match in sched_data['matches'][:12]: # Process top 12 matches
                home = match['homeTeam']['shortName']
                away = match['awayTeam']['shortName']
                date = utc_to_local(match['utcDate'])
                
                h_rec = calculate_team_points(finished_matches, home)
                a_rec = calculate_team_points(finished_matches, away)
                
                avg_goals = (h_rec['Average_Goals'] + a_rec['Average_Goals']) / 2
                h_score = MAX_SCORE * h_rec['Home_W_Weight']
                a_score = MAX_SCORE * a_rec['Away_W_Weight']
                
                res_type = 1 if h_score > a_score else 2 if a_score > h_score else 0
                exact = find_most_probable_score(int(round(avg_goals)), h_rec['Average_Goals'], a_rec['Average_Goals'], res_type)
                
                pred_label = "1W" if res_type == 1 else "2W" if res_type == 2 else "X"
                goal_tag = " > 2.5" if avg_goals > 2.5 else " > 1.5" if avg_goals > 1.5 else " < 1.5"

                results.append({
                    "Date": date,
                    "Home Team": home,
                    "Away Team": away,
                    "Predicted Score": f"{exact[0]} - {exact[1]}",
                    "Prediction": f"{pred_label} ({goal_tag})",
                    "Avg Goals": round(avg_goals, 2)
                })
            
            status.update(label="Complete!", state="complete")
            
            st.subheader(f"Results: {selected_country}")
            st.table(pd.DataFrame(results))
