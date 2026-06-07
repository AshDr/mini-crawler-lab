from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, List, Literal, Mapping, Optional, Tuple
from urllib.parse import urlparse


FetchMode = Literal["http", "render", "api"]
RenderPolicy = Literal["auto", "always", "never"]

_FETCH_MODES = {"http", "render", "api"}
_RENDER_POLICIES = {"auto", "always", "never"}
_PROFILE_FIELDS = {
    "domain",
    "default_fetch_mode",
    "max_rps",
    "js_required_patterns",
    "api_patterns",
    "render_policy",
    "last_verified",
}


@dataclass(frozen=True)
class SiteProfile:
    """Per-domain crawling preferences loaded from profile configuration."""

    domain: str
    default_fetch_mode: FetchMode = "http"
    max_rps: float = 1.0
    js_required_patterns: Tuple[str, ...] = ()
    api_patterns: Tuple[str, ...] = ()
    render_policy: RenderPolicy = "auto"
    last_verified: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize and validate profile fields after dataclass construction."""
        domain = normalize_domain(self.domain)
        if not domain:
            raise ValueError("domain must not be empty")

        default_fetch_mode = str(self.default_fetch_mode)
        if default_fetch_mode not in _FETCH_MODES:
            raise ValueError("default_fetch_mode must be one of: http, render, api")

        max_rps = float(self.max_rps)
        if max_rps <= 0:
            raise ValueError("max_rps must be greater than 0")

        render_policy = str(self.render_policy)
        if render_policy not in _RENDER_POLICIES:
            raise ValueError("render_policy must be one of: auto, always, never")

        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "default_fetch_mode", default_fetch_mode)
        object.__setattr__(self, "max_rps", max_rps)
        object.__setattr__(
            self,
            "js_required_patterns",
            _normalize_patterns(self.js_required_patterns),
        )
        object.__setattr__(
            self,
            "api_patterns",
            _normalize_patterns(self.api_patterns),
        )
        object.__setattr__(self, "render_policy", render_policy)
        object.__setattr__(
            self,
            "last_verified",
            _normalize_last_verified(self.last_verified),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SiteProfile":
        """Build and validate a profile from a mapping loaded from YAML."""
        unknown_fields = set(data) - _PROFILE_FIELDS
        if unknown_fields:
            unknown_list = ", ".join(sorted(unknown_fields))
            raise ValueError(f"unknown site profile fields: {unknown_list}")
        if "domain" not in data:
            raise ValueError("site profile requires a domain")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML-friendly dictionary with stable field ordering."""
        return {
            "domain": self.domain,
            "default_fetch_mode": self.default_fetch_mode,
            "max_rps": self.max_rps,
            "js_required_patterns": list(self.js_required_patterns),
            "api_patterns": list(self.api_patterns),
            "render_policy": self.render_policy,
            "last_verified": self.last_verified,
        }


class ProfileStore:
    """Mutable profile registry that can load from and save to a YAML file."""

    def __init__(
        self,
        profiles: Iterable[SiteProfile] = (),
        path: Optional[str | Path] = None,
    ) -> None:
        """Initialize the store with optional profiles and backing file path."""
        self.path = None if path is None else Path(path)
        self._profiles: dict[str, SiteProfile] = {}

        for profile in profiles:
            self.set(profile)

    @classmethod
    def load_yaml(cls, path: str | Path) -> "ProfileStore":
        """Load profiles from a YAML file and remember the path for saving."""
        yaml_path = Path(path)
        data = _load_yaml(yaml_path)
        return cls(_profiles_from_yaml_document(data), path=yaml_path)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProfileStore":
        """Alias for load_yaml for callers that prefer constructor naming."""
        return cls.load_yaml(path)

    @property
    def profiles(self) -> Tuple[SiteProfile, ...]:
        """Return profiles sorted by domain for deterministic iteration."""
        return tuple(self._profiles[domain] for domain in sorted(self._profiles))

    def to_dict(self) -> dict[str, Any]:
        """Return a YAML-friendly document preserving deterministic ordering."""
        return {"profiles": [profile.to_dict() for profile in self.profiles]}

    def save(self, path: Optional[str | Path] = None) -> None:
        """Persist the store to YAML using the current or provided file path."""
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("profile store has no path to save to")

        target.parent.mkdir(parents=True, exist_ok=True)
        _dump_yaml(target, self.to_dict())
        self.path = target

    def get(self, domain: str) -> Optional[SiteProfile]:
        """Return a profile by host or URL, or None when it is unknown."""
        return self._profiles.get(normalize_domain(domain))

    def require(self, domain: str) -> SiteProfile:
        """Return a profile by host or URL, raising KeyError if absent."""
        key = normalize_domain(domain)
        try:
            return self._profiles[key]
        except KeyError as exc:
            raise KeyError(f"no site profile for domain: {key}") from exc

    def set(self, profile: SiteProfile, save: bool = False) -> SiteProfile:
        """Insert or replace a profile and optionally persist the change."""
        if save and self.path is None:
            raise ValueError("profile store has no path to save to")

        self._profiles[profile.domain] = profile
        if save:
            self.save()
        return profile

    def update(
        self,
        domain: str,
        save: bool = True,
        **changes: Any,
    ) -> SiteProfile:
        """Update or create one domain profile and optionally save the file."""
        if "domain" in changes:
            raise ValueError("domain cannot be updated through changes")
        if save and self.path is None:
            raise ValueError("profile store has no path to save to")

        key = normalize_domain(domain)
        profile = self._profiles.get(key, SiteProfile(domain=key))
        updated = replace(profile, **changes)
        self._profiles[updated.domain] = updated

        if save:
            self.save()

        return updated

    def update_profile(
        self,
        domain: str,
        save: bool = True,
        **changes: Any,
    ) -> SiteProfile:
        """Alias for update with a more explicit method name."""
        return self.update(domain, save=save, **changes)


def normalize_domain(domain: str) -> str:
    """Normalize a host or URL into the profile store's stable domain key."""
    value = str(domain or "").strip()
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or parsed.netloc or parsed.path
    return host.strip().lower().rstrip(".")


def _profiles_from_yaml_document(data: Any) -> List[SiteProfile]:
    """Convert supported YAML document shapes into validated profiles."""
    if data is None:
        return []

    if isinstance(data, list):
        return [SiteProfile.from_mapping(_ensure_mapping(item)) for item in data]

    if isinstance(data, Mapping):
        if "profiles" in data:
            profiles = data["profiles"] or []
            if not isinstance(profiles, list):
                raise ValueError("profiles must be a list")
            return [
                SiteProfile.from_mapping(_ensure_mapping(item)) for item in profiles
            ]

        return [
            SiteProfile.from_mapping({"domain": domain, **_ensure_mapping(values)})
            for domain, values in data.items()
        ]

    raise ValueError("site profile YAML must be a mapping or a list")


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    """Validate that a YAML profile entry is a mapping."""
    if not isinstance(value, Mapping):
        raise ValueError("site profile entries must be mappings")
    return value


def _normalize_patterns(patterns: Iterable[Any] | str | None) -> Tuple[str, ...]:
    """Normalize configured URL patterns into a tuple of non-empty strings."""
    if patterns is None:
        return ()
    if isinstance(patterns, str):
        items = (patterns,)
    else:
        items = patterns
    return tuple(str(pattern).strip() for pattern in items if str(pattern).strip())


def _normalize_last_verified(value: Any) -> Optional[str]:
    """Normalize date-like values to ISO strings while preserving text input."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()

    normalized = str(value).strip()
    return normalized or None


def _load_yaml(path: Path) -> Any:
    """Load YAML with PyYAML when installed, else use the local subset parser."""
    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _load_simple_yaml(text)

    return yaml.safe_load(text)


def _dump_yaml(path: Path, data: Mapping[str, Any]) -> None:
    """Write YAML with PyYAML when installed, else use the local subset writer."""
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        path.write_text(_dump_simple_yaml(data), encoding="utf-8")
        return

    path.write_text(
        yaml.safe_dump(
            dict(data),
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )


def _load_simple_yaml(text: str) -> Any:
    """Parse the small YAML subset emitted by _dump_simple_yaml."""
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)

    lines = _meaningful_yaml_lines(text)
    if not lines:
        return None

    if lines[0][1] == "profiles:":
        return {"profiles": _load_simple_profile_list(lines[1:])}

    return _load_simple_domain_mapping(lines)


def _meaningful_yaml_lines(text: str) -> List[tuple[int, str]]:
    """Return non-empty, non-comment YAML lines with their indentation."""
    lines: List[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, stripped))
    return lines


def _load_simple_profile_list(lines: List[tuple[int, str]]) -> List[dict[str, Any]]:
    """Parse a list of profile dictionaries from simple YAML lines."""
    profiles: List[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    active_list_key: Optional[str] = None

    for indent, stripped in lines:
        if indent == 2 and stripped.startswith("- "):
            if current is not None:
                profiles.append(current)
            current = {}
            active_list_key = None
            rest = stripped[2:].strip()
            if rest:
                key, value = _split_key_value(rest)
                current[key] = _parse_scalar(value)
            continue

        if current is None:
            raise ValueError("profile list entries must start with '-'")

        if indent == 4:
            key, value = _split_key_value(stripped)
            if value == "":
                current[key] = []
                active_list_key = key
            else:
                current[key] = _parse_scalar(value)
                active_list_key = None
            continue

        if indent == 6 and stripped.startswith("- ") and active_list_key:
            current[active_list_key].append(_parse_scalar(stripped[2:].strip()))
            continue

        raise ValueError(f"unsupported YAML profile line: {stripped}")

    if current is not None:
        profiles.append(current)

    return profiles


def _load_simple_domain_mapping(
    lines: List[tuple[int, str]],
) -> dict[str, dict[str, Any]]:
    """Parse a simple domain-keyed mapping of profile values."""
    profiles: dict[str, dict[str, Any]] = {}
    current_domain: Optional[str] = None
    active_list_key: Optional[str] = None

    for indent, stripped in lines:
        if indent == 0 and stripped.endswith(":"):
            current_domain = stripped[:-1].strip()
            profiles[current_domain] = {}
            active_list_key = None
            continue

        if current_domain is None:
            raise ValueError("domain-keyed profile YAML must start with a domain")

        if indent == 2:
            key, value = _split_key_value(stripped)
            if value == "":
                profiles[current_domain][key] = []
                active_list_key = key
            else:
                profiles[current_domain][key] = _parse_scalar(value)
                active_list_key = None
            continue

        if indent == 4 and stripped.startswith("- ") and active_list_key:
            profiles[current_domain][active_list_key].append(
                _parse_scalar(stripped[2:].strip()),
            )
            continue

        raise ValueError(f"unsupported YAML mapping line: {stripped}")

    return profiles


def _split_key_value(line: str) -> tuple[str, str]:
    """Split a simple 'key: value' YAML line."""
    if ":" not in line:
        raise ValueError(f"expected key-value YAML line: {line}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> Any:
    """Parse scalar values used by the simple YAML subset."""
    if value == "":
        return ""

    lowered = value.lower()
    if lowered in {"null", "~", "none"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value[0:1] == '"':
        return json.loads(value)
    if value[0:1] == "'":
        return value.strip("'")

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _dump_simple_yaml(data: Mapping[str, Any]) -> str:
    """Emit deterministic YAML for the profile document shape."""
    profiles = data.get("profiles", [])
    lines = ["profiles:"]

    for profile in profiles:
        mapping = _ensure_mapping(profile)
        lines.append(f"  - domain: {_format_scalar(mapping.get('domain'))}")
        for key in (
            "default_fetch_mode",
            "max_rps",
            "js_required_patterns",
            "api_patterns",
            "render_policy",
            "last_verified",
        ):
            value = mapping.get(key)
            if isinstance(value, list):
                lines.append(f"    {key}:")
                for item in value:
                    lines.append(f"      - {_format_scalar(item)}")
            else:
                lines.append(f"    {key}: {_format_scalar(value)}")

    return "\n".join(lines) + "\n"


def _format_scalar(value: Any) -> str:
    """Format simple YAML scalar values, quoting strings when needed."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value)
    if not text or any(char in text for char in ":#[]{}'\"") or text != text.strip():
        return json.dumps(text)
    return text
