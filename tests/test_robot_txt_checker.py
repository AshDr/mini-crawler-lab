import json

import httpx
import pytest

from mini_crawler_lab import (
    RobotTxTChecker,
    RobotsTxt,
    RobotsTxtNotFoundError,
)


def test_fetch_parses_robots_txt_groups_rules_and_sitemaps() -> None:
    robots_text = """
    User-agent: *
    Disallow: /private
    Allow: /private/public
    Sitemap: https://example.com/sitemap.xml

    User-agent: BadBot
    Disallow: /
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/robots.txt"
        return httpx.Response(200, text=robots_text, request=request)

    checker = RobotTxTChecker(transport=httpx.MockTransport(handler))

    result = checker.fetch("example.com")

    assert isinstance(result, RobotsTxt)
    assert result.domain == "example.com"
    assert result.sitemaps == ["https://example.com/sitemap.xml"]
    assert len(result.groups) == 2
    assert result.groups[0].user_agents == ["*"]
    assert result.groups[0].rules[0].directive == "disallow"
    assert result.groups[0].rules[0].path == "/private"
    assert result.can_fetch("MiniCrawler", "https://example.com/private/public/page")
    assert not result.can_fetch("MiniCrawler", "https://example.com/private/page")
    assert not result.can_fetch("BadBot", "https://example.com/")


def test_fetch_accepts_wikipedia_robots_txt_url() -> None:
    robots_url = "https://en.wikipedia.org/robots.txt"
    robots_text = """
    User-agent: *
    Disallow: /w/
    Allow: /w/api.php?action=mobileview&
    Sitemap: https://en.wikipedia.org/sitemap.xml
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == robots_url
        return httpx.Response(200, text=robots_text, request=request)

    checker = RobotTxTChecker(transport=httpx.MockTransport(handler))

    result = checker.fetch(robots_url)

    assert result.domain == "en.wikipedia.org"
    assert result.url == robots_url
    assert result.sitemaps == ["https://en.wikipedia.org/sitemap.xml"]
    assert not result.can_fetch("MiniCrawler", "https://en.wikipedia.org/w/index.php")
    assert result.can_fetch(
        "MiniCrawler",
        "https://en.wikipedia.org/w/api.php?action=mobileview&format=json",
    )


def test_parse_zhihu_robots_txt_mock_content() -> None:
    robots_text = """
    User-agent: Baiduspider-image
    Disallow: /appview/
    Disallow: /login
    Disallow: /logout
    Disallow: /resetpassword
    Disallow: /terms
    Disallow: /search
    Disallow: /notifications
    Disallow: /settings
    Disallow: /inbox
    Disallow: /admin_inbox
    Disallow: /*?guide*
    Disallow: /en/

    User-agent: AdsBot-Google
    Allow: /en/
    Disallow: /

    User-agent: Sogou web spider
    Allow: /tardis/sogou/
    Disallow: /

    User-Agent: Google-Extended
    Disallow: /

    User-Agent: *
    Disallow: /
    """

    checker = RobotTxTChecker()

    result = checker.parse(robots_text, domain="zhihu.com")

    assert result.domain == "zhihu.com"
    assert len(result.groups) == 5
    assert not result.can_fetch("Baiduspider-image", "https://zhihu.com/login")
    assert not result.can_fetch("Baiduspider-image", "https://zhihu.com/question/1?guide=true")
    assert result.can_fetch("Baiduspider-image", "https://zhihu.com/question/1")
    assert result.can_fetch("AdsBot-Google", "https://zhihu.com/en/topic")
    assert not result.can_fetch("AdsBot-Google", "https://zhihu.com/question/1")
    assert result.can_fetch("Sogou web spider", "https://zhihu.com/tardis/sogou/page")
    assert not result.can_fetch("Sogou web spider", "https://zhihu.com/question/1")
    assert not result.can_fetch("Google-Extended", "https://zhihu.com/question/1")
    assert not result.can_fetch("MiniCrawler", "https://zhihu.com/question/1")


def test_parse_supports_rfc_9309_wildcard_and_end_anchor() -> None:
    checker = RobotTxTChecker()
    result = checker.parse(
        """
        User-agent: *
        Disallow: /*.pdf$
        """,
        domain="example.com",
    )

    assert not result.can_fetch("MiniCrawler", "/reports/final.pdf")
    assert result.can_fetch("MiniCrawler", "/reports/final.pdf?download=1")
    assert result.can_fetch("MiniCrawler", "/reports/final.pdf/preview")


def test_empty_disallow_does_not_block_requests() -> None:
    checker = RobotTxTChecker()
    result = checker.parse(
        """
        User-agent: *
        Disallow:
        """,
        domain="example.com",
    )

    assert result.can_fetch("MiniCrawler", "/anything")


def test_fetch_raises_clear_error_for_missing_robots_txt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    checker = RobotTxTChecker(transport=httpx.MockTransport(handler))

    with pytest.raises(RobotsTxtNotFoundError):
        checker.fetch("example.com")


def test_fetch_can_store_parsed_robots_txt(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /tmp", request=request)

    checker = RobotTxTChecker(
        transport=httpx.MockTransport(handler),
        storage_dir=tmp_path,
    )

    result = checker.fetch("example.com", store=True)
    stored_path = tmp_path / "example.com_robots.json"

    assert stored_path.exists()
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    assert stored["domain"] == result.domain
    assert stored["groups"][0]["rules"][0] == {"directive": "disallow", "path": "/tmp"}
    assert stored["raw_text"] == "User-agent: *\nDisallow: /tmp"
