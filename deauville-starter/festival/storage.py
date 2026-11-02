from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from festival.errors import FestivalError, StorageError
from festival.models import Festival

Result = TypeVar("Result")


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Festival:
        try:
            with self.path.open(encoding="utf-8") as file:
                raw: Any = json.load(file)
            return Festival.from_dict(raw)
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise StorageError(f"Cannot read festival data: {exc}") from exc
        except FestivalError as exc:
            raise StorageError(f"Invalid festival data: {exc}") from exc

    def save(self, festival: Festival) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(festival.to_dict(), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise StorageError(f"Cannot write festival data: {exc}") from exc


class FestivalRepository:
    def __init__(self, storage: JsonStorage, festival: Festival) -> None:
        self.storage = storage
        self.festival = festival

    @classmethod
    def open(cls, path: Path) -> FestivalRepository:
        storage = JsonStorage(path)
        return cls(storage, storage.load())

    def change(self, action: Callable[[Festival], Result]) -> Result:
        candidate = Festival.from_dict(self.festival.to_dict())
        result = action(candidate)
        candidate.validate()
        self.storage.save(candidate)
        self.festival = candidate
        return result
