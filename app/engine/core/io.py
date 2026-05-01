from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


def load_json_model(path: Path, model_type: type[ModelT]) -> ModelT:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return model_type.model_validate(payload)


def write_json_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(model.model_dump(mode="json"), handle, indent=2)
        handle.write("\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
