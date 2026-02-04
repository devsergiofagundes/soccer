import os
import requests
from typing import Optional, List, Dict, Tuple, Any
import pytz
import time
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv('FOOTBALL_API_KEY')

LOCAL_TIMEZONE = pytz.timezone('America/Sao_Paulo')
COUNTRY_ID = 0
COMPETITION_ID = 0
MAX_SCORE = 100
WIN_VALUE = 2
DRAW_VALUE = 1
LOSE_VALUE = -1
WIN_WEIGHT = 2
DRAW_WEIGHT = 1
LOSE_WEIGHT = 2

BASE_URL = 'https://api.football-data.org/v4'
HEADERS = {
    'X-Auth-Token': API_KEY,
    'Accept-Encoding': 'gzip, deflate, utf-8'
}

#=====================================
# Convert to LOCAL TIME ZONE
#=====================================
def utc_to_local(utc_date_str: str) -> str:
    if not utc_date_str:
        return "N/A"
    try:
        utc_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        local_dt = utc_dt.astimezone(LOCAL_TIMEZONE)
        return local_dt.strftime("%Y-%m-%d %H:%M %Z") 
    except ValueError:
        return "N/A"

#=====================================
# Get COUNTRY ID
#=====================================
def get_country_id (country_name: str) -> Optional[int]:
    areas_url = f"{BASE_URL}/areas"
    try:
        response = requests.get(areas_url, headers=HEADERS)
        response.raise_for_status() # Error for bad status codes (4xx or 5xx)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
        return None
    except requests.exceptions.JSONDecodeError:
        print("Error: Could not decode JSON response.")
        return None
    for area in data.get('areas', []):
        if area.get('name', '').lower() == country_name.lower():
            return area.get('id')
    print(f"Area ID for '{country_name}' not found.")
    return None

#=====================================
# Get COMPETITION ID
#=====================================
def get_competition_id(country_name: str, competition_name: str) -> Optional[int]:
    area_id = get_country_id(country_name)
    competitions_url = f"{BASE_URL}/competitions?areas={area_id}"
    try:
        response = requests.get(competitions_url, headers=HEADERS)
        response.raise_for_status()
        competitions_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching competitions: {e}")
        return None
    for competition in competitions_data.get('competitions', []):

        if competition.get('name').lower() == competition_name.lower():
            return competition.get('id')

    print(f"Error: Competition '{competition_name}' not found in the API response.")
    return None

#=========================================
# Get COUNTRY COMPETITION MATCHES FINISHED
#=========================================
def get_finished_matches(comp_id: int,
                         days_past: Optional[int] = 365
) -> Optional[List[Dict[str, Any]]]:
    today = datetime.now(LOCAL_TIMEZONE)
    start_date = today - timedelta(days=days_past)
    date_from = start_date.strftime("%Y-%m-%d")
    date_to = today.strftime("%Y-%m-%d") # Use today as the end date
    url = f"{BASE_URL}/competitions/{comp_id}/matches"
    params = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'status': 'FINISHED'
        # The API also supports 'limit' and 'offset' for pagination if needed
    }
#    print(f"\nSearching for finished matches in '{comp_id}' ({COUNTRY_ID})")
#    print(f"  > Date Range: {date_from} to {date_to}")
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        matches = data.get('matches', [])
#        print(f"Successfully retrieved {len(matches)} finished matches.")
        return matches
    except requests.exceptions.RequestException as e:
        print(f"Matches API request error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
 
#==========================================
# Get COUNTRY COMPETITION MATCHES SCHEDULED
#==========================================
def get_scheduled_matches(comp_id: int,
                         days_past: Optional[int] = 365
) -> Optional[List[Dict[str, Any]]]:
    today = datetime.now(LOCAL_TIMEZONE)
    start_date = today
    end_date = today + timedelta(days=days_past)
    date_from = start_date.strftime("%Y-%m-%d")
    date_to = end_date.strftime("%Y-%m-%d") # Use today as the end date
    url = f"{BASE_URL}/competitions/{comp_id}/matches"
    params = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'status': 'SCHEDULED,LIVE,IN_PLAY,PAUSED'
        # The API also supports 'limit' and 'offset' for pagination if needed
    }
#    print(f"\nSearching for scheduled matches in '{comp_id}' ({COUNTRY_ID})")
#    print(f"  > Date Range: {date_from} to {date_to}")
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        matches = data.get('matches', [])
#        print(f"Successfully retrieved {len(matches)} scheduled matches.")
        return matches
    except requests.exceptions.RequestException as e:
        print(f"Matches API request error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

#==========================================
# Get POINTS from Team in last competitions
#==========================================
def calculate_team_points(matches: list, team_name: str) -> dict:
    record = {
        "Home_Win": 0, "Home_Draw": 0, "Home_Lose": 0, "Home_Total": 0,
        "Away_Win": 0, "Away_Draw": 0, "Away_Lose": 0, "Away_Total": 0,
        "Game_Goals": 0, "Home_Goals": 0, "Away_Goals": 0,
        "Home_W_Weight": 0, "Away_W_Weight": 0,
        "Home_WD_Weight": 0, "Away_WD_Weight": 0,
        "Score": 0, "Average_Goals": 0
    }
    for match in matches:
        home_team = match.get('homeTeam', {}).get('shortName')
        away_team = match.get('awayTeam', {}).get('shortName')
        score_full_time = match.get('score', {}).get('fullTime')
        if not score_full_time or (team_name not in [home_team, away_team]):
            continue
        home_score = score_full_time.get('home')
        away_score = score_full_time.get('away')
        if not isinstance(home_score, int) or not isinstance(away_score, int):
            continue
        is_home_game = (home_team == team_name)
        result = ''
        score = DRAW_VALUE;
        score_weight = 1
        if home_score == away_score:
            result = 'Draw'
        elif is_home_game:
            if home_score > away_score:
                result = 'Win'
                score = WIN_VALUE
            else:
                result = 'Lose'
                score = LOSE_VALUE
                score_weight = LOSE_WEIGHT
        else: # is_away_game
            if away_score > home_score:
                result = 'Win'
                score = WIN_VALUE
                score_weight = WIN_WEIGHT
            else:
                result = 'Lose'
                score = LOSE_VALUE
#        record['Score'] += (score * score_weight)
        data = match.get('score', {})
        fulltime = data.get('fullTime', {})
        home_goals = fulltime.get('home')
        away_goals = fulltime.get('away')
        record['Game_Goals'] += home_goals + away_goals
        if is_home_game:
            record[f'Home_{result}'] += 1
            record['Home_Total'] += 1
            record['Home_Goals'] +=  home_goals
            record['Away_Goals'] +=  away_goals
        else:
            record[f'Away_{result}'] += 1
            record['Away_Total'] += 1
            record['Home_Goals'] +=  away_goals
            record['Away_Goals'] +=  home_goals
    total_games = record['Home_Total'] + record['Away_Total']
    record['Home_W_Weight'] = record['Home_Win'] / record['Home_Total'] if record['Home_Total'] > 0 else 0
    record['Away_W_Weight'] = record['Away_Win'] / record['Away_Total'] if record['Away_Total'] > 0 else 0
    record['Home_WD_Weight'] = (record['Home_Win'] + record['Home_Draw']) / record['Home_Total'] if record['Home_Total'] > 0 else 0
    record['Away_WD_Weight'] = (record['Away_Win'] + record['Away_Draw']) / record['Away_Total'] if record['Away_Total'] > 0 else 0
    average_goals = (record['Home_Goals'] + record['Away_Goals']) / total_games
    if is_home_game and record['Home_Total'] > 0:
        average_goals = record["Home_Goals"] / record['Home_Total']
    elif not is_home_game and record['Away_Total'] > 0:
        average_goals = record["Away_Goals"] / record['Away_Total']
    else:
        average_goals = (record['Home_Goals'] + record['Away_Goals']) / total_games
    record['Average_Goals'] = average_goals
    return record

#==========================================
# Get Historical matchs between 2 teams
#==========================================
def get_confrontation_matches(matches: list, team_a: str, team_b: str, last_x_days: int = 365) -> dict:
    # Manually filter matches for H2H between team_a and team_b
    h2h_matches = [
        match for match in matches 
        if (match.get('homeTeam', {}).get('shortName') == team_a and match.get('awayTeam', {}).get('shortName') == team_b) or
           (match.get('homeTeam', {}).get('shortName') == team_b and match.get('awayTeam', {}).get('shortName') == team_a)
    ]
    if not h2h_matches:
        return None
    return h2h_matches

#==========================================
# Get Historical matchs between 2 teams
#==========================================
def get_confrontation_historical(h2h_mat: list, team_a: str, team_b: str) -> dict:
    team_a_score = 0
    team_a_win = 0
    team_b_score = 0
    team_b_win = 0
    total_matches = 0
    h2h_matches = get_confrontation_matches(h2h_mat, team_a, team_b)
    if not h2h_matches:
        return {"Team_A_Score": 0, "Team_A_Weight": 1, "Team_B_Score": 0, "Team_B_Weight": 1, "Total_Matches": 0}
    for match in h2h_matches:
        home_team = match.get('homeTeam', {}).get('shortName')
        away_team = match.get('awayTeam', {}).get('shortName')
        score_full_time = match.get('score', {}).get('fullTime')
        if not score_full_time or not isinstance(score_full_time.get('home'), int) or not isinstance(score_full_time.get('away'), int):
            continue
        home_score = score_full_time.get('home')
        away_score = score_full_time.get('away')
        total_matches += 1
        # Determine winner/draw and apply points/weights for both teams
        # Draw
        if home_score == away_score:
            score = DRAW_VALUE * DRAW_WEIGHT
            team_a_score += score
            team_b_score += score
        # Home Team Wins
        elif home_score > away_score:
            if home_team == team_a:
                team_a_score += WIN_VALUE    # Team A (Home) Win
                team_b_score += LOSE_VALUE    # Team B (Away) Lose
                team_a_win += 1
            else: # home_team == team_b
                team_b_score += WIN_VALUE     # Team B (Home) Win
                team_a_score += LOSE_VALUE    # Team A (Away) Lose
                team_b_win += 1
        # Away Team Wins
        elif away_score > home_score:
            if away_team == team_a:
                team_a_score += WIN_VALUE * WIN_WEIGHT    # Team A (Away) Win
                team_b_score += LOSE_VALUE * LOSE_WEIGHT # Team B (Home) Lose
                team_a_win += 1
            else: # away_team == team_b
                team_b_score += WIN_VALUE * WIN_WEIGHT    # Team B (Away) Win
                team_a_score += LOSE_VALUE * LOSE_WEIGHT # Team A (Home) Lose
                team_b_win += 1
    team_a_weight = 1
    team_b_weight = 1
    if total_matches > 0:
        team_a_weight = team_a_win / total_matches
        team_b_weight = team_b_win / total_matches
#    if team_a == "Man United" and team_b == "Bournemouth":
#        print (f"{team_a} {team_a_weight} | {team_b} {team_b_weight}")
#        print (f"{team_a} {team_a_win} | {team_b} {team_b_win}")
#    if team_a_win == total_matches:
#        favorite_weight = 1
#    if team_b_win == total_matches:
#        favorite_weight = 2
    return {
        "Team_A_Score": team_a_score,
        "Team_A_Weight" : team_a_weight,
        "Team_B_Score": team_b_score,
        "Team_B_Weight" : team_b_weight,
        "Total_Matches": total_matches,
    }

#==========================================
# Get Indirect matchs between 2 teams
#==========================================
def get_confrontation_indirect(matches: list, team_a: str, team_b: str) -> tuple[float, float]:
    team_a_weight = 0
    team_a_win = 0
    team_a_win_home = 0
    team_b_weight = 0
    team_b_win = 0
    team_b_win_away = 0
    total_matches = 0
    total_matches_home = 0
    total_matches_away = 0
#    print (f"{team_a} x {team_b}")
    for match in matches:
        home_team = match.get('homeTeam', {}).get('shortName')
        away_team = match.get('awayTeam', {}).get('shortName')
        score_full_time = match.get('score', {}).get('fullTime')
        if not score_full_time or (team_a not in [home_team, away_team]):
            continue
        home_score = score_full_time.get('home')
        away_score = score_full_time.get('away')
        if not score_full_time or not isinstance(score_full_time.get('home'), int) or not isinstance(score_full_time.get('away'), int):
            continue
        if team_a == home_team:
            search_indirect = away_team
        else:
            search_indirect = home_team
        if team_b == search_indirect:
            continue
        for match2 in matches:
            home_team2 = match2.get('homeTeam', {}).get('shortName')
            away_team2 = match2.get('awayTeam', {}).get('shortName')
            score_full_time2 = match2.get('score', {}).get('fullTime')
            if team_a in [home_team2, away_team2]:
                continue
            if not score_full_time2 or team_b not in [home_team2, away_team2] or search_indirect not in [home_team2, away_team2]:
                continue
            home_score2 = score_full_time2.get('home')
            away_score2 = score_full_time2.get('away')
            if not score_full_time2 or not isinstance(score_full_time2.get('home'), int) or not isinstance(score_full_time2.get('away'), int):
                continue
            if team_a == home_team:
                total_matches_home += 1
                if home_score > away_score:
                    team_a_win += 1
                    team_a_win_home += 1
            else:
                if away_score > home_score:
                    team_a_win += 1
            if team_b == home_team2:
                if home_score2 > away_score2:
                    team_b_win += 1
            else:
                total_matches_away += 1
                if away_score2 > home_score2:
                    team_b_win += 1
                    team_b_win_away += 1
            total_matches += 1
#            print (f"Jogo {total_matches}")
#            print (f"{home_score}x{away_score}  {home_team} x {away_team}")
#            print (f"{home_score2}x{away_score2}  {home_team2} x {away_team2}")
            break
    wa = team_a_win / total_matches if total_matches > 0 else 1.0
    wb = team_b_win / total_matches if total_matches > 0 else 1.0
    wa_home = team_a_win_home / total_matches_home if total_matches_home > 0 else 1.0
    wb_away = team_b_win_away / total_matches_away if total_matches_away > 0 else 1.0
    wa_home *= wa
    wb_away *= wb
    
#    print (f"Jogo {total_matches}")
#    print (f"{team_a_win} {team_a} x {team_b} {team_b_win}")
#    print (f"{team_a_win_home}/{total_matches_home} {team_a} x {team_b} {team_b_win_away}/{total_matches_away}")
#    print (f"{wa_home} {team_a} x {team_b} {wb_away}")
    if total_matches == 0 or (team_a_win == 0 and team_b_win == 0):
        return 1,1
    return wa,wb

def poisson_pmf(k: int, lambda_val: float) -> float:
    """
    Calculates the Poisson Probability Mass Function (PMF).
    P(X=k) = (lambda^k * e^(-lambda)) / k!
    """
    if k < 0:
        return 0.0
    return (lambda_val**k * math.exp(-lambda_val)) / math.factorial(k)

def find_most_probable_score(
    total_goals: int,
    team_a_avg_goals: float,
    team_b_avg_goals: float,
    result: int  # New parameter: 0=Draw, 1=Team A Win, 2=Team B Win
) -> tuple[int, int]:
    # 2. === ADJUSTMENT LOGIC (The core change you requested) ===
    if result == 0 and total_goals % 2 != 0:
        if total_goals == 1:
            # Change 1 to 2 (e.g., to allow 1-1 instead of an impossible 0-1/1-0)
            total_goals = 2 
        else:
            # Change 3 to 2, 5 to 4, etc., by subtracting 1.
            total_goals -= 1
    if total_goals < 0 or not isinstance(total_goals, int):
        raise ValueError("total_goals must be a non-negative integer.")
    if result not in [0, 1, 2]:
        raise ValueError("result must be 0 (Draw), 1 (Team A Win), or 2 (Team B Win).")
    max_probability = -1.0
    most_probable_score = (-1, -1)  # Initialize to an invalid score
    # Iterate through all possible scores (i, j) where i + j = total_goals
    for goals_A in range(total_goals + 1):
        goals_B = total_goals - goals_A
        # 1. --- Check if the current score matches the required RESULT ---
        is_valid_result = False
        if result == 0 and goals_A == goals_B:
            is_valid_result = True  # Draw required and achieved
        elif result == 1 and goals_A > goals_B:
            is_valid_result = True  # Team A win required and achieved
        elif result == 2 and goals_B > goals_A:
            is_valid_result = True  # Team B win required and achieved
        if not is_valid_result:
            continue  # Skip this score, it doesn't match the required result
        # 2. --- Calculate Probability for Valid Scores ---
        # Calculate the probability of Team A scoring goals_A goals
        prob_A = poisson_pmf(goals_A, team_a_avg_goals)
        # Calculate the probability of Team B scoring goals_B goals
        prob_B = poisson_pmf(goals_B, team_b_avg_goals)
        current_probability = prob_A * prob_B
        # 3. --- Update Most Probable Score ---
        if current_probability > max_probability:
            max_probability = current_probability
            most_probable_score = (goals_A, goals_B)
        elif current_probability == max_probability:
            # Tie-breaker logic (Keep the one with a smaller goal difference)
            old_diff = abs(most_probable_score[0] - most_probable_score[1])
            new_diff = abs(goals_A - goals_B)
            # For DRAW (result=0), tie-breaker is less relevant as diff is 0,
            # but it is good practice to keep the goal difference as small as possible.
            if new_diff < old_diff:
                most_probable_score = (goals_A, goals_B)
    # Handle the case where no valid score could be found (e.g., total_goals=1 and result=0)
    if most_probable_score == (-1, -1):
        # This should only happen for impossible combinations (e.g., Draw with odd total goals)
        # We can return (0, 0) or handle the error, but for practical score prediction,
        # we might default to the required result with the smallest possible score.
        print("Warning: No score found that matches constraints. Returning default.")
        if result == 0 and total_goals % 2 == 0:
            return (total_goals // 2, total_goals // 2)
        elif result == 1:
            return (total_goals, 0) # Default A win
        elif result == 2:
            return (0, total_goals) # Default B win
        return (0, 0) # Default Fallback
    return most_probable_score



#==========================================
# Get Match prediction
#==========================================
def get_match_prediction(home_score: int, away_score: int, home_team_name: str, away_team_name: str) -> str:
    # 1. Check for small difference (absolute value of difference)
    score_difference = abs(home_score - away_score)
#    if score_difference <= 10:
#        return "DRAW (Scores close)"
    # Determine the leading team and scores
    if home_score > away_score:
        leader_score = home_score
        follower_score = away_score
        leader_team = "1" # leader_team = home_team_name
    elif away_score > home_score:
        leader_score = away_score
        follower_score = home_score
        leader_team = "2" # leader_team = away_team_name
    else:
        # Should be caught by the score_difference <= 10 check, but safe guard.
        return "(X)"
    # 2. Check for overwhelming lead (Score > 50% of opponent's score)
    if follower_score == 0:
           # If follower score is 0, any lead is considered a strong lead
           return f"({leader_team}W)"
    cinqperc = follower_score  * 3
    if leader_score > (cinqperc):
        return f"({leader_team}W)"
    # 3. Otherwise, prediction is Win or Draw for the leading team
    return f"({leader_team}W X)"

def get_competition_teams():
    url = f"{BASE_URL}/competitions/{COMPETITION_ID}/teams"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status() 
        data = response.json()
        return data
    except requests.exceptions.HTTPError as errh:
        # Handle specific HTTP errors (401 Unauthorized, 403 Forbidden, 404 Not Found)
        print(f"HTTP Error: {errh}")
        print("Check if your API Key is correct and if you have access to this competition/API version.")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"An error occurred: {err}")
    return None


def print_match_results(matches: Optional[List[Dict[str, Any]]]):
    DATE_WIDTH = 17
    TEAM_WIDTH = 15
    SCORE_WIDTH = 9
    if not matches:
        print("No matches to display.")
        return
    # --- Header ---
    header_date = "DATE".ljust(DATE_WIDTH)
    header_home = "HOME TEAM".ljust(TEAM_WIDTH)
    header_score = "SCORE".center(SCORE_WIDTH)
    header_away = "AWAY TEAM".ljust(TEAM_WIDTH)
    print("\n" + "=" * (DATE_WIDTH + TEAM_WIDTH * 2 + SCORE_WIDTH + 4))
    print(f"{header_date} | {header_home} | {header_score} | {header_away}")
    print("-" * (DATE_WIDTH + TEAM_WIDTH * 2 + SCORE_WIDTH + 4))
    # --- Data Rows ---
    for match in matches:
        # 1. Extract Teams (safely)
        home_team = match.get('homeTeam', {}).get('shortName', 'N/A')
        away_team = match.get('awayTeam', {}).get('shortName', 'N/A')
        # 2. Extract and Format Score
        full_time_score = match.get('score', {}).get('fullTime')
        if full_time_score:
            home_score = full_time_score.get('home', 'X')
            away_score = full_time_score.get('away', 'X')
            if home_score is None:
                home_score = 'X'
            if away_score is None:
                away_score = 'X'
            score_str = f"{home_score} - {away_score}"
        else:
            score_str = "N/A"
        # 3. Format Date
        match_date_str = "N/A"
        match_date_utc = utc_to_local(match.get('utcDate'))
        if match_date_utc:
            try:
                # Parse the ISO date string (e.g., "2023-11-29T23:30:00Z")
                dt_obj = datetime.fromisoformat(match_date_utc.replace('Z', '+00:00'))
                match_date_str = dt_obj.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass 
        # 4. Print Aligned Row
        date_col = match_date_str.ljust(DATE_WIDTH)
        home_col = home_team[:TEAM_WIDTH].ljust(TEAM_WIDTH) # Truncate long names
        if match.get('status') in ('LIVE', 'IN_PLAY'):
            score_str = score_str + ' L'
        score_col = score_str.center(SCORE_WIDTH)
        away_col = away_team[:TEAM_WIDTH].ljust(TEAM_WIDTH)
        print(f"{date_col} | {home_col} | {score_col} | {away_col}")
    print("=" * (DATE_WIDTH + TEAM_WIDTH * 2 + SCORE_WIDTH + 4) + "\n")


# --- Example Usage ---
if __name__ == '__main__':
    #------ Initialize ----------
    country_competitions = {
        "Brazil": "Campeonato Brasileiro Série A",
        "England": "Premier League",
        "France": "Ligue 1",
        "Germany": "Bundesliga",
        "Italy": "Serie A",
        "Netherlands": "Eredivisie",
        "Portugal": "Primeira Liga",
        "Spain": "Primera Division",
        "Europe": "UEFA Champions League",
    }
    for country, competition in country_competitions.items():
        COUNTRY_ID = get_country_id(country)
        time.sleep(6.5)
        COMPETITION_ID = get_competition_id(country, competition)
        time.sleep(6.5)
        SCHEDULED_MATCHS = get_scheduled_matches(COMPETITION_ID,30)
        if not SCHEDULED_MATCHS:
            print(f"  (!) No upcoming matches found for {competition}. Skipping...")
            continue
        time.sleep(6.5)
        FINISHED_MATCHS = get_finished_matches(COMPETITION_ID,365)
        if not FINISHED_MATCHS:
            print(f"  (!) No historical data found for {competition}. Cannot predict.")
            continue
        time.sleep(6.5)
        COMPETITION_TEAMS = get_competition_teams()
        time.sleep(6.5)
#       COMPETITION_TEAMS_LIST = COMPETITION_TEAMS['teams']
        # Iterate through scheduled matches to make a prediction
        prediction_list = []
        for match in SCHEDULED_MATCHS:
            home_team = match.get('homeTeam', {}).get('shortName')
            away_team = match.get('awayTeam', {}).get('shortName')
            match_date = utc_to_local(match.get('utcDate', ''))[:16]
            
            if match_date:
                try:
                    # Parse the ISO date string (e.g., "2023-11-29T23:30:00Z")
                    dt_obj = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                    match_date_str = dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass 
        
            # Calculate 'Season Score' for each team
            home_team_record = calculate_team_points(FINISHED_MATCHS, home_team)
            away_team_record = calculate_team_points(FINISHED_MATCHS, away_team)
            avg_gols_a = home_team_record.get('Average_Goals', 0)
            avg_gols_b = away_team_record.get('Average_Goals', 0)
            avg_goals = (avg_gols_a + avg_gols_b) / 2
            
            home_w_score = MAX_SCORE * home_team_record.get('Home_W_Weight', 0) * home_team_record.get('Away_W_Weight', 0)
            home_wd_score = MAX_SCORE * home_team_record.get('Home_WD_Weight', 0)
            away_w_score = MAX_SCORE * away_team_record.get('Away_W_Weight', 0) *  away_team_record.get('Home_W_Weight', 0)
            away_wd_score = MAX_SCORE * away_team_record.get('Away_WD_Weight', 0)
        
            # Retrieve the H2H Score
            h2h_scores = get_confrontation_historical(FINISHED_MATCHS, home_team, away_team)
            h2h_scores_indirect = get_confrontation_indirect(FINISHED_MATCHS, home_team, away_team)
            
        
            # COMBINE SCORES: Add H2H Score to Season Score
            home_score = h2h_scores['Team_A_Weight'] * home_w_score * h2h_scores_indirect[0]
            away_score = h2h_scores['Team_B_Weight'] * away_w_score * h2h_scores_indirect[1]

        
#            print(f"-> Analyzing {home_team} vs {away_team} on {match_date}:")
#            print(f"   Season Scores (H/A): {home_score} / {away_score}")
#            print(f"   H2H Scores (H/A): {h2h_scores['Team_A_Score']} / {h2h_scores['Team_B_Score']}")
#            print(f"   H2H Weight (H/A): {h2h_scores['Team_A_Weight']} / {h2h_scores['Team_B_Weight']}")
#            print(f"   Combined Scores (H/A): {home_score} / {away_score}")
        
            high_score = max(home_score,away_score)
#            home_score += high_score * h2h_scores['Team_A_Weight']
#            away_score += high_score * h2h_scores['Team_B_Weight']
        
            # Call the function for prediction
            prediction = get_match_prediction(
                home_score, 
                away_score, 
                home_team, 
                away_team,
            )
            tmp_res = 0
            if home_score > away_score:
                tmp_res = 1
            elif away_score > home_score:
                tmp_res = 2
            exact_total_goals = int(round(avg_goals))
            exact_score = find_most_probable_score(exact_total_goals, avg_gols_a, avg_gols_b,tmp_res)
            finalscore = f"{exact_score[0]} - {exact_score[1]}"
            prediction = finalscore + prediction
        
            prediction_list.append({
                'Date': match_date_str,
                'HomeTeam': home_team,
                'AwayTeam': away_team,
                'Prediction': prediction,
                'Avg_Goals': avg_goals,
                'Home_Score': home_score,
                'Away_Score': away_score
            })
        # Sort the list by Date in ascending order
        prediction_list_sorted = sorted(prediction_list, key=lambda x: x['Date'])

        # Print the sorted listing
        print(f"\n--- FINAL PREDICTIONS, {country}, {competition} ---")
        print(f"{'Date':<18} | {'Home Team':<22} | {'Away Team':<22} | {'Prediction':<25}")
        print("-" * 94)

        av_goals = " < 1.5"
        for p in prediction_list_sorted:
#            p['HomeTeam'] += f" ({p['Home_Score']:.2f}) ({p['Away_Score']:.2f})"
            if p['Avg_Goals'] > 3.5 and p['Avg_Goals'] <= 4.5:
                av_goals = " > 3.5"
            elif p['Avg_Goals'] > 2.5 and p['Avg_Goals'] <= 3.5:
                av_goals = " > 2.5"
            elif p['Avg_Goals'] > 1.5 and p['Avg_Goals'] <= 2.5:
                av_goals = " > 1.5"
                
            p['Prediction'] += av_goals
            print(
                f"{p['Date']:<18} | "
                f"{p['HomeTeam']:<22} | "
                f"{p['AwayTeam']:<22} | "
                f"{p['Prediction']:<25}"
            )
    
        print("==============================================")

