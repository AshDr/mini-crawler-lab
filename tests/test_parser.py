from mini_crawler_lab import HTMLParser, ParsedPage


def test_parse_extracts_title_links_and_text_length() -> None:
    html = """
    <html>
      <head>
        <title> Example Page </title>
        <style>.hidden { display: none; }</style>
      </head>
      <body>
        <h1>Hello</h1>
        <p>World</p>
        <a href="/about">About</a>
        <a href="https://other.example/path">Other</a>
        <a href="?page=2">Next</a>
        <script>console.log("skip me")</script>
      </body>
    </html>
    """

    result = HTMLParser().parse(html, "https://example.com/docs/index.html")

    assert isinstance(result, ParsedPage)
    assert result.title == "Example Page"
    assert result.links == [
        "https://example.com/about",
        "https://other.example/path",
        "https://example.com/docs/index.html?page=2",
    ]
    assert result.text_length == len("Hello World About Other Next")


def test_parse_handles_missing_title_and_relative_links() -> None:
    result = HTMLParser().parse(
        '<body><a href="../up">Up</a><a>No href</a>Text</body>',
        "https://example.com/a/b/page.html",
    )

    assert result.title == ""
    assert result.links == ["https://example.com/a/up"]
    assert result.text_length == len("Up No href Text")
