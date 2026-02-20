import os
import time
import sqlite3
import requests
import traceback
from datetime import datetime
from atproto import Client, models
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image
from io import BytesIO

# =============================
# CONFIG
# =============================

CHECK_INTERVAL = 240  # 4 minutes

LB_USERNAME = os.getenv("LB_USERNAME")
LB_TOKEN = os.getenv("LB_TOKEN")

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_PASSWORD = os.getenv("BLUESKY_PASSWORD")

DB_PATH = "state.db"

MAX_IMAGE_SIZE = 950 * 1024  # 950KB (under Bluesky's 976.56KB limit)
MAX_IMAGE_DIMENSION = 2000  # Max width/height to resize to

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
# IMAGE PROCESSING
# =============================

def resize_image(image_bytes):
    """
    Resize image to fit within Bluesky's size and dimension limits
    """
    try:
        # Open the image
        img = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if necessary (remove alpha channel)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Check if resizing is needed based on dimensions
        width, height = img.size
        
        # If image is larger than MAX_IMAGE_DIMENSION in either dimension, resize it
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            # Calculate new dimensions while maintaining aspect ratio
            ratio = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            
            # Resize image
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"📏 Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Save to bytes with quality adjustment if needed
        quality = 95
        output = BytesIO()
        
        # Try saving with decreasing quality until size is under limit
        while True:
            output.seek(0)
            output.truncate()
            
            # Save as JPEG (more compression than PNG)
            img.save(output, format='JPEG', quality=quality, optimize=True)
            
            size = output.tell()
            
            if size < MAX_IMAGE_SIZE or quality <= 10:
                break
                
            # Reduce quality and try again
            quality -= 10
            print(f"📦 Image size: {size/1024:.2f}KB, reducing quality to {quality}...")
        
        final_size = output.tell()
        print(f"✅ Final image size: {final_size/1024:.2f}KB")
        
        return output.getvalue()
        
    except Exception as e:
        print(f"⚠️ Image processing failed: {e}")
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
# HASHTAG FACETS
# =============================

def create_hashtag_facets(text, hashtags):
    """
    Create Bluesky facets for hashtags.
    Returns a tuple of (text_with_hashtags, facets)
    """
    facets = []
    
    # Add the hashtags to the text
    hashtag_text = " ".join(hashtags)
    full_text = f"{text}\n\n{hashtag_text}"
    
    # Calculate the starting position of hashtags in the full text
    hashtag_start = len(text) + 2  # +2 for the two newlines
    
    current_pos = hashtag_start
    
    for hashtag in hashtags:
        # Find where this hashtag appears in the text
        hashtag_without_hash = hashtag[1:]  # Remove the # for the tag value
        
        # Create the facet for this hashtag
        facet = models.AppBskyRichtextFacet.Main(
            features=[
                models.AppBskyRichtextFacet.Tag(
                    tag=hashtag_without_hash
                )
            ],
            index=models.AppBskyRichtextFacet.ByteSlice(
                byte_start=current_pos,
                byte_end=current_pos + len(hashtag)
            )
        )
        
        facets.append(facet)
        
        # Move position past this hashtag plus the space
        current_pos += len(hashtag) + 1  # +1 for the space
    
    return full_text, facets


# =============================
# POST TO BLUESKY
# =============================

def post_to_bluesky(text, image_bytes=None, hashtags=None):
    print("📤 Posting to Bluesky...")

    try:
        if hashtags:
            full_text, facets = create_hashtag_facets(text, hashtags)
        else:
            full_text = text
            facets = None

        if image_bytes:
            # Resize the image before uploading
            resized_image = resize_image(image_bytes)
            
            if not resized_image:
                print("⚠️ Image processing failed, posting without image")
                client.send_post(
                    text=full_text,
                    facets=facets
                )
            else:
                upload = client.upload_blob(resized_image)

                client.send_post(
                    text=full_text,
                    facets=facets,
                    embed={
                        "$type": "app.bsky.embed.images",
                        "images": [{
                            "image": upload.blob,
                            "alt": text.split('\n')[0]  # Use first line as alt text
                        }]
                    }
                )
        else:
            client.send_post(
                text=full_text,
                facets=facets
            )

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
    
    # Create hashtags list
    hashtags = ["#NowPlaying"]
    
    # Add artist hashtag (remove spaces)
    artist_tag = f"#{artist.replace(' ', '')}"
    hashtags.append(artist_tag)
    
    # Add genre hashtags
    for genre in genres:
        genre_tag = f"#{genre.replace(' ', '')}"
        hashtags.append(genre_tag)

    progress_bar = generate_progress_bar()

    post_text = f"""🎧 KeeCloud Music

🎵 {artist} – {title}

{progress_bar}"""

    image = get_album_art(release_mbid)

    success = post_to_bluesky(post_text, image, hashtags)

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