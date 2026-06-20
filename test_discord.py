import os

import discord
from dotenv import load_dotenv


load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))


intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    channel = client.get_channel(DISCORD_CHANNEL_ID)

    if channel is None:
        channel = await client.fetch_channel(DISCORD_CHANNEL_ID)

    await channel.send("DRBOT test message: Discord connection is working.")

    print("Test message sent.")
    await client.close()


if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

client.run(DISCORD_TOKEN)