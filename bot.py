import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from db import (
    init_db,
    has_been_processed,
    mark_as_posted,
    mark_as_skipped,
    get_active_subreddit_configs,
    list_subreddit_configs,
    upsert_subreddit_config,
    remove_subreddit_config,
    set_subreddit_active,
    clear_processed_posts_for_subreddit,
)
from reddit_fetcher import fetch_latest_posts


load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

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
tree = app_commands.CommandTree(client)
slash_commands_synced = False

@client.event
async def on_ready():
    global slash_commands_synced

    print(f"Logged in as {client.user}")

    init_db()

    if not slash_commands_synced:
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash commands to guild {DISCORD_GUILD_ID}.")
        else:
            synced = await tree.sync()
            print(f"Synced {len(synced)} global slash commands.")

        slash_commands_synced = True

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
        media_hint = post.get("media_hint", "unknown")
        has_media_candidate = post.get("has_media_candidate", False)

        if has_media_candidate:
            description = (
                f"New post from r/{subreddit}\n\n"
                f"Media detected, but RSS did not expose direct image URLs.\n"
                f"Open the Reddit post to view the full carousel/gallery."
            )
        else:
            description = f"New post from r/{subreddit}"

        embed = discord.Embed(
            title=title,
            url=url,
            description=description,
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
            name="Media Hint",
            value=media_hint,
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

                if has_been_processed(post_id):
                    print(f"Already processed, skipping: {title}")
                    continue
                has_media_candidate = post.get("has_media_candidate", False)
                media_hint = post.get("media_hint", "unknown")

                if not image_urls and not video_urls and not has_media_candidate:
                    print(f"No media found, soft skipping: {title}")
                    continue
                
                '''
                if not image_urls and not video_urls:
                    print(f"No media found, permanently skipping: {title}")

                    mark_as_skipped(
                        post_id=post_id,
                        title=title,
                        reddit_url=url,
                        subreddit_name=subreddit,
                        reason="no_media_found",
                    )

                    continue
                '''
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

ALLOWED_FEED_MODES = {"old", "hot", "new", "top", "rising"}


def user_can_manage_bot(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    permissions = interaction.user.guild_permissions

    return permissions.administrator or permissions.manage_guild


def validate_modes(modes: str) -> tuple[bool, str]:
    mode_list = [
        mode.strip().lower()
        for mode in modes.split(",")
        if mode.strip()
    ]

    if not mode_list:
        return False, "No feed modes provided."

    invalid_modes = [
        mode
        for mode in mode_list
        if mode not in ALLOWED_FEED_MODES
    ]

    if invalid_modes:
        return (
            False,
            f"Invalid mode(s): {', '.join(invalid_modes)}. "
            f"Allowed: {', '.join(sorted(ALLOWED_FEED_MODES))}",
        )

    return True, ",".join(mode_list)

@tree.command(
    name="drbot_add",
    description="Add or update a subreddit feed config.",
)
async def drbot_add(
    interaction: discord.Interaction,
    subreddit: str,
    modes: str = "old,hot,new",
    limit: int = 25,
    channel: Optional[discord.TextChannel] = None,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    if limit < 1 or limit > 100:
        await interaction.response.send_message(
            "Limit must be between 1 and 100.",
            ephemeral=True,
        )
        return

    modes_are_valid, normalized_modes_or_error = validate_modes(modes)

    if not modes_are_valid:
        await interaction.response.send_message(
            normalized_modes_or_error,
            ephemeral=True,
        )
        return

    target_channel = channel or interaction.channel

    upsert_subreddit_config(
        subreddit_name=subreddit,
        discord_channel_id=str(target_channel.id),
        feed_modes=normalized_modes_or_error,
        post_limit=limit,
    )

    await interaction.response.send_message(
        f"Added/updated `r/{subreddit}` → {target_channel.mention}\n"
        f"Modes: `{normalized_modes_or_error}`\n"
        f"Limit: `{limit}`",
        ephemeral=True,
    )


@tree.command(
    name="drbot_list",
    description="List all subreddit feed configs.",
)
async def drbot_list(interaction: discord.Interaction):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    configs = list_subreddit_configs()

    if not configs:
        await interaction.response.send_message(
            "No subreddit configs found.",
            ephemeral=True,
        )
        return

    lines = []

    for row in configs:
        (
            config_id,
            subreddit_name,
            discord_channel_id,
            is_active,
            feed_modes,
            post_limit,
            created_at,
        ) = row

        status = "ACTIVE" if is_active else "INACTIVE"

        lines.append(
            f"`{config_id}` | r/{subreddit_name} | "
            f"<#{discord_channel_id}> | {status} | "
            f"modes=`{feed_modes}` | limit=`{post_limit}`"
        )

    message = "\n".join(lines)

    if len(message) > 1800:
        message = message[:1800] + "\n...truncated"

    await interaction.response.send_message(
        message,
        ephemeral=True,
    )


@tree.command(
    name="drbot_remove",
    description="Remove a subreddit feed config.",
)
async def drbot_remove(
    interaction: discord.Interaction,
    subreddit: str,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    deleted_count = remove_subreddit_config(subreddit)

    await interaction.response.send_message(
        f"Removed `{deleted_count}` config(s) for `r/{subreddit}`.",
        ephemeral=True,
    )


@tree.command(
    name="drbot_pause",
    description="Pause a subreddit feed without deleting it.",
)
async def drbot_pause(
    interaction: discord.Interaction,
    subreddit: str,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    updated_count = set_subreddit_active(
        subreddit_name=subreddit,
        is_active=False,
    )

    await interaction.response.send_message(
        f"Paused `{updated_count}` config(s) for `r/{subreddit}`.",
        ephemeral=True,
    )


@tree.command(
    name="drbot_resume",
    description="Resume a paused subreddit feed.",
)
async def drbot_resume(
    interaction: discord.Interaction,
    subreddit: str,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    updated_count = set_subreddit_active(
        subreddit_name=subreddit,
        is_active=True,
    )

    await interaction.response.send_message(
        f"Resumed `{updated_count}` config(s) for `r/{subreddit}`.",
        ephemeral=True,
    )


@tree.command(
    name="drbot_clear",
    description="Clear processed post history for a subreddit.",
)
async def drbot_clear(
    interaction: discord.Interaction,
    subreddit: str,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    deleted_count = clear_processed_posts_for_subreddit(subreddit)

    await interaction.response.send_message(
        f"Cleared `{deleted_count}` processed post(s) for `r/{subreddit}`.",
        ephemeral=True,
    )


@tree.command(
    name="drbot_fetch",
    description="Fetch and post one subreddit item immediately without saving config.",
)
async def drbot_fetch(
    interaction: discord.Interaction,
    subreddit: str,
    mode: str = "hot",
    limit: int = 25,
    channel: Optional[discord.TextChannel] = None,
):
    if not user_can_manage_bot(interaction):
        await interaction.response.send_message(
            "You need Manage Server or Administrator permission to use this.",
            ephemeral=True,
        )
        return

    mode = mode.strip().lower()

    if mode not in ALLOWED_FEED_MODES:
        await interaction.response.send_message(
            f"Invalid mode `{mode}`. Allowed: {', '.join(sorted(ALLOWED_FEED_MODES))}",
            ephemeral=True,
        )
        return

    if limit < 1 or limit > 100:
        await interaction.response.send_message(
            "Limit must be between 1 and 100.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    target_channel = channel or interaction.channel

    posts = fetch_latest_posts(
        subreddit_name=subreddit,
        feed_mode=mode,
        limit=limit,
    )

    if not posts:
        await interaction.followup.send(
            f"No posts found for `r/{subreddit}` using mode `{mode}`.",
            ephemeral=True,
        )
        return

    for post in posts:
        post_id = post["id"]
        title = post["title"]
        url = post["url"]
        image_urls = post.get("image_urls", [])
        video_urls = post.get("video_urls", [])
        has_media_candidate = post.get("has_media_candidate", False)

        if has_been_processed(post_id):
            continue

        if not image_urls and not video_urls and not has_media_candidate:
            continue

        await send_reddit_post_to_discord(
            channel=target_channel,
            post=post,
        )

        mark_as_posted(
            post_id=post_id,
            title=title,
            reddit_url=url,
            subreddit_name=subreddit,
        )

        await interaction.followup.send(
            f"Posted one item from `r/{subreddit}` using `{mode}` to {target_channel.mention}.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"No unprocessed media/candidate posts found for `r/{subreddit}` using `{mode}`.",
        ephemeral=True,
    )

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

client.run(DISCORD_TOKEN)