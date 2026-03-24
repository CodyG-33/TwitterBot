import asyncio
import json
import os
import re
from typing import Optional

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

try:
    from twikit import Client as TwikitClient
except ImportError:
    TwikitClient = None

load_dotenv()

# Tweet extraction: prefer twikit (https://github.com/d60/twikit) with cookies or login.
# bisguzar/twitter-scraper is archived (Aug 2024) and targets legacy unauthenticated X APIs.

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

DB_FILE = "bookmarks.json"

_twikit_client = None
_twikit_init_lock = asyncio.Lock()

STATUS_ID_RE = re.compile(r"/status/(\d+)")


def _twikit_cookies_path() -> str:
    raw = os.getenv("TWITTER_COOKIES_FILE", "twikit_cookies.json")
    return raw if os.path.isabs(raw) else os.path.join(BOT_DIR, raw)


async def _ensure_twikit_client():
    """Return a logged-in Twikit client, or None if twikit is unavailable or not configured."""
    global _twikit_client
    if TwikitClient is None:
        return None

    async with _twikit_init_lock:
        if _twikit_client is not None:
            return _twikit_client

        cookies_path = _twikit_cookies_path()
        client = TwikitClient(os.getenv("TWITTER_LANG", "en-US"))

        if os.path.isfile(cookies_path):
            client.load_cookies(cookies_path)
            _twikit_client = client
            return _twikit_client

        username = os.getenv("TWITTER_USERNAME")
        password = os.getenv("TWITTER_PASSWORD")
        if not username or not password:
            return None

        email = os.getenv("TWITTER_EMAIL") or username
        await client.login(
            auth_info_1=username,
            auth_info_2=email,
            password=password,
            cookies_file=cookies_path,
        )
        _twikit_client = client
        return _twikit_client


def _tweet_id_from_url(url: str) -> Optional[str]:
    m = STATUS_ID_RE.search(url.split("?")[0])
    return m.group(1) if m else None


def _format_twikit_tweet(tweet) -> str:
    author = "Unknown Author"
    if getattr(tweet, "user", None) is not None:
        u = tweet.user
        author = getattr(u, "name", None) or getattr(u, "screen_name", None) or author
    text = getattr(tweet, "text", None) or getattr(tweet, "full_text", None) or ""
    rt = getattr(tweet, "retweeted_tweet", None)
    if rt is not None:
        inner = getattr(rt, "text", None) or getattr(rt, "full_text", None) or ""
        inner_user = getattr(getattr(rt, "user", None), "screen_name", None) or "user"
        text = f"RT @{inner_user}: {inner}"
    return f"Tweet by {author}: {text}"


async def _fetch_via_twikit(tweet_id: str) -> Optional[str]:
    try:
        client = await _ensure_twikit_client()
        if client is None:
            return None
        tweet = await client.get_tweet_by_id(tweet_id)
        return _format_twikit_tweet(tweet)
    except Exception:
        return None


def _fetch_via_public_embed_api(url: str) -> Optional[str]:
    """Try third-party oEmbed-style JSON mirrors (no X login). Multiple hosts for resilience."""
    clean_url = url.split("?")[0]
    hosts = ("api.vxtwitter.com", "api.fxtwitter.com")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    last_error: Optional[Exception] = None
    for host in hosts:
        api_url = clean_url.replace("x.com", host).replace("twitter.com", host)
        try:
            resp = requests.get(api_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            tweet_text = (
                data.get("text")
                or data.get("full_text")
                or data.get("tweet", {}).get("text")
                or data.get("tweet", {}).get("full_text")
            )
            author = (
                data.get("user_name")
                or data.get("user", {}).get("name")
                or data.get("tweet", {}).get("user", {}).get("name")
                or "Unknown Author"
            )
            if not tweet_text:
                tweet_text = f"(raw tweet data, truncated) {json.dumps(data)[:1000]}"
            return f"Tweet by {author}: {tweet_text}"
        except Exception as e:
            last_error = e
            continue
    if last_error:
        return f"Failed to extract tweet text (public API fallback): {last_error}"
    return None


async def fetch_tweet_content(url: str) -> str:
    tweet_id = _tweet_id_from_url(url)
    if not tweet_id:
        return "Could not find a tweet id in that URL."

    twikit_text = await _fetch_via_twikit(tweet_id)
    if twikit_text:
        return twikit_text

    public = _fetch_via_public_embed_api(url)
    if public:
        return public

    return (
        "Could not load this tweet. Set up Twikit: add TWITTER_USERNAME + TWITTER_PASSWORD "
        "(and TWITTER_EMAIL if needed) or place a valid session in TWITTER_COOKIES_FILE "
        "(see https://github.com/d60/twikit )."
    )


def load_bookmarks():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r") as file:
        return json.load(file)

def save_bookmark(text):
    bookmarks = load_bookmarks()
    bookmarks.append(text)
    with open(DB_FILE, "w") as file:
        json.dump(bookmarks, file, indent=4)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "V4 Online.\n"
        "- Send 'Save: [link/text]' to store data (X links are fetched via Twikit if configured, else public mirrors).\n"
        "- Send /project to get your weekly build recommendations."
    )

# New Function: The Weekly Project Generator
async def project_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bookmarks = load_bookmarks()
    
    if not bookmarks:
        await update.message.reply_text("Your memory bank is empty. Save some strategies first!")
        return

    await update.message.reply_text("Analyzing your research and generating project ideas... 🧠")

    # Custom prompt tailored to your analytics background
    prompt = f"""
    You are an elite AI engineering mentor. Your student is a Business Analytics and Applied Statistical Modeling major who uses Python, R, and APIs. They are looking for internships and a side hustle.
    
    Here is the research and strategies they saved this week:
    {json.dumps(bookmarks)}
    
    Analyze this data and recommend 1 or 2 highly actionable, impressive weekend projects they can build using ONLY the concepts, tools, or strategies mentioned in their saved research.
    
    For each project, provide:
    1. Project Title
    2. The Value Proposition (What is the problem this project solves and why is it valuable?)
    3. The Concept (Why it is a strong resume builder)
    4. Tech Stack / Tools to use
    5. The first 3 concrete steps to start building it today.
    """
    
    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Error generating project: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    print(f"Received: {user_text}")
    
    if user_text.lower().startswith("save:"):
        content_to_save = user_text[5:].strip()
        twitter_links = re.findall(r'(https?://(?:www\.)?(?:twitter\.com|x\.com)/[^\s]+)', content_to_save)
        
        if twitter_links:
            await update.message.reply_text("Extracting data...")
            extracted_text = await fetch_tweet_content(twitter_links[0])
            content_to_save = f"Source URL: {twitter_links[0]}\nContent: {extracted_text}"
        
        save_bookmark(content_to_save)
        await update.message.reply_text("✅ Saved to your memory bank.")
        
    else:
        bookmarks = load_bookmarks()
        prompt = f"""
        You are my personal knowledge assistant. Here are my saved bookmarks:
        {json.dumps(bookmarks)}
        Answer my question using ONLY this context. If the answer isn't there, tell me.
        Question: {user_text}
        """
        try:
            response = model.generate_content(prompt)
            await update.message.reply_text(response.text)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

def main():
    print("Starting V4 bot locally...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("project", project_command)) # Registers the new command
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Polling for messages...")
    app.run_polling()

if __name__ == '__main__':
    main()