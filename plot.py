import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import time

# Function to fetch data from the endpoint with added timeout and retry logic
def fetch_data(max_retries=3, retry_delay=2):
    url = "https://irk0p9p6ig.execute-api.us-east-1.amazonaws.com/prod/players"
    params = {
        'type': 'ostracize',
        'quantity': 10,
        'startIndex': 0,
        'reversed': 'true'
    }
    for attempt in range(max_retries):
        try:
            current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{current_timestamp} - Attempting to fetch data (Attempt {attempt + 1})...")
            start_time = time.time()
            response = requests.get(url, params=params, timeout=5)  # Added timeout of 5 seconds
            response.raise_for_status()  # Raise an error for bad status codes
            duration = time.time() - start_time
            print(f"{current_timestamp} - Data fetched successfully in {duration:.2f} seconds")
            try:
                data = response.json()
                return data
            except ValueError:
                print(f"{current_timestamp} - Error parsing JSON!")
                return None
        except requests.exceptions.RequestException as e:
            print(f"{current_timestamp} - Error fetching data: {e}")
            if attempt < max_retries - 1:
                print(f"{current_timestamp} - Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"{current_timestamp} - Max retries reached. Skipping this fetch.")
                return None

# Initialize variables
data_dict = {}
last_save_time = datetime.now()

# Parameters
fetch_interval = 1      # Fetch data every 1 second
save_interval = 600     # Save graph every 10 minutes

while True:
    current_time = datetime.now()
    
    # Reset the graph at xx:00:01 of every hour
    if current_time.minute == 0 and current_time.second == 1:
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - Resetting data for the new hour...")
        data_dict = {}
        last_save_time = current_time

    # Fetch data
    data = fetch_data()
    if data and 'players' in data:
        players = data['players']
        for player in players:
            username = player.get('username')
            score = player.get('score')
            if username and score is not None:
                if username not in data_dict:
                    data_dict[username] = {'time': [], 'score': []}
                data_dict[username]['time'].append(current_time)
                data_dict[username]['score'].append(score)
    else:
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - No valid player data found.")
    
    # Save the graph at specified intervals
    if (current_time - last_save_time).total_seconds() >= save_interval:
        plt.figure(figsize=(10, 6))
        
        # Sort players by their latest score and pick the top 5
        sorted_players = sorted(data_dict.items(), key=lambda x: x[1]['score'][-1], reverse=True)[:5]
        
        for username, values in sorted_players:
            plt.plot(values['time'], values['score'], label=username)
        
        plt.xlabel('Time (HH:MM)')
        plt.ylabel('Score')
        plt.title('Top 5 Player Scores Over Time')
        plt.legend(loc='upper right', fontsize='small')
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gcf().autofmt_xdate()
        
        file_name = f'player_scores_{current_time.strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(file_name)
        plt.close()
        
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - Graph saved as {file_name}")
        last_save_time = current_time
    
    # Wait for the next fetch
    time.sleep(fetch_interval)
