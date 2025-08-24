import json
from functools import lru_cache
from pathlib import Path

# Кандидаты путей: рядом с этим файлом, плюс на случай запуска из пакета
CANDIDATE_NAMES = [
    "questions.ru.json",
    "questions.json",
    "quiz_questions.ru.json",
    "quiz_questions.json",
]

def _candidate_paths():
    here = Path(__file__).resolve().parent
    data_dir = here / "data"
    for name in CANDIDATE_NAMES:
        yield data_dir / name

@lru_cache
def load_questions(locale: str = "ru") -> list[dict]:
    # простая файловая загрузка
    for p in _candidate_paths():
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))

    # как дополнительный fallback — через importlib.resources
    try:
        from importlib.resources import files
        base = files("games").joinpath("data")
        for name in CANDIDATE_NAMES:
            fp = base.joinpath(name)
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
    except Exception:
        pass

    return []
