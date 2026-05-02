import json

from mini_crawler_lab import JsonlItemWriter


def test_append_writes_utf8_json_lines(tmp_path) -> None:
    path = tmp_path / "data" / "items.jsonl"
    writer = JsonlItemWriter(path)

    writer.append({"title": "你好", "url": "https://example.com/一"})
    writer.append({"title": "second", "count": 2})

    content = path.read_text(encoding="utf-8")

    assert content == (
        '{"title": "你好", "url": "https://example.com/一"}\n'
        '{"title": "second", "count": 2}\n'
    )
    assert [json.loads(line) for line in content.splitlines()] == [
        {"title": "你好", "url": "https://example.com/一"},
        {"title": "second", "count": 2},
    ]
