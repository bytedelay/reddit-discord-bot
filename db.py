import os 

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing. Check your .env file.")

    return psycopg.connect(DATABASE_URL)

def init_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Table 1: stores Reddit posts that were already sent to Discord
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_posts (
                    reddit_post_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    reddit_url TEXT NOT NULL,
                    subreddit_name TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            # Table 2: stores which subreddit should post to which Discord channel
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subreddit_configs (
                id SERIAL PRIMARY KEY,
                subreddit_name TEXT NOT NULL,
                discord_channel_id TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (subreddit_name, discord_channel_id)
                );
                """
            )

    print("Database initialized successfully.")


def has_been_posted(post_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM posted_posts
                WHERE reddit_post_id = %s;
                """,
                (post_id,),
            )

            return cursor.fetchone() is not None
        
def mark_as_posted(
    post_id: str,
    title: str,
    reddit_url: str,
    subreddit_name: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO posted_posts (
                    reddit_post_id,
                    title,
                    reddit_url,
                    subreddit_name,
                    status,
                    skip_reason
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (reddit_post_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    skip_reason = EXCLUDED.skip_reason;
                """,
                (
                    post_id,
                    title,
                    reddit_url,
                    subreddit_name,
                    "posted",
                    None,
                ),
            )

    print(f"Marked post as posted: {post_id}")

    
def add_subreddit_config(subreddit_name: str, discord_channel_id: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subreddit_configs (
                    subreddit_name,
                    discord_channel_id
                )
                VALUES (%s, %s)
                ON CONFLICT (subreddit_name, discord_channel_id) DO NOTHING;
                """,
                (subreddit_name, discord_channel_id),
            )

    print(f"Added config: r/{subreddit_name} -> channel {discord_channel_id}")


def get_active_subreddit_configs():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    subreddit_name,
                    discord_channel_id,
                    COALESCE(feed_modes, 'old,hot,new') AS feed_modes,
                    COALESCE(post_limit, 25) AS post_limit
                FROM subreddit_configs
                WHERE is_active = TRUE
                ORDER BY id ASC;
                """
            )

            return cursor.fetchall()
        
def has_been_processed(post_id: str) -> bool:
    """
    Returns True if the Reddit post was either posted or intentionally skipped.
    This prevents the bot from repeatedly checking the same text-only/no-media posts.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM posted_posts
                WHERE reddit_post_id = %s;
                """,
                (post_id,),
            )

            return cursor.fetchone() is not None


def mark_as_skipped(
    post_id: str,
    title: str,
    reddit_url: str,
    subreddit_name: str,
    reason: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO posted_posts (
                    reddit_post_id,
                    title,
                    reddit_url,
                    subreddit_name,
                    status,
                    skip_reason
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (reddit_post_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    skip_reason = EXCLUDED.skip_reason;
                """,
                (
                    post_id,
                    title,
                    reddit_url,
                    subreddit_name,
                    "skipped",
                    reason,
                ),
            )

    print(f"Marked post as skipped: {post_id} | Reason: {reason}")