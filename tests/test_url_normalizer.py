from mini_crawler_lab import SeenUrlStore, URLNormalizer


def test_normalize_lowercases_scheme_and_host() -> None:
    normalizer = URLNormalizer()

    result = normalizer.normalize("HTTPS://Example.COM/Some/Path")

    assert result == "https://example.com/Some/Path"


def test_normalize_removes_fragment() -> None:
    normalizer = URLNormalizer()

    result = normalizer.normalize("https://example.com/page?a=1#section")

    assert result == "https://example.com/page?a=1"


def test_normalize_removes_tracking_query_params_and_sorts_remaining_params() -> None:
    normalizer = URLNormalizer()

    result = normalizer.normalize(
        "https://example.com/page?utm_source=news&b=2&gclid=ad&a=1&fbclid=fb&utm_medium=email"
    )

    assert result == "https://example.com/page?a=1&b=2"


def test_normalize_treats_tracking_query_keys_case_insensitively() -> None:
    normalizer = URLNormalizer()

    result = normalizer.normalize(
        "https://example.com/page?UTM_Source=news&FbClId=fb&GCLID=ad&keep=yes"
    )

    assert result == "https://example.com/page?keep=yes"


def test_normalize_resolves_relative_url_with_base_url() -> None:
    normalizer = URLNormalizer()

    result = normalizer.normalize("../about?z=9&a=1#top", "HTTPS://Example.COM/docs/page")

    assert result == "https://example.com/about?a=1&z=9"


def test_normalize_can_remove_trailing_slash() -> None:
    normalizer = URLNormalizer(keep_trailing_slash=False)

    result = normalizer.normalize("https://example.com/docs/")

    assert result == "https://example.com/docs"


def test_normalize_keeps_root_slash_when_removing_trailing_slash() -> None:
    normalizer = URLNormalizer(keep_trailing_slash=False)

    result = normalizer.normalize("https://example.com/")

    assert result == "https://example.com/"


def test_seen_url_store_returns_true_only_for_new_normalized_urls() -> None:
    store = SeenUrlStore(URLNormalizer(keep_trailing_slash=False))

    assert store.add("HTTPS://Example.COM/docs/?utm_source=news&b=2&a=1#top")
    assert not store.add("https://example.com/docs?a=1&b=2")
    assert store.add("https://example.com/other")
    assert store.has_seen("/docs?b=2&a=1", "https://example.com/base")
    assert len(store) == 2
