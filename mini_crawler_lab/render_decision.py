from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Literal, Optional


RenderDecisionName = Literal[
    "http_ok",
    "need_render",
    "parse_embedded_json",
    "uncertain",
]


@dataclass(frozen=True)
class RenderDecision:
    """Decision and page signals used to choose the crawler's next step."""

    decision: RenderDecisionName
    is_app_shell: bool
    has_next_data: bool
    has_initial_state: bool
    text_length: int
    link_count: int
    rendered_text_length: Optional[int] = None
    rendered_link_count: Optional[int] = None
    reasons: List[str] = field(default_factory=list)


class RenderDecisionEngine:
    """Classify static HTML and decide whether browser rendering is useful."""

    _INITIAL_STATE_PATTERN = re.compile(
        r"\bwindow\s*\.\s*__INITIAL_STATE__\b",
        re.IGNORECASE,
    )
    _NEXT_DATA_PATTERN = re.compile(r"\b__NEXT_DATA__\b", re.IGNORECASE)
    _APP_ROOT_IDS = {
        "app",
        "root",
        "__next",
        "__nuxt",
        "svelte",
        "gatsby-focus-wrapper",
    }
    _SCRIPTY_EXTENSIONS = (".js", ".mjs")
    _LOW_TEXT_LIMIT = 120
    _SPARSE_TEXT_LIMIT = 40
    _RICH_TEXT_LIMIT = 200

    def decide(
        self,
        static_html: str,
        rendered_html: Optional[str] = None,
    ) -> RenderDecision:
        """Return the preferred handling strategy for the given HTML."""
        static_stats = _HTMLSignalParser.parse(static_html)
        rendered_stats = (
            None if rendered_html is None else _HTMLSignalParser.parse(rendered_html)
        )

        has_next_data = self._has_next_data(static_html)
        has_initial_state = self._has_initial_state(static_html)
        is_app_shell = self._is_app_shell(static_stats)
        rendered_is_richer = self._rendered_html_is_richer(static_stats, rendered_stats)
        reasons = self._reasons(
            static_stats=static_stats,
            rendered_stats=rendered_stats,
            has_next_data=has_next_data,
            has_initial_state=has_initial_state,
            is_app_shell=is_app_shell,
            rendered_is_richer=rendered_is_richer,
        )

        return RenderDecision(
            decision=self._decision(
                static_stats=static_stats,
                rendered_stats=rendered_stats,
                has_next_data=has_next_data,
                has_initial_state=has_initial_state,
                is_app_shell=is_app_shell,
                rendered_is_richer=rendered_is_richer,
            ),
            is_app_shell=is_app_shell,
            has_next_data=has_next_data,
            has_initial_state=has_initial_state,
            text_length=static_stats.text_length,
            link_count=static_stats.link_count,
            rendered_text_length=(
                None if rendered_stats is None else rendered_stats.text_length
            ),
            rendered_link_count=(
                None if rendered_stats is None else rendered_stats.link_count
            ),
            reasons=reasons,
        )

    def _decision(
        self,
        static_stats: "_HTMLSignals",
        rendered_stats: Optional["_HTMLSignals"],
        has_next_data: bool,
        has_initial_state: bool,
        is_app_shell: bool,
        rendered_is_richer: bool,
    ) -> RenderDecisionName:
        """Map extracted signals to a stable crawler decision."""
        if has_next_data or has_initial_state:
            return "parse_embedded_json"
        if is_app_shell or rendered_is_richer:
            return "need_render"
        if self._static_html_has_enough_content(static_stats):
            return "http_ok"
        if rendered_stats is not None and self._static_html_has_enough_content(
            rendered_stats,
        ):
            return "need_render"
        return "uncertain"

    def _is_app_shell(self, stats: "_HTMLSignals") -> bool:
        """Identify sparse pages that likely depend on JavaScript hydration."""
        low_content = stats.text_length <= self._LOW_TEXT_LIMIT and stats.link_count <= 3
        has_shell_root = bool(self._APP_ROOT_IDS.intersection(stats.element_ids))
        has_bundled_scripts = stats.script_count >= 2 or stats.has_script_bundle

        if low_content and has_shell_root and has_bundled_scripts:
            return True
        if stats.text_length <= self._SPARSE_TEXT_LIMIT and stats.requires_javascript:
            return True
        if stats.text_length == 0 and has_shell_root and stats.script_count > 0:
            return True
        return False

    def _static_html_has_enough_content(self, stats: "_HTMLSignals") -> bool:
        """Treat substantial text or navigational links as useful static HTML."""
        return stats.text_length >= self._RICH_TEXT_LIMIT or stats.link_count >= 5

    def _rendered_html_is_richer(
        self,
        static_stats: "_HTMLSignals",
        rendered_stats: Optional["_HTMLSignals"],
    ) -> bool:
        """Detect when browser rendering materially adds crawlable content."""
        if rendered_stats is None:
            return False

        text_gain = rendered_stats.text_length - static_stats.text_length
        link_gain = rendered_stats.link_count - static_stats.link_count
        return text_gain >= 100 or link_gain >= 3

    def _reasons(
        self,
        static_stats: "_HTMLSignals",
        rendered_stats: Optional["_HTMLSignals"],
        has_next_data: bool,
        has_initial_state: bool,
        is_app_shell: bool,
        rendered_is_richer: bool,
    ) -> List[str]:
        """Produce compact diagnostic labels for logs and tests."""
        reasons: List[str] = []

        if has_next_data:
            reasons.append("has_next_data")
        if has_initial_state:
            reasons.append("has_initial_state")
        if is_app_shell:
            reasons.append("static_html_looks_like_app_shell")
        if rendered_is_richer:
            reasons.append("rendered_html_is_richer")
        if self._static_html_has_enough_content(static_stats):
            reasons.append("static_html_has_content")
        if rendered_stats is not None and self._static_html_has_enough_content(
            rendered_stats,
        ):
            reasons.append("rendered_html_has_content")

        return reasons

    @classmethod
    def _has_next_data(cls, html: str) -> bool:
        """Return whether the document contains Next.js embedded data."""
        return bool(cls._NEXT_DATA_PATTERN.search(html))

    @classmethod
    def _has_initial_state(cls, html: str) -> bool:
        """Return whether the document contains a window.__INITIAL_STATE__ blob."""
        return bool(cls._INITIAL_STATE_PATTERN.search(html))


@dataclass(frozen=True)
class _HTMLSignals:
    """Small set of HTML features needed by the render decision heuristic."""

    text_length: int
    link_count: int
    script_count: int
    has_script_bundle: bool
    requires_javascript: bool
    element_ids: List[str]


class _HTMLSignalParser(HTMLParser):
    """Extract text, link, script, and root element signals from HTML."""

    _IGNORED_TEXT_TAGS = {"head", "script", "style", "template", "title"}

    def __init__(self) -> None:
        """Initialize mutable parser state."""
        super().__init__(convert_charrefs=True)
        self.text_parts: List[str] = []
        self.link_count = 0
        self.script_count = 0
        self.has_script_bundle = False
        self.requires_javascript = False
        self.element_ids: List[str] = []
        self._tag_stack: List[str] = []

    @classmethod
    def parse(cls, html: str) -> _HTMLSignals:
        """Parse HTML and return signals without raising on malformed markup."""
        parser = cls()
        parser.feed(html or "")
        parser.close()
        return _HTMLSignals(
            text_length=len(" ".join(parser.text_parts).strip()),
            link_count=parser.link_count,
            script_count=parser.script_count,
            has_script_bundle=parser.has_script_bundle,
            requires_javascript=parser.requires_javascript,
            element_ids=parser.element_ids,
        )

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        """Track tags and collect app-shell related attributes."""
        normalized_tag = tag.lower()
        self._tag_stack.append(normalized_tag)
        attributes = {name.lower(): value for name, value in attrs}

        element_id = attributes.get("id")
        if element_id:
            self.element_ids.append(element_id.lower())

        if normalized_tag == "a" and attributes.get("href"):
            self.link_count += 1
        elif normalized_tag == "script":
            self.script_count += 1
            src = (attributes.get("src") or "").split("?", 1)[0].lower()
            if src.endswith(RenderDecisionEngine._SCRIPTY_EXTENSIONS):
                self.has_script_bundle = True

    def handle_endtag(self, tag: str) -> None:
        """Trim parser nesting state on closing tags."""
        normalized_tag = tag.lower()
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == normalized_tag:
                del self._tag_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        """Collect visible text and JavaScript-required fallback hints."""
        stripped = data.strip()
        if not stripped:
            return

        if self._current_tag_is("noscript") and "javascript" in stripped.lower():
            self.requires_javascript = True

        if any(self._current_tag_is(tag) for tag in self._IGNORED_TEXT_TAGS):
            return

        self.text_parts.append(stripped)

    def _current_tag_is(self, tag: str) -> bool:
        """Return whether the parser is currently inside the tag."""
        return tag in self._tag_stack
