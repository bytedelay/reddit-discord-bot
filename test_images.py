from reddit_fetcher import fetch_latest_posts


posts = fetch_latest_posts(limit=5)

for post in posts:
    print("-" * 80)
    print("Title:", post["title"])
    print("URL:", post["url"])
    print("Image:", post["image_url"])