from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Dict, List, Mapping, Optional, Union
from urllib.parse import quote, urlparse, urlunparse

import httpx


class RobotsTxtError(Exception):
    """Base error for robots.txt fetch and parsing failures."""


class RobotsTxtNotFoundError(RobotsTxtError):
    """Raised when a domain does not publish a robots.txt file."""


class RobotsTxtFetchError(RobotsTxtError):
    """Raised when robots.txt cannot be fetched successfully."""


@dataclass(frozen=True)
class RobotsRule:
    directive: str
    path: str

    def to_dict(self) -> Dict[str, str]:
        return {"directive": self.directive, "path": self.path}


@dataclass(frozen=True)
class RobotsGroup:
    user_agents: List[str]
    rules: List[RobotsRule]

    def to_dict(self) -> Dict[str, object]:
        return {
            "user_agents": list(self.user_agents),
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True)
class RobotsTxt:
    domain: str
    url: str
    groups: List[RobotsGroup]
    sitemaps: List[str]
    raw_text: str
    fetched_at_ms: float

    def can_fetch(self, user_agent: str, url_or_path: str) -> bool:
        path = self._request_path(url_or_path)
        rules = self._rules_for_user_agent(user_agent)
        if not rules:
            return True

        normalized_path = self._normalized_path(path)
        matches = [rule for rule in rules if self._rule_matches(rule, normalized_path)]
        if not matches:
            return True

        best = max(matches, key=lambda rule: (len(rule.path), rule.directive == "allow"))
        return best.directive == "allow"

    def to_dict(self, include_raw_text: bool = False) -> Dict[str, object]:
        data: Dict[str, object] = {
            "domain": self.domain,
            "url": self.url,
            "groups": [group.to_dict() for group in self.groups],
            "sitemaps": list(self.sitemaps),
            "fetched_at_ms": self.fetched_at_ms,
        }
        if include_raw_text:
            data["raw_text"] = self.raw_text
        return data

    def summary(self) -> str:
        lines = [
            f"domain: {self.domain}",
            f"url: {self.url}",
            f"groups: {len(self.groups)}",
            f"sitemaps: {len(self.sitemaps)}",
        ]
        for index, group in enumerate(self.groups, start=1):
            user_agents = ", ".join(group.user_agents)
            lines.append(f"group {index}: user-agents={user_agents}; rules={len(group.rules)}")
        return "\n".join(lines)

    def _rules_for_user_agent(self, user_agent: str) -> List[RobotsRule]:
        normalized = user_agent.lower()
        matching_groups = [
            group
            for group in self.groups
            if any(self._user_agent_matches(normalized, agent) for agent in group.user_agents)
        ]
        if not matching_groups:
            return []

        best_length = max(
            len(agent)
            for group in matching_groups
            for agent in group.user_agents
            if self._user_agent_matches(normalized, agent)
        )
        return [
            rule
            for group in matching_groups
            if any(
                self._user_agent_matches(normalized, agent) and len(agent) == best_length
                for agent in group.user_agents
            )
            for rule in group.rules
        ]

    @staticmethod
    def _user_agent_matches(user_agent: str, agent: str) -> bool:
        normalized_agent = agent.lower()
        return normalized_agent == "*" or normalized_agent in user_agent

    @staticmethod
    def _request_path(url_or_path: str) -> str:
        parsed = urlparse(url_or_path)
        if parsed.scheme or parsed.netloc:
            path = parsed.path or "/"
            return f"{path}?{parsed.query}" if parsed.query else path
        return url_or_path or "/"

    @staticmethod
    def _normalized_path(path: str) -> str:
        return quote(path, safe="/:%?=&;,+~*$")

    @staticmethod
    def _rule_matches(rule: RobotsRule, path: str) -> bool:
        if rule.directive == "disallow" and rule.path == "":
            return False

        pattern = re.escape(rule.path)
        is_end_anchored = pattern.endswith(r"\$")
        if is_end_anchored:
            pattern = pattern[:-2]
        pattern = pattern.replace(r"\*", ".*")
        suffix = "$" if is_end_anchored else ""
        return re.match(f"^{pattern}{suffix}", path) is not None


class RobotTxtChecker:
    def __init__(
        self,
        timeout: float = 10.0,
        headers: Optional[Mapping[str, str]] = None,
        follow_redirects: bool = True,
        transport: Optional[httpx.BaseTransport] = None,
        storage_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.follow_redirects = follow_redirects
        self.transport = transport
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None

    def fetch(self, domain: str, store: bool = False) -> RobotsTxt:
        robots_url = self.robots_url(domain)
        started_at = perf_counter()

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=self.follow_redirects,
                transport=self.transport,
            ) as client:
                response = client.get(robots_url)
        except Exception as exc:
            raise RobotsTxtFetchError(f"failed to fetch {robots_url}: {exc}") from exc

        if response.status_code == 404:
            raise RobotsTxtNotFoundError(f"robots.txt not found for {domain}")
        if response.status_code >= 400:
            raise RobotsTxtFetchError(
                f"robots.txt fetch failed for {domain}: HTTP {response.status_code}"
            )

        result = self.parse(
            response.text,
            domain=self._domain_key(domain),
            url=str(response.url),
            fetched_at_ms=(perf_counter() - started_at) * 1000,
        )

        if store:
            self.store(result)

        return result

    def parse(
        self,
        text: str,
        domain: str,
        url: Optional[str] = None,
        fetched_at_ms: float = 0.0,
    ) -> RobotsTxt:
        groups: List[RobotsGroup] = []
        sitemaps: List[str] = []
        current_agents: List[str] = []
        current_rules: List[RobotsRule] = []
        has_rule = False

        for raw_line in text.splitlines():
            line = self._strip_comment(raw_line).strip()
            if not line or ":" not in line:
                continue

            field, value = line.split(":", 1)
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                if current_agents and has_rule:
                    groups.append(RobotsGroup(current_agents, current_rules))
                    current_agents = []
                    current_rules = []
                    has_rule = False
                current_agents.append(value)
                continue

            if field in {"allow", "disallow"} and current_agents:
                current_rules.append(RobotsRule(field, self._normalize_rule_path(value)))
                has_rule = True
                continue

            if field == "sitemap" and value:
                sitemaps.append(value)

        if current_agents:
            groups.append(RobotsGroup(current_agents, current_rules))

        robots_url = url or self.robots_url(domain)
        return RobotsTxt(
            domain=self._domain_key(domain),
            url=robots_url,
            groups=groups,
            sitemaps=sitemaps,
            raw_text=text,
            fetched_at_ms=fetched_at_ms,
        )

    def store(self, robots_txt: RobotsTxt, path: Optional[Union[str, Path]] = None) -> Path:
        target = Path(path) if path is not None else self._default_storage_path(robots_txt.domain)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(robots_txt.to_dict(include_raw_text=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target

    @classmethod
    def robots_url(cls, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or parsed.path
        return urlunparse((scheme, netloc, "/robots.txt", "", "", ""))

    @classmethod
    def _domain_key(cls, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        return (parsed.netloc or parsed.path).lower()

    @staticmethod
    def _strip_comment(line: str) -> str:
        return line.split("#", 1)[0]

    @staticmethod
    def _normalize_rule_path(path: str) -> str:
        if path == "":
            return ""
        return quote(path, safe="/:%?=&;,+~*$")

    def _default_storage_path(self, domain: str) -> Path:
        if self.storage_dir is None:
            raise RobotsTxtError("storage_dir is required when store=True and no path is given")
        safe_domain = domain.replace(":", "_").replace("/", "_")
        return self.storage_dir / f"{safe_domain}_robots.json"


RobotTxTChecker = RobotTxtChecker
