from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Union


class JsonlItemWriter:
    def __init__(self, path: Union[str, Path] = "data/items.jsonl") -> None:
        self.path = Path(path)

    def append(self, item: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            json.dump(item, file, ensure_ascii=False)
            file.write("\n")
