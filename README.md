# Claudio FM

A PyQt6 desktop music player powered by NetEase Cloud Music and an Anthropic AI companion.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

## Features

- **NetEase Cloud Music** — QR code login, loads your liked songs playlist (up to 200 tracks)
- **AI Companion (Claudio)** — Chat with an LLM powered by Claude; ask it to play songs, recommend music based on your mood and weather, or just talk
- **AI Playlist tab** — Every song Claudio plays is collected in a dedicated tab, persisted per account and restored on next launch
- **TTS** — 12 Chinese voices via Edge TTS; switch voices mid-conversation
- **Voice input** — Click the mic button to speak; speech is transcribed and sent to Claudio
- **Live weather** — Clock area shows real-time weather icon + temperature via QWeather
- **Scheduled recommendations** — Claudio proactively recommends music at 12:00, 15:00, and 18:00 based on weather and your mood
- **Per-user chat history** — Conversation history is stored in SQLite, isolated by NetEase account, and restored on login
- **Shuffle playback** — Toggle shuffle mode in the player bar
- **Dark / Light theme** — Toggle in the nav bar

## Screenshots

> Coming soon

## Requirements

- Python 3.10+
- A NetEase Cloud Music account (for QR login)
- Anthropic API key (or Bilibili internal proxy)
- QWeather API key (free tier works)

## Setup

```bash
git clone https://github.com/qiaoyuan0902-cpu/music_agent.git
cd music_agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
# Anthropic
ANTHROPIC_API_KEY=sk-...

# QWeather  https://dev.qweather.com
QWEATHER_API_KEY=your_key_here

# Optional
CLAUDE_MODEL=claude-sonnet-4-6
MAX_HISTORY_TURNS=20
```

## Run

```bash
python main.py
```

1. Scan the QR code with NetEase Cloud Music to log in
2. Your liked songs load into the **QUEUE** tab
3. Type or speak to Claudio — try *"帮我播放周杰伦的晴天"*
4. AI-played songs appear in the **AI 点歌** tab and are saved for next time

## Project Structure

```
├── agent/          # LLM agentic loop (Claude tool_use)
│   ├── core.py
│   ├── system_prompt.py
│   └── tools/
├── memory/         # SQLite conversation history + user profile
├── music/          # NetEase Cloud Music API wrapper
├── ui/             # PyQt6 application
│   └── qt_app.py
├── weather/        # QWeather integration
├── config.py
└── main.py
```

## License

MIT
