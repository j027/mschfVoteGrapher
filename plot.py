import httpx
import asyncio
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from fake_useragent import UserAgent
import logging
import json
import os
import aiofiles
from concurrent.futures import ThreadPoolExecutor

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
        httpx.AsyncClient(
            http2=True, proxies={"http://": proxy_url, "https://": proxy_url}
        )
    )

user_agent = UserAgent()  # Initialize UserAgent object
# Define the directory where you want to save the files
SAVE_DIRECTORY = os.path.expanduser("~/gdrive/ostracize_graphs")
# Ensure the directory exists
os.makedirs(SAVE_DIRECTORY, exist_ok=True)

lock = asyncio.Lock()
executor = ThreadPoolExecutor(max_workers=1)
JSON_STATE_FILE = "leaderboard_state.json"


async def async_fetch_data(client, quantity, max_retries=3, retry_delay=2):
    url = "https://irk0p9p6ig.execute-api.us-east-1.amazonaws.com/prod/players"
    params = {
        "type": "ostracize",
        "quantity": quantity,
        "startIndex": 0,
        "reversed": "true",
    }

    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": user_agent.random}
            start_time = time.time()
            logging.info(
                f"Attempting to fetch data (Attempt {attempt + 1}) with quantity: {quantity}..."
            )

            response = await client.get(
                url, params=params, headers=headers, timeout=5.0
            )
            response.raise_for_status()
            duration = time.time() - start_time
            logging.info(f"Data fetched successfully in {duration:.2f} seconds")
            return response.json()

        except httpx.HTTPStatusError as e:
            # Log the basic error message
            logging.error(f"HTTP error occurred: {e}")

            # Log request details
            if e.request:
                logging.error(f"Request URL: {e.request.url}")
                logging.error(f"Request Method: {e.request.method}")
                logging.error(f"Request Headers: {e.request.headers}")

            # Log response details
            if e.response:
                logging.error(f"Response Status Code: {e.response.status_code}")
                logging.error(f"Response Headers: {e.response.headers}")
                logging.error(f"Response Content: {e.response.text}")

            return None

        except httpx.RequestError as e:
            # Log the basic error message
            logging.error(f"Request error occurred: {e}")

            # Log request details if available
            if e.request:
                logging.error(f"Request URL: {e.request.url}")
                logging.error(f"Request Method: {e.request.method}")
                logging.error(f"Request Headers: {e.request.headers}")

            # Optionally, if the error includes response data
            if e.response:
                logging.error(f"Response Status Code: {e.response.status_code}")
                logging.error(f"Response Headers: {e.response.headers}")
                logging.error(f"Response Content: {e.response.text}")

            return None


async def async_save_state(data_dict, end_of_hour):
    end_of_hour_str = (
        end_of_hour.isoformat() if isinstance(end_of_hour, datetime) else end_of_hour
    )
    state = {
        "data_dict": {
            k: [
                {
                    "time": (
                        t["time"].isoformat()
                        if isinstance(t["time"], datetime)
                        else t["time"]
                    ),
                    "score": t["score"],
                }
                for t in v
            ]
            for k, v in data_dict.items()
        },
        "end_of_hour": end_of_hour_str,
    }

    async with aiofiles.open(JSON_STATE_FILE, "w") as f:
        await f.write(json.dumps(state, indent=4))
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
            state["data_dict"][k] = [
                {
                    "time": (
                        datetime.fromisoformat(t["time"])
                        if isinstance(t["time"], str)
                        else t["time"]
                    ),
                    "score": t["score"],
                }
                for t in v
            ]
        logging.info("State loaded from JSON file.")
        return state
    return None


async def async_save_graph(end_of_hour, data_dict):
    async with lock:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(executor, save_graph_sync, end_of_hour, data_dict)
        except Exception as e:
            logging.error(f"Failed to save graph: {e}")

def save_graph_sync(end_of_hour, data_dict):
    fig = go.Figure()

    for username, records in data_dict.items():
        times = [entry["time"] for entry in records]
        scores = [entry["score"] for entry in records]
        fig.add_trace(
            go.Scatter(
                x=times,
                y=scores,
                mode="lines+markers",
                line_shape="hv",
                name=username,
            )
        )

    fig.update_layout(
        title="Player Scores Over Time (Ostracize)",
        xaxis_title="Time (HH:MM)",
        yaxis_title="Score",
        xaxis=dict(tickformat="%H:%M", hoverformat="%H:%M:%S.%L"),
        legend=dict(font=dict(size=10)),
        hovermode="x"
    )

    html_file_name = os.path.join(SAVE_DIRECTORY, f'player_scores_{end_of_hour.strftime("%Y%m%d_%H%M%S")}.html')
    png_file_name = os.path.join(SAVE_DIRECTORY, f'player_scores_{end_of_hour.strftime("%Y%m%d_%H%M%S")}.png')

    fig.write_html(html_file_name, include_plotlyjs="cdn")
    fig.write_image(png_file_name, format="png")
    logging.info(f"Graph saved as {html_file_name} and {png_file_name}")

async def periodic_save_graph(interval, end_of_hour, data_dict):
    while True:
        await async_save_graph(end_of_hour, data_dict)
        await asyncio.sleep(interval)


async def main():
    fetch_interval = 0.1  # Fetch data every 0.1 seconds
    client_index = 0
    leaderboard_size = 50
    max_leaderboard_size = 12000

    proxies = read_proxies()
    if not proxies:
        logging.error("No proxies found. Please ensure 'proxies.txt' contains proxies.")
        exit(1)  # Exit if no proxies are found

    clients = []

    clients.append(httpx.AsyncClient(http2=True))
    for proxy_url in proxies:
        clients.append(
            httpx.AsyncClient(
                http2=True, proxies={"http://": proxy_url, "https://": proxy_url}
            )
        )

    end_of_hour = (datetime.now() + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )

    # Load saved state if it exists and is still valid
    saved_state = load_state()
    if saved_state and saved_state["end_of_hour"].hour == end_of_hour.hour:
        data_dict = saved_state["data_dict"]
        logging.info("Loaded previous state from the same hour.")
    else:
        if saved_state:
            previous_end_of_hour = saved_state["end_of_hour"]
            await async_save_graph(previous_end_of_hour, saved_state["data_dict"])

        data_dict = {}
        logging.info(
            "No valid previous state found or new hour started. Starting fresh."
        )

    # Start periodic saving
    save_interval = 20  # Save graph every 20 seconds
    save_graph_task = asyncio.create_task(periodic_save_graph(save_interval, end_of_hour, data_dict))

    try:
        while True:
            current_time = datetime.now()

            # Fetch data using the current client
            data = await async_fetch_data(clients[client_index], leaderboard_size)
            if data and "players" in data:
                players = data["players"]

                # Check for reset if past end of hour
                if current_time >= end_of_hour:
                    all_zero_scores = all(player["score"] == 0 for player in players)

                    if all_zero_scores:
                        logging.info(
                            "Detected leaderboard reset. Saving data and preparing for next hour."
                        )

                        # Save the current data before moving to the next hour
                        await async_save_graph(end_of_hour, data_dict)

                        # Reset the data for the new round
                        logging.info("Resetting data for the new hour...")
                        data_dict = {}

                        # Reset the leaderboard size for the next hour
                        leaderboard_size = 50

                        # Calculate the end of the next hour
                        end_of_hour = (current_time + timedelta(hours=1)).replace(
                            minute=0, second=0, microsecond=0
                        )

                        if save_graph_task:
                            save_graph_task.cancel()
                        save_graph_task = asyncio.create_task(periodic_save_graph(save_interval, end_of_hour, data_dict))

                        # Remove state file as the new hour has started
                        if os.path.exists(JSON_STATE_FILE):
                            os.remove(JSON_STATE_FILE)

                        continue


                # Check last score, to increase leaderboard size as needed
                last_score = players[-1]["score"] if players else None
                if (
                    last_score is not None
                    and last_score > 0
                    and leaderboard_size < max_leaderboard_size
                ):
                    leaderboard_size = min(leaderboard_size * 2, max_leaderboard_size)
                    logging.info(
                        f"Leaderboard size increased to {leaderboard_size} for next fetch."
                    )

                # Tracking changes in score
                for player in players:
                    username = player.get("username")
                    score = player.get("score")

                    if username and score is not None:
                        # Add data only if there's a change in score
                        if username not in data_dict or (
                            data_dict[username]
                            and score != data_dict[username][-1]["score"]
                        ):
                            if username not in data_dict:
                                data_dict[username] = []

                            # Append the new time-score dictionary to the list
                            data_dict[username].append(
                                {"time": current_time, "score": score}
                            )

                # Periodically save the state to avoid losing progress
                await async_save_state(data_dict, end_of_hour)

            else:
                logging.warning("No valid player data found.")

            # Increment the client index for the next request
            client_index = (client_index + 1) % len(clients)

            # Wait for the next fetch
            await asyncio.sleep(fetch_interval)

    finally:
        # Save the state before exiting
        await async_save_state(data_dict, end_of_hour)
        
        # Close all clients when done
        for client in clients:
            await client.aclose()
        
        if save_graph_task:
            save_graph_task.cancel()


# Run the main function in the event loop
asyncio.run(main())
