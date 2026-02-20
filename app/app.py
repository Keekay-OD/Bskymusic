import os
import time
import sqlite3
import requests
from datetime import datetime
from atproto import Client
from dotenv import load_dotenv

load_dotenv()

LB_USERNAME = os.getenv("LB_USERNAME")
LB_TOKEN = os.getenv("LB_TOKEN")
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_PASSWORD = os.getenv("BLUESKY_PASSWORD")

CHECK_INTERVAL = 240  # 4 minutes
LB_HEADERS = {"Authorization": f"Token {LB_TOKEN}"}

print("========== 🎵 BSKY MUSIC BOT STARTING ==========")
print("User:", LB_USERNAME)
print("Interval:", CHECK_INTERVAL, "seconds")

# --------------------------
# DATABASE
# --------------------------

conn = sqlite3.connect("state.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    artist TEXT,
    title TEXT,
    date TEXT
)
""")

conn.commit()

print("Database initialized.")

def already_posted_today(artist, title):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute(
        "SELECT 1 FROM posts WHERE artist=? AND title=? AND date=?",
        (artist, title, today)
    )
    return c.fetchone() is not None


def record_post(artist, title):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO posts (artist, title, date) VALUES (?, ?, ?)",
        (artist, title, today)
    )
    conn.commit()
    print("Recorded post in DB.")


# --------------------------
# PROGRESS BAR
# --------------------------

def build_progress_bar(percent=75):
    total_blocks = 10
    filled = int((percent / 100) * total_blocks)
    empty = total_blocks - filled
    return "▰" * filled + "▱" * empty


# --------------------------
# LISTENBRAINZ
# --------------------------

def get_now_playing():
    print("Checking ListenBrainz...")

    url = f"https://api.listenbrainz.org/1/user/{LB_USERNAME}/playing-now"
    r = requests.get(url, headers=LB_HEADERS)

    print("Status:", r.status_code)

    if r.status_code != 200:
        print("Error:", r.text)
        return None

    listens = r.json().get("payload", {}).get("listens", [])
    if not listens:
        print("Nothing playing.")
        return None

    track = listens[0]["track_metadata"]

    artist = track.get("artist_name")
    title = track.get("track_name")
    year = track.get("release_year", "")
    mbid = track.get("additional_info", {}).get("release_mbid")

    # Try to get genre tags
    tags = track.get("tags", [])
    genres = []

    if tags:
        for tag in tags[:3]:  # max 3 genre tags
            clean = tag.replace(" ", "")
            genres.append(f"#{clean}")

    print("Now Playing:", artist, "-", title)

    return artist, title, year, mbid, genres


def get_album_art(mbid):
    if not mbid:
        print("No MBID for album art.")
        return None

    url = f"https://coverartarchive.org/release/{mbid}/front-500"
    r = requests.get(url)

    if r.status_code == 200:
        print("Album art found.")
        return r.content

    print("No album art available.")
    return None


# --------------------------
# BLUESKY
# --------------------------

print("Logging into Bluesky...")
client = Client()
client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
print("Bluesky login successful.")

def post_to_bluesky(text, image_bytes=None):
    print("Posting to Bluesky...")

    if image_bytes:
        upload = client.upload_blob(image_bytes)

        client.send_post(
            text=text,
            embed={
                "$type": "app.bsky.embed.images",
                "images": [{
                    "image": upload.blob,
                    "alt": text
                }]
            }
        )
    else:
        client.send_post(text)

    print("Post successful.")


# --------------------------
# MAIN CHECK
# --------------------------

def run_check():
    now = get_now_playing()

    if not now:
        return

    artist, title, year, mbid, genres = now

    if already_posted_today(artist, title):
        print("Already posted today.")
        return

    # Clean title line
    if year and str(year).strip():
        title_line = f"{artist} – {title} ({year})"
    else:
        title_line = f"{artist} – {title}"

    # Animated-style progress (fake but looks dynamic)
    progress_bar = build_progress_bar(75)

    clean_artist = artist.replace(" ", "")
    base_tags = f"#NowPlaying #{clean_artist}"

    genre_tags = " ".join(genres)

    post_text = f"""🎧 VibesCloud Music

🎵 {title_line}

{progress_bar}

{base_tags} {genre_tags}
"""

    album_art = get_album_art(mbid)

    post_to_bluesky(post_text, album_art)
    record_post(artist, title)


# --------------------------
# LOOP
# --------------------------

print("Initial check on startup...")
run_check()

while True:
    print("Sleeping for", CHECK_INTERVAL, "seconds...")
    time.sleep(CHECK_INTERVAL)

    print("Running scheduled check...")
    try:
        run_check()
    except Exception as e:
        print("ERROR:", e)
        time.sleep(30)
