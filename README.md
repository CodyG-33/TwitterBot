# TwitterBot

A Telegram bot that saves posts and notes to a local “memory bank,” expands **X (Twitter)** links into tweet text when possible, and uses **Google Gemini** to answer questions from your saves or suggest weekend projects from them.

## Features

- **`Save: …`** — Append text or a tweet URL to `bookmarks.json`. For `x.com` / `twitter.com` links, the bot fetches tweet text (see below).
- **Anything else** — Gemini answers using **only** your saved bookmarks as context.
- **`/project`** — Gemini proposes 1–2 actionable projects grounded in what you saved (tailored for analytics / Python / R / API work).
- **`/start`** — Short usage reminder.

## Requirements

- Python 3.9+ (use a recent 3.x if [twikit](https://github.com/d60/twikit) raises compatibility issues).
- A [Telegram Bot](https://core.telegram.org/bots/tutorial) token and a [Gemini API key](https://ai.google.dev/).

## Setup

```bash
cd TwitterBot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `GEMINI_API_KEY` | From Google AI Studio |

### Optional: reliable X tweet text ([Twikit](https://github.com/d60/twikit))

Without Twikit, the bot tries public mirror APIs (`api.vxtwitter.com`, `api.fxtwitter.com`), which can fail or rate-limit.

To use Twikit, set:

- `TWITTER_USERNAME`, `TWITTER_PASSWORD`
- `TWITTER_EMAIL` if your account needs it (otherwise you can mirror username)

On first successful login, a cookie file is written (default `twikit_cookies.json` next to `bot.py`). You can override the path with `TWITTER_COOKIES_FILE`. Optional: `TWITTER_LANG` (default `en-US`).

**Do not commit** `.env`, `twikit_cookies.json`, or `bookmarks.json` (they are listed in `.gitignore`). Using Twikit means automating an X session; follow X’s terms and Twikit’s guidance for your own risk tolerance.

## Run

From the `TwitterBot` directory (so `bookmarks.json` is created in the right place):

```bash
source .venv/bin/activate
python bot.py
```

## Repository

https://github.com/CodyG-33/TwitterBot

## Stack

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [google-generativeai](https://github.com/google-gemini/generative-ai-python)
- [twikit](https://github.com/d60/twikit)
- `requests` for public tweet mirror fallbacks
