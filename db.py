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
                    subreddit_name
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (reddit_post_id) DO NOTHING;
                """,
                (post_id, title, reddit_url, subreddit_name),
            )

    print(f"Marked post as posted: {post_id}")