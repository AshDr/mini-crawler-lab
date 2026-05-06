from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Union


class JsonlItemWriter:
    """Append extracted crawler items to a UTF-8 JSON Lines file."""

    def __init__(self, path: Union[str, Path] = "data/items.jsonl") -> None:
        """Create a writer for the given JSON Lines path."""
        self.path = Path(path)

    def append(self, item: Mapping[str, Any]) -> None:
        """Append one item mapping as a JSON line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            json.dump(item, file, ensure_ascii=False)
            file.write("\n")
