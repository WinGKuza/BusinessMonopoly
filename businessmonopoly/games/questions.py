import json
from functools import lru_cache
from importlib.resources import files

@lru_cache
def load_questions(locale: str = "ru") -> list[dict]:
    path = files("games").joinpath("data", "questions.json")
    return json.loads(path.read_text(encoding="utf-8"))