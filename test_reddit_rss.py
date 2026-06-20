import os

import feedparser
import requests
from dotenv import load_dotenv


load_dotenv()

SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "wallpapers")

feed_urls = [
    f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new/.rss",
    f"https://old.reddit.com/r/{SUBREDDIT_NAME}/new/.rss",
]

headers = {
    "User-Agent": "DRBOT/0.1 by local-development"
}


def fetch_feed():
    last_error = None

    for url in feed_urls:
        print(f"Trying feed URL: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=10)
            print("Status code:", response.status_code)

            if response.status_code == 200:
                return feedparser.parse(response.text)

            last_error = f"Failed with status {response.status_code}"

        except requests.RequestException as error:
            last_error = str(error)

    raise RuntimeError(f"Could not fetch Reddit RSS feed. Last error: {last_error}")


feed = fetch_feed()

print(f"\nLatest posts from r/{SUBREDDIT_NAME}:")

if not feed.entries:
    print("No entries found.")
else:
    for entry in feed.entries[:5]:
        print("-" * 60)
        print("Title:", entry.title)
        print("ID:", entry.id)
        print("URL:", entry.link)