import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# Function to fetch data from the endpoint with added timeout and retry logic
def fetch_data(max_retries=3, retry_delay=2):
    url = "https://irk0p9p6ig.execute-api.us-east-1.amazonaws.com/prod/players"
    params = {
        'type': 'ostracize',
        'quantity': 50,  # Fetch data for top 50 players
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
fetch_interval = 0.4  # Fetch data every 0.5 seconds

# Calculate the end of the current hour
current_time = datetime.now()
end_of_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

while True:
    current_time = datetime.now()

    # Check if it's past the end of the current hour
    if current_time >= end_of_hour:
        fig = go.Figure()

        # Sort players by their latest score and pick the top 50
        sorted_players = sorted(data_dict.items(), key=lambda x: x[1]['score'][-1], reverse=True)[:50]

        for username, values in sorted_players:
            fig.add_trace(go.Scatter(
                x=values['time'], 
                y=values['score'], 
                mode='lines+markers', 
                line_shape='hv',  # Use horizontal-vertical steps for accurate jumps
                name=username
            ))
        
        fig.update_layout(
            title='Top 50 Player Scores Over Time',
            xaxis_title='Time (HH:MM)',
            yaxis_title='Score',
            xaxis=dict(tickformat='%H:%M'),
            legend=dict(font=dict(size=10))
        )
        
        # Save the interactive HTML graph
        html_file_name = f'player_scores_{current_time.strftime("%Y%m%d_%H%M%S")}.html'
        fig.write_html(html_file_name)
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - Graph saved as {html_file_name}")

        # Save the graph as a static PNG image as a fallback
        png_file_name = f'player_scores_{current_time.strftime("%Y%m%d_%H%M%S")}.png'
        fig.write_image(png_file_name, format='png')
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - Graph saved as {png_file_name}")

        # Reset the data for the new round
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - Resetting data for the new hour...")
        data_dict = {}

        # Calculate the end of the next hour
        end_of_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        continue

    # Fetch data
    data = fetch_data()
    if data and 'players' in data:
        players = data['players']
        for player in players:
            username = player.get('username')
            score = player.get('score')
            if username and score is not None:
                # Add data only if there's a change in score
                if username not in data_dict or (data_dict[username]['score'] and score != data_dict[username]['score'][-1]):
                    if username not in data_dict:
                        data_dict[username] = {'time': [], 'score': []}
                    data_dict[username]['time'].append(current_time)
                    data_dict[username]['score'].append(score)
    else:
        print(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} - No valid player data found.")
    
    # Wait for the next fetch
    time.sleep(fetch_interval)