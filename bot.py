import os

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from db import (
    init_db,
    has_been_posted,
    mark_as_posted,
    get_active_subreddit_configs,
)
from reddit_fetcher import fetch_latest_posts


load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

POST_LIMIT = int(os.getenv("POST_LIMIT", 25))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", 5))

FEED_MODES = [
    mode.strip().lower()
    for mode in os.getenv("FEED_MODES", "old,hot,new").split(",")
    if mode.strip()
]

rotation_pointer = 0

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    init_db()

    print(f"Feed modes: {FEED_MODES}")
    print(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
    print(f"Post candidate limit: {POST_LIMIT}")

    if not check_reddit_posts.is_running():
        check_reddit_posts.start()


async def send_reddit_post_to_discord(channel, post: dict):
    post_id = post["id"]
    title = post["title"]
    url = post["url"]
    subreddit = post["subreddit"]
    source_mode = post["feed_mode"]

    image_urls = post.get("image_urls", [])
    video_urls = post.get("video_urls", [])

    # Discord allows up to 10 embeds in one message.
    # So we send up to 10 images from a Reddit gallery/post.
    if image_urls:
        embeds = []

        for index, image_url in enumerate(image_urls[:10], start=1):
            embed = discord.Embed(
                title=title if index == 1 else f"{title} — image {index}",
                url=url,
                description=f"New post from r/{subreddit}",
            )

            embed.add_field(
                name="Subreddit",
                value=f"r/{subreddit}",
                inline=True,
            )

            embed.add_field(
                name="Mode",
                value=source_mode,
                inline=True,
            )

            embed.add_field(
                name="Image",
                value=f"{index}/{len(image_urls)}",
                inline=True,
            )

            embed.set_image(url=image_url)
            embeds.append(embed)

        await channel.send(embeds=embeds)

    else:
        embed = discord.Embed(
            title=title,
            url=url,
            description=f"New post from r/{subreddit}",
        )

        embed.add_field(
            name="Subreddit",
            value=f"r/{subreddit}",
            inline=True,
        )

        embed.add_field(
            name="Mode",
            value=source_mode,
            inline=True,
        )

        embed.add_field(
            name="Post ID",
            value=post_id,
            inline=True,
        )

        await channel.send(embed=embed)

    # Send direct video links separately if the RSS extractor found any.
    # Discord usually previews direct .mp4/.webm/.gif links better as normal messages.
    if video_urls:
        for video_url in video_urls[:3]:
            await channel.send(
                f"Video from **r/{subreddit}**:\n"
                f"{video_url}\n"
                f"Original post: {url}"
            )


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_reddit_posts():
    global rotation_pointer

    print("Checking active subreddit configs...")

    configs = get_active_subreddit_configs()

    if not configs:
        print("No active subreddit configs found.")
        return

    jobs = []

    for subreddit_name, discord_channel_id, feed_modes_text, config_post_limit in configs:
        feed_modes = [
            mode.strip().lower()
            for mode in feed_modes_text.split(",")
                if mode.strip()
        ]

        for feed_mode in feed_modes:
            jobs.append(
                {
                    "subreddit_name": subreddit_name,
                    "discord_channel_id": discord_channel_id,
                    "feed_mode": feed_mode,
                    "post_limit": config_post_limit,
                }
            )

    if not jobs:
        print("No jobs available.")
        return

    start_index = rotation_pointer % len(jobs)

    # Try every subreddit/mode pair until we find one unposted post.
    for offset in range(len(jobs)):
        job_index = (start_index + offset) % len(jobs)
        job = jobs[job_index]

        subreddit_name = job["subreddit_name"]
        discord_channel_id = job["discord_channel_id"]
        feed_mode = job["feed_mode"]
        job_post_limit = job["post_limit"]

        print(
            f"Trying r/{subreddit_name} [{feed_mode}] "
            f"for channel {discord_channel_id}..."
        )

        try:
            channel_id = int(discord_channel_id)

            channel = client.get_channel(channel_id)

            if channel is None:
                channel = await client.fetch_channel(channel_id)

            posts = fetch_latest_posts(
                subreddit_name=subreddit_name,
                feed_mode=feed_mode,
                limit=job_post_limit,
            )

            if not posts:
                print(f"No posts found for r/{subreddit_name} [{feed_mode}].")
                continue

            for post in posts:
                post_id = post["id"]
                title = post["title"]
                url = post["url"]
                subreddit = post["subreddit"]

                image_urls = post.get("image_urls", [])
                video_urls = post.get("video_urls", [])

                if has_been_posted(post_id):
                    print(f"Repeat found, skipping: {title}")
                    continue

                if not image_urls and not video_urls:
                    print(f"Text-only post skipped: {title}")
                    continue

                await send_reddit_post_to_discord(
                channel=channel,
                post=post,
                )

                mark_as_posted(
                    post_id=post_id,
                    title=title,
                    reddit_url=url,
                    subreddit_name=subreddit,
                )

                print(f"Posted to Discord: {title}")

                # Next cycle starts from the next subreddit/mode pair.
                rotation_pointer = job_index + 1

                # Important: only one Reddit post per cycle.
                return

            print(
                f"All candidate posts were repeats for "
                f"r/{subreddit_name} [{feed_mode}]."
            )

        except Exception as error:
            print(
                f"Error while processing "
                f"r/{subreddit_name} [{feed_mode}]: {error}"
            )

    print("No unposted posts found in any active subreddit/mode.")


if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

client.run(DISCORD_TOKEN)