# games/questions.py
import json
from functools import lru_cache
from pathlib import Path

CANDIDATE_NAMES = [
    "questions.ru.json", "questions.json",
    "quiz_questions.ru.json", "quiz_questions.json",
]

def _candidate_paths():
    here = Path(__file__).resolve().parent / "data"
    for name in CANDIDATE_NAMES:
        yield here / name

@lru_cache
def load_questions(locale: str = "ru") -> list[dict]:
    for p in _candidate_paths():
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
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

def _with_defaults(q: dict) -> dict:
    q = dict(q)
    r = q.get("reward") or {}
    q["reward"] = {"money": int(r.get("money", 0)), "influence": int(r.get("influence", 0))}
    return q

def get_question_by_id(qid: int) -> dict | None:
    for q in load_questions():
        if int(q.get("id", 0)) == int(qid):
            return _with_defaults(q)
    return None
