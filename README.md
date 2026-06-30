# Discord Music Bot

A feature-rich Discord Music Bot built with `discord.py` and `Wavelink` (Lavalink v4 wrapper).

## Features
- Play music from YouTube, SoundCloud, and other sources using Lavalink v4.
- Save and load playlists (supported on MongoDB or local Sqlite fallback).
- Track state persistence to restore music session after restart.
- Slash command interfaces and UI components (buttons, select menus) for queue management.

## Setup Instructions

1. **Clone the Repository**
2. **Install dependencies**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure environment variables**:
   Create a `.env` file based on `.env.example` and fill in your Discord Bot token.
4. **Run the bot**:
   - On Windows: Run `run.bat` or `.\run.ps1`
   - Otherwise: `python -m music_bot.bot`
