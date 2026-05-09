from mini_crawler_lab import RenderDecision, RenderDecisionEngine


def test_decide_returns_http_ok_for_content_rich_static_html() -> None:
    html = """
    <html>
      <body>
        <h1>Documentation</h1>
        <p>Mini crawler lab has enough static page text for direct parsing.</p>
        <p>This paragraph adds realistic body copy for the crawler decision.</p>
        <p>Static HTML can be parsed without starting a browser in this case.</p>
        <p>More page copy keeps this over the useful content threshold.</p>
      </body>
    </html>
    """

    result = RenderDecisionEngine().decide(html)

    assert isinstance(result, RenderDecision)
    assert result.decision == "http_ok"
    assert not result.is_app_shell
    assert result.text_length >= 200
    assert result.link_count == 0
    assert result.rendered_text_length is None
    assert result.rendered_link_count is None
    assert "static_html_has_content" in result.reasons


def test_decide_requests_render_for_sparse_app_shell() -> None:
    html = """
    <html>
      <body>
        <div id="root"></div>
        <script src="/assets/runtime.js"></script>
        <script src="/assets/app.js"></script>
      </body>
    </html>
    """

    result = RenderDecisionEngine().decide(html)

    assert result.decision == "need_render"
    assert result.is_app_shell
    assert result.text_length == 0
    assert result.link_count == 0
    assert result.reasons == ["static_html_looks_like_app_shell"]


def test_decide_prefers_embedded_json_for_next_data() -> None:
    html = """
    <html>
      <body>
        <div id="__next"></div>
        <script id="__NEXT_DATA__" type="application/json">
          {"props":{"pageProps":{"title":"From JSON"}}}
        </script>
      </body>
    </html>
    """

    result = RenderDecisionEngine().decide(html)

    assert result.decision == "parse_embedded_json"
    assert result.has_next_data
    assert not result.has_initial_state
    assert "has_next_data" in result.reasons


def test_decide_prefers_embedded_json_for_initial_state() -> None:
    html = """
    <html>
      <body>
        <div id="app"></div>
        <script>
          window.__INITIAL_STATE__ = {"items": ["one", "two"]};
        </script>
      </body>
    </html>
    """

    result = RenderDecisionEngine().decide(html)

    assert result.decision == "parse_embedded_json"
    assert result.has_initial_state
    assert not result.has_next_data
    assert "has_initial_state" in result.reasons


def test_decide_requests_render_when_rendered_html_adds_content() -> None:
    static_html = """
    <html>
      <body>
        <main id="content">Loading</main>
        <script src="/client.js"></script>
      </body>
    </html>
    """
    rendered_html = """
    <html>
      <body>
        <main id="content">
          <h1>Loaded article</h1>
          <p>The rendered page now includes enough article text to crawl.</p>
          <p>It also exposes navigation anchors that were missing before.</p>
          <a href="/one">One</a>
          <a href="/two">Two</a>
          <a href="/three">Three</a>
        </main>
      </body>
    </html>
    """

    result = RenderDecisionEngine().decide(static_html, rendered_html=rendered_html)

    assert result.decision == "need_render"
    assert not result.is_app_shell
    assert result.text_length == len("Loading")
    assert result.link_count == 0
    assert result.rendered_text_length is not None
    assert result.rendered_text_length > result.text_length
    assert result.rendered_link_count == 3
    assert "rendered_html_is_richer" in result.reasons


def test_decide_returns_uncertain_for_sparse_non_shell_html() -> None:
    html = "<html><body><p>Coming soon</p></body></html>"

    result = RenderDecisionEngine().decide(html)

    assert result.decision == "uncertain"
    assert not result.is_app_shell
    assert result.text_length == len("Coming soon")
    assert result.link_count == 0
    assert result.reasons == []
