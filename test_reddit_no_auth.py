import os

import requests
from dotenv import load_dotenv


load_dotenv()

SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "python")

url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new.json?limit=5"

headers = {
    "User-Agent": "DRBOT/0.1 by local-development"
}

response = requests.get(url, headers=headers, timeout=10)

print("Status code:", response.status_code)

response.raise_for_status()

data = response.json()

print(f"Latest posts from r/{SUBREDDIT_NAME}:")

for item in data["data"]["children"]:
    post = item["data"]

    print("-" * 50)
    print("Title:", post["title"])
    print("ID:", post["id"])
    print("URL:", f"https://www.reddit.com{post['permalink']}")