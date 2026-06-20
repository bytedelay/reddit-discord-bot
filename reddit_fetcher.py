import os
from typing import Dict, List

import feedparser
import requests
from dotenv import load_dotenv


load_dotenv()

SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "wallpapers")


def fetch_latest_posts(limit: int = 5) -> List[Dict[str, str]]:
    feed_url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new/.rss"

    headers = {
        "User-Agent": "DRBOT/0.1 by local-development"
    }

    response = requests.get(feed_url, headers=headers, timeout=10)

    print("Reddit RSS status code:", response.status_code)

    response.raise_for_status()

    feed = feedparser.parse(response.text)

    posts = []

    for entry in feed.entries[:limit]:
        posts.append(
            {
                "id": entry.id,
                "title": entry.title,
                "url": entry.link,
                "subreddit": SUBREDDIT_NAME,
            }
        )

    return posts