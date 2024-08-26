import httpx
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from fake_useragent import UserAgent
import logging

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Initialize an HTTPX client with HTTP/2 support
client = httpx.Client(http2=True)
user_agent = UserAgent()  # Initialize UserAgent object

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

# Initialize variables
data_dict = {}
fetch_interval = 0.5  # Fetch data every 0.5 seconds

# Calculate the end of the current hour
current_time = datetime.now()
end_of_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

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
                    name=username)
                )

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
            logging.warning("No valid player data found.")
        
        # Wait for the next fetch
        time.sleep(fetch_interval)

finally:
    # Close the client when done
    client.close()
