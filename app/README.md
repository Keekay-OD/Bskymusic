# 📀 Bskymusic — Bluesky Now Playing Bot

Automated bot that posts your currently playing track from **ListenBrainz** to **Bluesky Social** with album art, genre tags, animated progress bar, and clean formatted posts — all in a Docker container.

---

## 🚀 Features

✔ Automatically checks what you’re listening to every 4 minutes
✔ Posts now playing with **album art**
✔ Removes empty year parentheses
✔ Adds genre auto-tags
✔ Branded output with animated-style progress bar
✔ Avoids duplicate posts within the same day
✔ Persistent state stored in SQLite
✔ Works in Docker with auto-restart & live code updates

---

## 📦 Technologies

* Python 3.11
* Docker & Docker Compose
* ListenBrainz API
* Bluesky AT Protocol API
* SQLite (persistent track history)

---

## 🧠 Getting Started

### 🔌 Prerequisites

Before you begin, make sure you have:

* Docker & Docker Compose installed
* A **ListenBrainz user token** (see ListenBrainz settings)
* A **Bluesky handle + app password**

---

## 📥 Installation

1. **Clone the repo**

```bash
git clone https://github.com/Keekay-OD/Bskymusic.git
cd Bskymusic
```

2. **Create your `.env` file**

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```
LB_USERNAME=your_listenbrainz_username
LB_TOKEN=your_listenbrainz_token
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_PASSWORD=your_app_password
```

---

## 🐳 Docker Setup

### 📁 Folder Structure

```
Bskymusic/
├── docker-compose.yml
├── app/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
└── .env
```

---

## 🚀 Start the Bot

To build and start the container:

```bash
docker compose up -d --build
```

### 🪶 View Logs

Tail live logs:

```bash
docker logs -f bsky-music
```

Container auto-restarts on failure and loads new script edits instantly thanks to the bind mount.

---

## ❓ How It Works

1. On startup and every **4 minutes**, the script queries the ListenBrainz API for the currently playing track.
2. If a track is playing and hasn’t been posted *today*, the bot will:

   * Format a clean “Now Playing” message
   * Fetch album art
   * Build a progress bar
   * Extract genre tags from ListenBrainz
   * Post to Bluesky via the AT Protocol
3. The track and date are saved to SQLite to avoid reposting duplicates within the same day.

---

## 📸 Sample Post

```
🎧 KeeCloud Music

🎵 DJ Snake – Loco Contigo

▰▰▰▰▰▰▰▱▱▱

#NowPlaying #DJSnake #Dancehall #Pop
```

📌 Album art appears below the post as an image embed.

---

## ⚙️ Customization

### 🔁 Polling Interval

Edit `CHECK_INTERVAL` inside `app.py` to change how often it checks for new tracks.

---

## 🛠 Advanced Options

Want to take this further?

✅ Delete previous post when a new track starts
✅ Add listening history dashboard
✅ Support multiple users
✅ Track play duration before posting
✅ iTunes or Last.FM cover art fallback

---

## 🧹 Troubleshooting

* **Nothing posts / no logs:**

  * Make sure `.env` values are correct
  * Check `docker logs bsky-music`
  * Ensure the bot has valid ListenBrainz responses

* **Album art missing:**

  * Not all tracks have release MBIDs
  * We can add fallback art sources on request

---

## 📄 Contributor Guide

If you want to extend this project:

* Add more tags (genre, mood, decade)
* Add a web dashboard
* Add user authentication and multi-user posts
* Add Prometheus metrics
* Add scheduler alternatives (webhook triggers)

---

## 📜 License

This project is MIT Licensed — see the license file for more info.

---

## 🧡 Thanks

Powered by ListenBrainz + Bluesky + KeeCloud

---
