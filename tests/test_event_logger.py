import json

from mini_crawler_lab import CrawlEvent, EventLogger, summarize


def test_crawl_event_to_dict_contains_expected_fields() -> None:
    event = CrawlEvent(
        url="https://example.com/page",
        domain="example.com",
        fetch_mode="http",
        status_code=200,
        error_type=None,
        elapsed_ms=12.5,
        content_length=123,
        timestamp="2026-05-03T00:00:00+00:00",
    )

    assert event.to_dict() == {
        "url": "https://example.com/page",
        "domain": "example.com",
        "fetch_mode": "http",
        "status_code": 200,
        "error_type": None,
        "elapsed_ms": 12.5,
        "content_length": 123,
        "timestamp": "2026-05-03T00:00:00+00:00",
    }


def test_event_logger_writes_json_lines(tmp_path) -> None:
    path = tmp_path / "logs" / "crawl.jsonl"
    logger = EventLogger(path)

    logger.log(
        CrawlEvent(
            url="https://example.com/ok",
            domain="example.com",
            fetch_mode="http",
            status_code=200,
            error_type=None,
            elapsed_ms=10.0,
            content_length=20,
            timestamp="2026-05-03T00:00:00+00:00",
        )
    )
    logger.log(
        CrawlEvent(
            url="https://example.com/timeout",
            domain="example.com",
            fetch_mode="http",
            status_code=None,
            error_type="timeout",
            elapsed_ms=30.0,
            content_length=None,
            timestamp="2026-05-03T00:00:01+00:00",
        )
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert rows == [
        {
            "url": "https://example.com/ok",
            "domain": "example.com",
            "fetch_mode": "http",
            "status_code": 200,
            "error_type": None,
            "elapsed_ms": 10.0,
            "content_length": 20,
            "timestamp": "2026-05-03T00:00:00+00:00",
        },
        {
            "url": "https://example.com/timeout",
            "domain": "example.com",
            "fetch_mode": "http",
            "status_code": None,
            "error_type": "timeout",
            "elapsed_ms": 30.0,
            "content_length": None,
            "timestamp": "2026-05-03T00:00:01+00:00",
        },
    ]


def test_summarize_returns_success_rate_key_status_counts_timeout_and_average_elapsed(
    tmp_path,
) -> None:
    path = tmp_path / "crawl.jsonl"
    logger = EventLogger(path)
    events = [
        CrawlEvent("https://example.com/ok", "example.com", "http", 200, None, 10.0, 100),
        CrawlEvent("https://example.com/redirect", "example.com", "http", 302, None, 20.0, 0),
        CrawlEvent("https://example.com/403", "example.com", "http", 403, None, 30.0, 50),
        CrawlEvent("https://example.com/429", "example.com", "http", 429, None, 40.0, 50),
        CrawlEvent("https://example.com/timeout", "example.com", "http", None, "timeout", 50.0, None),
    ]
    for event in events:
        logger.log(event)

    assert EventLogger.summarize(path) == {
        "total": 5,
        "successful": 2,
        "success_rate": 0.4,
        "403": 1,
        "429": 1,
        "timeout": 1,
        "average_elapsed_ms": 30.0,
    }
    assert summarize(path)["success_rate"] == 0.4


def test_summarize_missing_file_returns_zero_summary(tmp_path) -> None:
    assert EventLogger.summarize(tmp_path / "missing.jsonl") == {
        "total": 0,
        "successful": 0,
        "success_rate": 0.0,
        "403": 0,
        "429": 0,
        "timeout": 0,
        "average_elapsed_ms": 0.0,
    }
