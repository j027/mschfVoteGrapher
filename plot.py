import httpx
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from fake_useragent import UserAgent
import logging
import json
import os

# Set up logging configuration with milliseconds
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Function to read proxies from a file
def read_proxies(file_path='proxies.txt'):
    proxies = []
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

# Initialize proxies
proxies = read_proxies()
if not proxies:
    logging.error("No proxies found. Please ensure 'proxies.txt' contains proxies.")
    exit(1)  # Exit if no proxies are found

# Create a list of HTTPX clients, each using a different proxy
clients = []
for proxy_url in proxies:
    clients.append(httpx.Client(http2=True, proxies={"http://": proxy_url, "https://": proxy_url}))

user_agent = UserAgent()  # Initialize UserAgent object

# File to save state
JSON_STATE_FILE = 'leaderboard_state.json'

# Function to fetch data from the endpoint with added timeout and retry logic
def fetch_data(client, max_retries=3, retry_delay=2):
    url = "https://irk0p9p6ig.execute-api.us-east-1.amazonaws.com/prod/players"
    params = {
        'type': 'ostracize',
        'quantity': 12000,  # Fetch data for all players, to handle leaderboard clearing properly
        'startIndex': 0,
        'reversed': 'true'
    }

    for attempt in range(max_retries):
        try:
            headers = {'User-Agent': user_agent.random}  # Set a random user agent
            start_time = time.time()
            logging.info(f"Attempting to fetch data (Attempt {attempt + 1})...")
            response = client.get(url, params=params, headers=headers, timeout=5.0)  # Include headers in the request
            
            # Check for HTTP errors and raise if any
            response.raise_for_status()
            
            duration = time.time() - start_time
            logging.info(f"Data fetched successfully in {duration:.2f} seconds")
            try:
                data = response.json()
                return data
            except ValueError:
                logging.error("Error parsing JSON!")
                return None

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP errors
            if e.response.status_code == 403:
                logging.warning(f"403 Forbidden error occurred. Retrying in {retry_delay} seconds...")
            else:
                logging.error(f"HTTP error occurred: {e}")
            # Retry on certain HTTP status codes
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logging.error("Max retries reached. Skipping this fetch.")
                return None

        except httpx.RequestError as e:
            logging.error(f"Error fetching data: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error("Max retries reached. Skipping this fetch.")
                return None

# Function to save the current state to a JSON file
def save_state(data_dict, end_of_hour):
    # Ensure end_of_hour is a datetime object before converting
    if isinstance(end_of_hour, datetime):
        end_of_hour_str = end_of_hour.isoformat()
    else:
        end_of_hour_str = end_of_hour  # Already a string
    
    # Convert datetime objects in data_dict to ISO format for JSON serialization
    state = {
        'data_dict': {k: {'time': [t.isoformat() if isinstance(t, datetime) else t for t in v['time']], 'score': v['score']} for k, v in data_dict.items()},
        'end_of_hour': end_of_hour_str
    }
    with open(JSON_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)
    logging.info("State saved to JSON file.")

# Function to load the saved state from a JSON file
def load_state():
    if os.path.exists(JSON_STATE_FILE):
        with open(JSON_STATE_FILE, 'r') as f:
            state = json.load(f)
        # Convert strings back to datetime objects if necessary
        if isinstance(state['end_of_hour'], str):
            state['end_of_hour'] = datetime.fromisoformat(state['end_of_hour'])
        for k, v in state['data_dict'].items():
            v['time'] = [datetime.fromisoformat(t) if isinstance(t, str) else t for t in v['time']]
        logging.info("State loaded from JSON file.")
        return state
    return None

# Initialize variables
fetch_interval = 0.1  # Reduced interval to 0.1 seconds since we're using multiple proxies
client_index = 0  # Start with the first client

# Calculate the end of the current hour
current_time = datetime.now()
end_of_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

# Load saved state if it exists and is still valid
saved_state = load_state()
if saved_state and saved_state['end_of_hour'] == end_of_hour:
    data_dict = saved_state['data_dict']
    logging.info("Loaded previous state from the same hour.")
else:
    data_dict = {}
    logging.info("No valid previous state found or new hour started. Starting fresh.")

try:
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
                xaxis_title='Time (HH:MM)',  # Axis title to indicate minute-level granularity
                yaxis_title='Score',
                xaxis=dict(
                    tickformat='%H:%M',  # Show hours and minutes on the axis
                    hoverformat='%H:%M:%S.%L'  # Show hours, minutes, seconds, and milliseconds on hover
                ),
                legend=dict(font=dict(size=10))
            )
            
            # Save the interactive HTML graph
            html_file_name = f'player_scores_{current_time.strftime("%Y%m%d_%H%M%S")}.html'
            fig.write_html(html_file_name)
            logging.info(f"Graph saved as {html_file_name}")

            # Save the graph as a static PNG image as a fallback
            png_file_name = f'player_scores_{current_time.strftime("%Y%m%d_%H%M%S")}.png'
            fig.write_image(png_file_name, format='png')
            logging.info(f"Graph saved as {png_file_name}")

            # Reset the data for the new round
            logging.info("Resetting data for the new hour...")
            data_dict = {}

            # Calculate the end of the next hour
            end_of_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

            # Remove state file as new hour has started
            if os.path.exists(JSON_STATE_FILE):
                os.remove(JSON_STATE_FILE)

            continue

        # Fetch data using the current client
        data = fetch_data(clients[client_index])
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
                        data_dict[username]['time'].append(current_time.isoformat())  # Convert datetime to ISO format for JSON
                        data_dict[username]['score'].append(score)
            # Periodically save the state to avoid losing progress
            save_state(data_dict, end_of_hour)
        else:
            logging.warning("No valid player data found.")
        
        # Increment the client index for the next request
        client_index = (client_index + 1) % len(clients)

        # Wait for the next fetch
        time.sleep(fetch_interval)

finally:
    # Save the state before exiting
    save_state(data_dict, end_of_hour)
    # Close all clients when done
    for client in clients:
        client.close()
