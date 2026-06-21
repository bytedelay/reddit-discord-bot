from reddit_fetcher import fetch_latest_posts


posts = fetch_latest_posts(
    subreddit_name="PORNism",
    feed_mode="hot",
    limit=5,
)

for post in posts:
    print("-" * 80)
    print("Title:", post["title"])
    print("URL:", post["url"])
    print("Images found:", len(post["image_urls"]))
    for image_url in post["image_urls"]:
        print("  IMG:", image_url)

    print("Videos found:", len(post["video_urls"]))
    for video_url in post["video_urls"]:
        print("  VID:", video_url)