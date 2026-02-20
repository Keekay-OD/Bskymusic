import os
import time
import sqlite3
import requests
import traceback
from datetime import datetime
from atproto import Client
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============================
# CONFIG
# =============================

CHECK_INTERVAL = 240  # 4 minutes

LB_USERNAME = os.getenv("LB_USERNAME")
LB_TOKEN = os.getenv("LB_TOKEN")

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_PASSWORD = os.getenv("BLUESKY_PASSWORD")

DB_PATH = "state.db"

# =============================
# HTTP SESSION (PRODUCTION SAFE)
# =============================

def create_session():
    session = requests.Session()

    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


session = create_session()

# =============================
# BLUESKY CLIENT
# =============================

client = Client()


def safe_login():
    try:
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
        print("✅ Bluesky login successful.")
    except Exception as e:
        print(f"⚠️ Bluesky login failed: {e}")
        time.sleep(5)
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)


# =============================
# DATABASE
# =============================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT,
            title TEXT,
            post_date TEXT
        )
    """)

    conn.commit()
    conn.close()


def already_posted_today(artist, title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    today = datetime.utcnow().date().isoformat()

    c.execute("""
        SELECT * FROM posts
        WHERE artist=? AND title=? AND post_date=?
    """, (artist, title, today))

    result = c.fetchone()
    conn.close()

    return result is not None


def save_post(artist, title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    today = datetime.utcnow().date().isoformat()

    c.execute("""
        INSERT INTO posts (artist, title, post_date)
        VALUES (?, ?, ?)
    """, (artist, title, today))

    conn.commit()
    conn.close()


# =============================
# LISTENBRAINZ
# =============================

def get_now_playing():
    url = f"https://api.listenbrainz.org/1/user/{LB_USERNAME}/playing-now"

    headers = {"Authorization": f"Token {LB_TOKEN}"}

    response = session.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        print("⚠️ ListenBrainz API error:", response.status_code)
        return None

    data = response.json()

    if "payload" not in data or "listens" not in data["payload"]:
        return None

    listens = data["payload"]["listens"]

    if not listens:
        return None

    track = listens[0]["track_metadata"]

    artist = track.get("artist_name")
    title = track.get("track_name")
    release = track.get("release_name")

    additional = track.get("additional_info", {})
    release_mbid = additional.get("release_mbid")

    return {
        "artist": artist,
        "title": title,
        "release": release,
        "release_mbid": release_mbid,
    }


# =============================
# ALBUM ART
# =============================

def get_album_art(mbid):
    if not mbid:
        return None

    url = f"https://coverartarchive.org/release/{mbid}/front"

    try:
        response = session.get(url, timeout=15)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        print("Album art fetch failed:", e)

    return None


# =============================
# GENRES
# =============================

def get_genres(artist):
    try:
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{artist}&fmt=json"
        response = session.get(url, timeout=15)

        if response.status_code != 200:
            return []

        data = response.json()
        if not data.get("artists"):
            return []

        tags = data["artists"][0].get("tags", [])
        return [tag["name"] for tag in tags[:3]]

    except Exception as e:
        print("Genre lookup failed:", e)
        return []


# =============================
# PROGRESS BAR
# =============================

def generate_progress_bar():
    # Fake animated-style static bar (visual only)
    filled = 7
    empty = 3
    return "▰" * filled + "▱" * empty


# =============================
# POST TO BLUESKY
# =============================

def post_to_bluesky(text, image_bytes=None):
    print("📤 Posting to Bluesky...")

    try:
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

        print("✅ Post successful.")
        return True

    except Exception as e:
        print("⚠️ Post failed:", e)
        safe_login()
        return False


# =============================
# MAIN LOGIC
# =============================

def check_now_playing():
    track = get_now_playing()

    if not track:
        print("Nothing playing.")
        return

    artist = track["artist"]
    title = track["title"]
    release_mbid = track["release_mbid"]

    if already_posted_today(artist, title):
        print("Already posted today.")
        return

    genres = get_genres(artist)
    genre_tags = " ".join(f"#{g.replace(' ', '')}" for g in genres)

    progress_bar = generate_progress_bar()

    clean_artist = artist.replace(" ", "")

    post_text = f"""🎧 KeeCloud Music

🎵 {artist} – {title}

{progress_bar}

#NowPlaying #{clean_artist} {genre_tags}
"""

    image = get_album_art(release_mbid)

    success = post_to_bluesky(post_text, image)

    if success:
        save_post(artist, title)


# =============================
# STARTUP
# =============================

if __name__ == "__main__":
    print("🚀 Starting BskyMusic Bot...")

    init_db()
    safe_login()

    print("🔎 Initial check on startup...")
    try:
        check_now_playing()
    except Exception:
        traceback.print_exc()

    while True:
        try:
            print("⏱ Checking now playing...")
            check_now_playing()
        except Exception:
            traceback.print_exc()

        time.sleep(CHECK_INTERVAL)
