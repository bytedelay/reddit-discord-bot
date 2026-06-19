from db import init_db, has_been_posted, mark_as_posted


def main():
    print("Starting database test...")

    init_db()

    test_post_id = "test123"

    already_posted_before = has_been_posted(test_post_id)
    print(f"Already posted before insert? {already_posted_before}")

    mark_as_posted(
        post_id=test_post_id,
        title="Test Reddit Post",
        reddit_url="https://www.reddit.com/r/phonewallpapers/",
        subreddit_name="python",
    )

    already_posted_after = has_been_posted(test_post_id)
    print(f"Already posted after insert? {already_posted_after}")

    print("Database test complete.")


if __name__ == "__main__":
    main()