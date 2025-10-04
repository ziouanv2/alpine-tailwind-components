from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import OutputSettings


class StorageWriter:
    def __init__(self, settings: OutputSettings):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._base_dir = self._determine_base_dir()
        self._csv_writer: Optional[csv.DictWriter] = None
        self._csv_file = None
        if self.settings.output_format == "csv":
            path = self._resolve_output_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._csv_file = path.open("a", encoding="utf-8", newline="")
            self._csv_writer = None  # will be initialised on first write

    def _determine_base_dir(self) -> Path:
        if self.settings.output_path and self.settings.output_path.suffix:
            base = self.settings.output_path.parent
            base.mkdir(parents=True, exist_ok=True)
            return base
        base = self.settings.output_path or Path("outputs")
        if self.settings.create_timestamp_directory:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            base = base / today
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _resolve_output_path(self) -> Path:
        if self.settings.output_path and self.settings.output_path.suffix:
            return self.settings.output_path
        filename = "results.csv"
        return self._base_dir / filename

    def _keyword_jsonl_path(self, keyword: str) -> Path:
        safe_keyword = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in keyword.strip())
        if not safe_keyword:
            safe_keyword = "keyword"
        return self._base_dir / f"{safe_keyword}.jsonl"

    async def write_record(self, keyword: str, record: Dict[str, Any]) -> None:
        async with self._lock:
            if self.settings.output_format == "jsonl":
                if self.settings.output_path and self.settings.output_path.suffix == ".jsonl":
                    path = self.settings.output_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    path = self._keyword_jsonl_path(keyword)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                if not self._csv_writer:
                    fieldnames = list(record.keys())
                    self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
                    if self._csv_file.tell() == 0:
                        self._csv_writer.writeheader()
                self._csv_writer.writerow(record)
                self._csv_file.flush()

    async def close(self) -> None:
        async with self._lock:
            if self._csv_file:
                self._csv_file.close()


__all__ = ["StorageWriter"]
