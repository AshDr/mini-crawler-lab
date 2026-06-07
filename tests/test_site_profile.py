import pytest

from mini_crawler_lab import ProfileStore, SiteProfile


def test_site_profile_normalizes_domain_and_patterns() -> None:
    profile = SiteProfile(
        domain="https://Example.COM/products/1",
        default_fetch_mode="render",
        max_rps="2.5",
        js_required_patterns=["/app/", "", "  /hydrate  "],
        api_patterns="/api/",
        render_policy="always",
        last_verified="2026-05-11T12:00:00+08:00",
    )

    assert profile.domain == "example.com"
    assert profile.max_rps == 2.5
    assert profile.js_required_patterns == ("/app/", "/hydrate")
    assert profile.api_patterns == ("/api/",)
    assert profile.to_dict() == {
        "domain": "example.com",
        "default_fetch_mode": "render",
        "max_rps": 2.5,
        "js_required_patterns": ["/app/", "/hydrate"],
        "api_patterns": ["/api/"],
        "render_policy": "always",
        "last_verified": "2026-05-11T12:00:00+08:00",
    }


def test_site_profile_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="default_fetch_mode"):
        SiteProfile(domain="example.com", default_fetch_mode="browser")

    with pytest.raises(ValueError, match="max_rps"):
        SiteProfile(domain="example.com", max_rps=0)

    with pytest.raises(ValueError, match="render_policy"):
        SiteProfile(domain="example.com", render_policy="maybe")


def test_profile_store_loads_profiles_from_yaml(tmp_path) -> None:
    profile_path = tmp_path / "profiles.yaml"
    profile_path.write_text(
        """
profiles:
  - domain: example.com
    default_fetch_mode: http
    max_rps: 1.5
    js_required_patterns:
      - /app/
      - /products/.*
    api_patterns:
      - /api/
    render_policy: auto
    last_verified: "2026-05-11"
  - domain: https://Shop.Example.com/catalog
    default_fetch_mode: api
    max_rps: 4
    js_required_patterns:
    api_patterns:
      - /graphql
    render_policy: never
    last_verified: null
""",
        encoding="utf-8",
    )

    store = ProfileStore.load_yaml(profile_path)

    assert store.path == profile_path
    assert store.require("https://example.com/page").default_fetch_mode == "http"
    assert store.require("shop.example.com").domain == "shop.example.com"
    assert store.require("shop.example.com").api_patterns == ("/graphql",)
    assert store.get("missing.example") is None


def test_profile_store_updates_domain_and_saves_yaml(tmp_path) -> None:
    profile_path = tmp_path / "profiles.yaml"
    store = ProfileStore(
        [
            SiteProfile(
                domain="example.com",
                default_fetch_mode="http",
                max_rps=1,
            ),
        ],
        path=profile_path,
    )

    updated = store.update(
        "https://EXAMPLE.com/page",
        default_fetch_mode="render",
        max_rps=3,
        js_required_patterns=["/app/"],
        render_policy="always",
        last_verified="2026-05-11",
    )
    reloaded = ProfileStore.load_yaml(profile_path)

    assert updated.domain == "example.com"
    assert updated.default_fetch_mode == "render"
    assert updated.max_rps == 3
    assert reloaded.require("example.com").js_required_patterns == ("/app/",)
    assert reloaded.require("example.com").render_policy == "always"
    assert "profiles:" in profile_path.read_text(encoding="utf-8")


def test_profile_store_save_requires_path_before_mutating() -> None:
    store = ProfileStore([SiteProfile(domain="example.com", max_rps=1)])

    with pytest.raises(ValueError, match="no path"):
        store.update("example.com", max_rps=2)

    assert store.require("example.com").max_rps == 1


def test_profile_store_supports_domain_keyed_yaml(tmp_path) -> None:
    profile_path = tmp_path / "profiles.yaml"
    profile_path.write_text(
        """
example.com:
  default_fetch_mode: api
  max_rps: 2
  js_required_patterns:
    - /client/
  api_patterns:
    - /v1/
  render_policy: never
  last_verified: 2026-05-11
""",
        encoding="utf-8",
    )

    store = ProfileStore.from_yaml(profile_path)

    assert store.require("example.com").default_fetch_mode == "api"
    assert store.require("example.com").last_verified == "2026-05-11"
