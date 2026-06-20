import os

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from db import init_db, has_been_posted, mark_as_posted
from reddit_fetcher import fetch_latest_posts


load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "wallpapers")
POST_LIMIT = int(os.getenv("POST_LIMIT", 5))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", 5))


intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    init_db()

    if not check_reddit_posts.is_running():
        check_reddit_posts.start()


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_reddit_posts():
    print(f"Checking r/{SUBREDDIT_NAME}...")

    channel = client.get_channel(DISCORD_CHANNEL_ID)

    if channel is None:
        channel = await client.fetch_channel(DISCORD_CHANNEL_ID)

    posts = fetch_latest_posts(limit=POST_LIMIT)

    if not posts:
        print("No posts found.")
        return

    for post in reversed(posts):
        post_id = post["id"]
        title = post["title"]
        url = post["url"]
        image_url = post.get("image_url")
        subreddit = post["subreddit"]

        if has_been_posted(post_id):
            print(f"Already posted: {title}")
            continue

        image_url = post.get("image_url")

        embed = discord.Embed(
        title=title,
        url=url,
        description=f"New post from r/{subreddit}",
        )

        embed.add_field(name="Subreddit", value=f"r/{subreddit}", inline=True)
        embed.add_field(name="Post ID", value=post_id, inline=True)

        if image_url:
            embed.set_image(url=image_url)

        await channel.send(embed=embed)

        mark_as_posted(
            post_id=post_id,
            title=title,
            reddit_url=url,
            subreddit_name=subreddit,
        )

        print(f"Posted to Discord: {title}")


if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

client.run(DISCORD_TOKEN)