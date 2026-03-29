import streamlit as st
import json
import time
import pandas as pd
import matplotlib.pyplot as plt

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from openai import OpenAI


client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


st.set_page_config(page_title="Sofascore Player Stats", layout="centered")
st.title("⚽ Player Statistics Viewer")


def search_match_selenium(query):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get("https://www.sofascore.com")
        time.sleep(3)

        query_encoded = query.replace(" ", "%20")

        js = f"""
        return fetch("https://api.sofascore.com/api/v1/search/all?q={query_encoded}")
            .then(r => r.json())
            .then(d => JSON.stringify(d));
        """

        data = json.loads(driver.execute_script(js))

        events = []
        for item in data.get("results", []):
            if item.get("type") == "event":
                e = item["entity"]
                events.append({
                    "id": e["id"],
                    "name": e["name"],
                    "tournament": e["tournament"]["name"],
                    "timestamp": e["startTimestamp"]
                })

        return events

    finally:
        driver.quit()


def get_player_statistics_selenium(match_id):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get("https://www.sofascore.com")
        time.sleep(3)

        js_stats = f"""
        return fetch("https://api.sofascore.com/api/v1/event/{match_id}/player-statistics")
            .then(r => r.json())
            .then(d => JSON.stringify(d))
            .catch(() => null);
        """

        result = driver.execute_script(js_stats)

        if result:
            data = json.loads(result)
            if data.get("players"):
                return data["players"]

        js_lineups = f"""
        return fetch("https://api.sofascore.com/api/v1/event/{match_id}/lineups")
            .then(r => r.json())
            .then(d => JSON.stringify(d));
        """

        data = json.loads(driver.execute_script(js_lineups))

        players = []
        players += data.get("home", {}).get("players", [])
        players += data.get("away", {}).get("players", [])

        return players

    finally:
        driver.quit()

#
def find_player(players, name):
    name = name.lower().strip()
    for p in players:
        if name in p["player"]["name"].lower():
            return p
    return None

def generate_performance_summary(player):
    s = player["statistics"]
    name = player["player"]["name"]

    total_pass = s.get("totalPass", 0)
    accurate_pass = s.get("accuratePass", 0)
    pass_accuracy = (accurate_pass / total_pass * 100) if total_pass else 0

    duels_won = s.get("duelWon", 0)
    duels_lost = s.get("duelLost", 0)
    duel_rate = (duels_won / (duels_won + duels_lost) * 100) if (duels_won + duels_lost) else 0

    return f"""
**{name}** played **{s.get("minutesPlayed", "-")} minutes**  
Pass accuracy: **{pass_accuracy:.1f}%**  
Shots: **{s.get("totalShots", 0)}** | Key passes: **{s.get("keyPass", 0)}**  
Duels won: **{duel_rate:.1f}%**  
Overall rating: **{s.get("rating", "-")}**
"""

def create_performance_dataframe(player):
    s = player["statistics"]
    return pd.DataFrame({
        "Metric": ["Total Passes", "Accurate Passes", "Duels Won", "Duels Lost", "Shots", "Key Passes", "Tackles"],
        "Value": [
            s.get("totalPass", 0),
            s.get("accuratePass", 0),
            s.get("duelWon", 0),
            s.get("duelLost", 0),
            s.get("totalShots", 0),
            s.get("keyPass", 0),
            s.get("totalTackle", 0),
        ]
    })

def plot_metrics(df):
    fig, ax = plt.subplots()
    ax.bar(df["Metric"], df["Value"])
    ax.set_title("Player Performance Metrics")
    plt.xticks(rotation=30)
    st.pyplot(fig)


def generate_coach_advice(player):
    stats = player["statistics"]
    name = player["player"]["name"]
    position = player["player"].get("position", "player")

    prompt = f"""
You are an elite football coach.

Player: {name}
Position: {position}

Match performance stats:
{json.dumps(stats, indent=2)}

Give professional coaching advice:
- What the player did well
- What to improve
- Concrete training suggestions
- Tactical advice for next match

Write clearly and concisely.
"""

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=300
    )

    return response.choices[0].message.content

# -----------------------------
# UI
# -----------------------------
match_query = st.text_input(
    "⚽ Enter match (team vs team + competition or year)",
    placeholder="Ex: Morocco vs Senegal AFCON 2025"
)

player_name = st.text_input(
    "👤 Player name",
    placeholder="Ex: Neil El Aynaoui"
)

if st.button("📊 Load Player Stats"):

    with st.spinner("Searching matches..."):
        matches = search_match_selenium(match_query)

    if not matches:
        st.error("No matches found.")
        st.stop()

    labels = [f"{m['name']} | {m['tournament']} | {m['timestamp']}" for m in matches]
    selected_label = st.selectbox("Select the correct match", labels)
    match = matches[labels.index(selected_label)]

    with st.spinner("Fetching players..."):
        players = get_player_statistics_selenium(match["id"])

    player = find_player(players, player_name)

    if not player:
        st.error("Player not found.")
        st.stop()

    st.success(player["player"]["name"])

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Position", player["player"].get("position", "-"))
        st.metric("Jersey", player["player"].get("jerseyNumber", "-"))
    with col2:
        st.metric("Rating", player["statistics"].get("rating", "-"))
        st.metric("Minutes", player["statistics"].get("minutesPlayed", "-"))

    st.write("## 🧠 Performance Summary")
    st.markdown(generate_performance_summary(player))

    st.write("## 📊 Performance Metrics")
    df = create_performance_dataframe(player)
    st.dataframe(df, use_container_width=True)
    plot_metrics(df)

    st.write("## 🧠 AI Coach Advice")
    with st.spinner("Generating coaching advice..."):
        advice = generate_coach_advice(player)

    st.markdown(advice)
