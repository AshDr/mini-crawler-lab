from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from .crawl_event import CrawlEvent


class EventLogger:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def log(self, event: CrawlEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            json.dump(event.to_dict(), file, ensure_ascii=False)
            file.write("\n")

    @staticmethod
    def summarize(log_file: Union[str, Path]) -> Dict[str, Any]:
        total = 0
        successful = 0
        status_403 = 0
        status_429 = 0
        timeout = 0
        elapsed_total = 0.0
        elapsed_count = 0

        path = Path(log_file)
        if not path.exists():
            return _summary(
                total=0,
                successful=0,
                status_403=0,
                status_429=0,
                timeout=0,
                average_elapsed_ms=0.0,
            )

        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                event = json.loads(line)
                total += 1

                status_code = event.get("status_code")
                error_type = event.get("error_type")
                if error_type is None and isinstance(status_code, int) and 200 <= status_code < 400:
                    successful += 1
                if status_code == 403:
                    status_403 += 1
                if status_code == 429:
                    status_429 += 1
                if error_type == "timeout":
                    timeout += 1

                elapsed_ms = event.get("elapsed_ms")
                if isinstance(elapsed_ms, (int, float)):
                    elapsed_total += float(elapsed_ms)
                    elapsed_count += 1

        average_elapsed_ms = elapsed_total / elapsed_count if elapsed_count else 0.0
        return _summary(
            total=total,
            successful=successful,
            status_403=status_403,
            status_429=status_429,
            timeout=timeout,
            average_elapsed_ms=average_elapsed_ms,
        )


def summarize(log_file: Union[str, Path]) -> Dict[str, Any]:
    return EventLogger.summarize(log_file)


def _summary(
    total: int,
    successful: int,
    status_403: int,
    status_429: int,
    timeout: int,
    average_elapsed_ms: float,
) -> Dict[str, Any]:
    success_rate = successful / total if total else 0.0
    return {
        "total": total,
        "successful": successful,
        "success_rate": success_rate,
        "403": status_403,
        "429": status_429,
        "timeout": timeout,
        "average_elapsed_ms": average_elapsed_ms,
    }
