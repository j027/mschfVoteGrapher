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
    format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# Function to read proxies from a file
def read_proxies(file_path="proxies.txt"):
    proxies = []
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
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
    clients.append(
        httpx.Client(http2=True, proxies={"http://": proxy_url, "https://": proxy_url})
    )

user_agent = UserAgent()  # Initialize UserAgent object

# File to save state
JSON_STATE_FILE = "leaderboard_state.json"


# Function to fetch data from the endpoint with added timeout and retry logic
def fetch_data(client, quantity, max_retries=3, retry_delay=2):
    url = "https://irk0p9p6ig.execute-api.us-east-1.amazonaws.com/prod/players"
    params = {
        "type": "ostracize",
        "quantity": quantity,  # Fetch data for the specified number of players
        "startIndex": 0,
        "reversed": "true",
    }

    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": user_agent.random}  # Set a random user agent
            start_time = time.time()
            logging.info(
                f"Attempting to fetch data (Attempt {attempt + 1}) with quantity: {quantity}..."
            )
            response = client.get(
                url, params=params, headers=headers, timeout=5.0
            )  # Include headers in the request

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
                logging.warning(
                    f"403 Forbidden error occurred. Retrying in {retry_delay} seconds..."
                )
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
        "data_dict": {
            k: {
                "time": [
                    t.isoformat() if isinstance(t, datetime) else t for t in v["time"]
                ],
                "score": v["score"],
            }
            for k, v in data_dict.items()
        },
        "end_of_hour": end_of_hour_str,
    }
    with open(JSON_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)
    logging.info("State saved to JSON file.")


# Function to load the saved state from a JSON file
def load_state():
    if os.path.exists(JSON_STATE_FILE):
        with open(JSON_STATE_FILE, "r") as f:
            state = json.load(f)
        # Convert strings back to datetime objects if necessary
        if isinstance(state["end_of_hour"], str):
            state["end_of_hour"] = datetime.fromisoformat(state["end_of_hour"])
        for k, v in state["data_dict"].items():
            v["time"] = [
                datetime.fromisoformat(t) if isinstance(t, str) else t
                for t in v["time"]
            ]
        logging.info("State loaded from JSON file.")
        return state
    return None


def save_graph(end_of_hour, data_dict):
    fig = go.Figure()

    # Graph all players in the current data
    for username, values in data_dict.items():
        fig.add_trace(
            go.Scatter(
                x=values["time"],
                y=values["score"],
                mode="lines+markers",
                line_shape="hv",  # Use horizontal-vertical steps for accurate jumps
                name=username,
            )
        )

    fig.update_layout(
        title="Player Scores Over Time",
        xaxis_title="Time (HH:MM)",  # Axis title to indicate minute-level granularity
        yaxis_title="Score",
        xaxis=dict(
            tickformat="%H:%M",  # Show hours and minutes on the axis
            hoverformat="%H:%M:%S.%L",  # Show hours, minutes, seconds, and milliseconds on hover
        ),
        legend=dict(font=dict(size=10)),
    )

    # Save the interactive HTML graph
    html_file_name = f'player_scores_{end_of_hour.strftime("%Y%m%d_%H%M%S")}.html'
    fig.write_html(html_file_name, include_plotlyjs="cdn")
    logging.info(f"Graph saved as {html_file_name}")

    # Save the graph as a static PNG image as a fallback
    png_file_name = f'player_scores_{end_of_hour.strftime("%Y%m%d_%H%M%S")}.png'
    fig.write_image(png_file_name, format="png")
    logging.info(f"Graph saved as {png_file_name}")


# Initialize variables
fetch_interval = 0.1  # Reduced interval to 0.1 seconds since we're using multiple proxies
client_index = 0  # Start with the first client
leaderboard_size = 50  # Start fetching top 50 players
max_leaderboard_size = 12000  # Max limit for fetching

# Calculate the end of the current hour
current_time = datetime.now()
end_of_hour = (current_time + timedelta(hours=1)).replace(
    minute=0, second=0, microsecond=0
)

# Load saved state if it exists and is still valid
saved_state = load_state()
if saved_state and saved_state["end_of_hour"].hour == end_of_hour.hour:
    data_dict = saved_state["data_dict"]
    logging.info("Loaded previous state from the same hour.")
else:
    if saved_state:
        # Save graph with old data before starting fresh
        previous_end_of_hour = saved_state["end_of_hour"]
        save_graph(previous_end_of_hour, saved_state["data_dict"])

    # Start fresh
    data_dict = {}
    logging.info("No valid previous state found or new hour started. Starting fresh.")

try:
    while True:
        current_time = datetime.now()

        # Fetch data using the current client
        data = fetch_data(clients[client_index], leaderboard_size)
        if data and "players" in data:
            players = data["players"]

            # check for reset if past end of hour
            if current_time >= end_of_hour:
                # first place info from current leaderboard
                first_place_player = players[0]
                first_place_name = first_place_player["name"]
                first_place_score = first_place_player["score"]

                # if first place name isn't in the saved data 
                # or if the score is below what was last saved
                if first_place_name not in data_dict or first_place_score < data_dict[first_place_name][-1]:
                    logging.info(
                        "Detected leaderboard reset. Saving data and preparing for next hour."
                    )

                    # Save the current data before moving to the next hour
                    save_graph(end_of_hour, data_dict)

                    # Reset the data for the new round
                    logging.info("Resetting data for the new hour...")
                    data_dict = {}

                    # Reset the leaderboard size for the next hour
                    leaderboard_size = 50

                    # Calculate the end of the next hour
                    end_of_hour = (current_time + timedelta(hours=1)).replace(
                        minute=0, second=0, microsecond=0
                    )

                    # Remove state file as the new hour has started
                    if os.path.exists(JSON_STATE_FILE):
                        os.remove(JSON_STATE_FILE)

                    continue

            # check last score, to increase leaderboard size as needed
            last_score = players[-1]["score"] if players else None
            if (
                last_score is not None
                and last_score > 0
                and leaderboard_size < max_leaderboard_size
            ):
                # Double the leaderboard size for the next request if the last player score is greater than 0
                leaderboard_size = min(leaderboard_size * 2, max_leaderboard_size)
                logging.info(
                    f"Leaderboard size increased to {leaderboard_size} for next fetch."
                )

            # tracking changes in score
            for player in players:
                username = player.get("username")
                score = player.get("score")

                if username and score is not None:
                    # Add data only if there's a change in score
                    if username not in data_dict or (
                        data_dict[username]["score"]
                        and score != data_dict[username]["score"][-1]
                    ):
                        if username not in data_dict:
                            data_dict[username] = {"time": [], "score": []}

                        # Convert datetime to ISO format for JSON
                        data_dict[username]["time"].append(current_time.isoformat())
                        data_dict[username]["score"].append(score)

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
