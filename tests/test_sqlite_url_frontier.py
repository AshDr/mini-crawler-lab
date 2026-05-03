import sqlite3

from mini_crawler_lab import SQLiteUrlFrontier


def test_add_url_returns_true_only_for_unique_urls() -> None:
    frontier = SQLiteUrlFrontier()

    assert frontier.add_url("https://example.com/a")
    assert not frontier.add_url("https://example.com/a")

    frontier.close()


def test_get_next_returns_highest_priority_pending_url_first() -> None:
    frontier = SQLiteUrlFrontier()
    frontier.add_url("https://example.com/low", priority=1)
    frontier.add_url("https://example.com/high", priority=10)
    frontier.add_url("https://example.com/mid", priority=5)

    assert frontier.get_next() == "https://example.com/high"
    frontier.mark_done("https://example.com/high")
    assert frontier.get_next() == "https://example.com/mid"

    frontier.close()


def test_mark_done_removes_url_from_pending_queue() -> None:
    frontier = SQLiteUrlFrontier()
    frontier.add_url("https://example.com/done")

    assert frontier.mark_done("https://example.com/done")
    assert frontier.get_next() is None

    frontier.close()


def test_mark_failed_retries_until_max_retry_is_exceeded() -> None:
    frontier = SQLiteUrlFrontier(max_retry=2)
    frontier.add_url("https://example.com/retry")

    assert frontier.mark_failed("https://example.com/retry", "timeout")
    assert frontier.get_next() == "https://example.com/retry"
    assert frontier.mark_failed("https://example.com/retry", "timeout")
    assert frontier.get_next() == "https://example.com/retry"
    assert frontier.mark_failed("https://example.com/retry", "timeout")
    assert frontier.get_next() is None

    frontier.close()


def test_frontier_persists_status_retry_count_and_error_type(tmp_path) -> None:
    db_path = tmp_path / "frontier.sqlite"
    frontier = SQLiteUrlFrontier(db_path, max_retry=0)
    frontier.add_url("https://example.com/fail")
    frontier.mark_failed("https://example.com/fail", "invalid_url")
    frontier.close()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT status, retry_count, error_type
        FROM url_frontier
        WHERE url = ?
        """,
        ("https://example.com/fail",),
    ).fetchone()
    conn.close()

    assert row == ("failed", 1, "invalid_url")


def test_mark_methods_return_false_for_unknown_urls() -> None:
    frontier = SQLiteUrlFrontier()

    assert not frontier.mark_done("https://example.com/missing")
    assert not frontier.mark_failed("https://example.com/missing", "timeout")

    frontier.close()
