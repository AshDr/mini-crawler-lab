from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser as BaseHTMLParser
from typing import List
from urllib.parse import urljoin


@dataclass(frozen=True)
class ParsedPage:
    title: str
    links: List[str]
    text_length: int


class HTMLParser:
    def parse(self, html: str, base_url: str) -> ParsedPage:
        parser = _PageHTMLParser(base_url)
        parser.feed(html)
        parser.close()

        return ParsedPage(
            title=parser.title.strip(),
            links=parser.links,
            text_length=len(" ".join(parser.text_parts).strip()),
        )


class _PageHTMLParser(BaseHTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.links: List[str] = []
        self.text_parts: List[str] = []
        self._tag_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        self._tag_stack.append(normalized_tag)

        if normalized_tag != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self.links.append(urljoin(self.base_url, href))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == normalized_tag:
                del self._tag_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return

        if self._current_tag_is("title"):
            if not self.title:
                self.title = data
            return

        if self._current_tag_is("script") or self._current_tag_is("style"):
            return

        if self._tag_stack and not self._current_tag_is("body"):
            return

        self.text_parts.append(data.strip())

    def _current_tag_is(self, tag: str) -> bool:
        return tag in self._tag_stack
