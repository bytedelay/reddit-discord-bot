import html
import time
from typing import Dict, List

import feedparser
import requests
from bs4 import BeautifulSoup


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov")


def clean_url(url: str) -> str:
    return html.unescape(url).replace("&amp;", "&")


def url_without_query(url: str) -> str:
    return url.split("?")[0].lower()


def is_direct_image_url(url: str) -> bool:
    return url_without_query(url).endswith(IMAGE_EXTENSIONS)


def is_direct_video_url(url: str) -> bool:
    return url_without_query(url).endswith(VIDEO_EXTENSIONS)


def dedupe_urls(urls: List[str]) -> List[str]:
    seen = set()
    unique_urls = []

    for url in urls:
        if not url:
            continue

        cleaned = clean_url(url)

        if cleaned not in seen:
            seen.add(cleaned)
            unique_urls.append(cleaned)

    return unique_urls


def extract_media_urls(entry) -> Dict[str, List[str]]:
    """
    Extract as many media URLs as possible from Reddit RSS.
    This works for images/GIFs that Reddit exposes in the RSS summary.
    It may not expose every gallery image or Reddit video.
    """

    image_urls = []
    video_urls = []

    # 1. RSS media thumbnails
    if hasattr(entry, "media_thumbnail"):
        for thumbnail in entry.media_thumbnail:
            url = thumbnail.get("url")
            if url:
                image_urls.append(url)

    # 2. RSS media content
    if hasattr(entry, "media_content"):
        for media_item in entry.media_content:
            url = media_item.get("url")
            if url:
                if is_direct_video_url(url):
                    video_urls.append(url)
                else:
                    image_urls.append(url)

    # 3. Parse summary HTML and collect ALL images/links
    summary_html = entry.get("summary", "")

    if summary_html:
        soup = BeautifulSoup(summary_html, "html.parser")

        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                image_urls.append(src)

        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue

            if is_direct_image_url(href):
                image_urls.append(href)

            if is_direct_video_url(href):
                video_urls.append(href)

    # 4. Feed links/enclosures
    for link in entry.get("links", []):
        href = link.get("href", "")

        if is_direct_image_url(href):
            image_urls.append(href)

        if is_direct_video_url(href):
            video_urls.append(href)

    return {
        "image_urls": dedupe_urls(image_urls),
        "video_urls": dedupe_urls(video_urls),
    }


def build_feed_url(subreddit_name: str, feed_mode: str) -> str:
    feed_mode = feed_mode.lower().strip()

    if feed_mode == "old":
        # Reddit RSS has no true /old sort.
        # We simulate older posts by reversing the /new batch.
        return f"https://www.reddit.com/r/{subreddit_name}/new/.rss"

    if feed_mode in ["new", "hot", "top", "rising"]:
        return f"https://www.reddit.com/r/{subreddit_name}/{feed_mode}/.rss"

    raise ValueError(f"Unsupported feed mode: {feed_mode}")


def fetch_rss_with_retry(
    feed_url: str,
    subreddit_name: str,
    feed_mode: str,
    max_retries: int = 2,
):
    headers = {
        "User-Agent": "DRBOT/0.1 contact: local-development"
    }

    wait_seconds = 10

    for attempt in range(1, max_retries + 1):
        response = requests.get(feed_url, headers=headers, timeout=10)

        print(
            f"Reddit RSS status for r/{subreddit_name} [{feed_mode}]: "
            f"{response.status_code} "
            f"(attempt {attempt}/{max_retries})"
        )

        if response.status_code == 200:
            return response.text

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            if retry_after and retry_after.isdigit():
                wait_seconds = int(retry_after)

            print(
                f"Rate limited for r/{subreddit_name} [{feed_mode}]. "
                f"Waiting {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)
            wait_seconds *= 2
            continue

        response.raise_for_status()

    print(f"Failed to fetch r/{subreddit_name} [{feed_mode}] after retries.")
    return None


def fetch_latest_posts(
    subreddit_name: str,
    feed_mode: str = "new",
    limit: int = 25,
) -> List[Dict]:
    feed_mode = feed_mode.lower().strip()

    feed_url = build_feed_url(
        subreddit_name=subreddit_name,
        feed_mode=feed_mode,
    )

    rss_text = fetch_rss_with_retry(
        feed_url=feed_url,
        subreddit_name=subreddit_name,
        feed_mode=feed_mode,
        max_retries=2,
    )

    if rss_text is None:
        return []

    feed = feedparser.parse(rss_text)

    entries = list(feed.entries[:limit])

    if feed_mode == "old":
        entries.reverse()

    posts = []

    for entry in entries:
        media = extract_media_urls(entry)

        posts.append(
            {
                "id": entry.id,
                "title": entry.title,
                "url": entry.link,
                "image_urls": media["image_urls"],
                "video_urls": media["video_urls"],
                "subreddit": subreddit_name,
                "feed_mode": feed_mode,
            }
        )

    return posts