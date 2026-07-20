from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

WORDS_AGE4 = [
    ("cat", "A soft pet that says meow."),
    ("sun", "The bright light in the sky."),
    ("ball", "A round toy you can throw."),
    ("milk", "A white drink from cows."),
    ("book", "Pages with stories and pictures."),
    ("fish", "An animal that swims in water."),
    ("tree", "It has leaves and grows tall."),
    ("happy", "How you feel when you smile."),
]

WORDS_AGE7 = [
    ("brave", "Doing something even if you feel a little scared."),
    ("whisper", "To speak very quietly."),
    ("garden", "A place where flowers and veggies grow."),
    ("journey", "A long trip from one place to another."),
    ("curious", "Wanting to learn or explore."),
    ("friendship", "Being kind friends with someone."),
    ("carefully", "Doing something with care and attention."),
    ("adventure", "An exciting new experience."),
]

REPEAT_AGE4 = [
    "The cat is soft.",
    "I see a red ball.",
    "The sun is bright.",
    "Please and thank you.",
]

REPEAT_AGE7 = [
    "Curiosity helps us learn new words.",
    "I can spell friendship carefully.",
    "Whisper when the baby is sleeping.",
    "Every adventure starts with one small step.",
]

ISPY_COLORS = ["red", "blue", "green", "yellow", "orange", "purple", "pink", "white", "black"]


@dataclass
class GameSession:
    kind: str
    prompt: str
    answer: str
    hint: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "prompt": self.prompt,
            "hint": self.hint,
            "meta": self.meta,
            # answer intentionally omitted from client payloads
        }


def _word_bank(age: int) -> list[tuple[str, str]]:
    return WORDS_AGE4 if age <= 5 else WORDS_AGE7


def start_game(kind: str, age: int = 7) -> GameSession:
    kind = kind.strip().lower()
    if kind in ("word", "word_of_the_day"):
        word, meaning = random.choice(_word_bank(age))
        return GameSession(
            kind="word_of_the_day",
            prompt=f"Word of the day: {word}. It means: {meaning}. Can you say {word}?",
            answer=word.lower(),
            hint=f"It starts with {word[0].upper()}.",
            meta={"word": word, "meaning": meaning},
        )
    if kind in ("repeat", "repeat_after_me"):
        phrase = random.choice(REPEAT_AGE4 if age <= 5 else REPEAT_AGE7)
        return GameSession(
            kind="repeat_after_me",
            prompt=f"Repeat after me: {phrase}",
            answer=phrase.lower().rstrip("."),
            hint="Say it slowly, one word at a time.",
            meta={"phrase": phrase},
        )
    if kind in ("spell", "spelling"):
        word, meaning = random.choice(_word_bank(age))
        return GameSession(
            kind="spell",
            prompt=f"Spell the word for: {meaning}. The word has {len(word)} letters.",
            answer=word.lower(),
            hint=f"It starts with {word[0].upper()} and ends with {word[-1].upper()}.",
            meta={"word": word, "meaning": meaning},
        )
    if kind in ("phonics", "sounds"):
        word, _meaning = random.choice(WORDS_AGE4)
        letter = word[0]
        return GameSession(
            kind="phonics",
            prompt=f"What sound does the letter {letter.upper()} make at the start of {word}?",
            answer=letter.lower(),
            hint=f"Think of the first sound in {word}.",
            meta={"word": word, "letter": letter},
        )
    if kind in ("ispy", "i_spy"):
        color = random.choice(ISPY_COLORS)
        return GameSession(
            kind="i_spy",
            prompt=f"I spy with my little eye something {color}. What {color} thing do you see? "
            f"Say any {color} thing!",
            answer=color.lower(),
            hint=f"Look around for something that is {color}.",
            meta={"color": color},
        )
    raise ValueError(f"Unknown game: {kind}")


def score_answer(session: GameSession, user_text: str) -> dict[str, Any]:
    text = " ".join(user_text.lower().strip().split())
    answer = session.answer.lower()
    ok = False
    praise = "Nice try!"

    if session.kind == "word_of_the_day":
        ok = answer in text.replace(".", " ").split() or answer in text
        praise = f"Yes! {session.meta.get('word')} — great speaking!" if ok else f"Almost! Say: {session.meta.get('word')}."
    elif session.kind == "repeat_after_me":
        # loose: ignore punctuation and allow close match
        target = answer
        ok = target in text or text in target or _token_overlap(target, text) >= 0.6
        praise = "Perfect repeat!" if ok else f"Try again: {session.meta.get('phrase')}"
    elif session.kind == "spell":
        compact = text.replace(" ", "").replace("-", "")
        ok = compact == answer or text == " ".join(answer)
        praise = f"Spelled {answer} correctly!" if ok else f"Not quite. It is spelled {answer}."
    elif session.kind == "phonics":
        ok = answer in text or text.startswith(answer)
        praise = f"Yes — {answer.upper()}!" if ok else f"Listen for the first sound: {answer}."
    elif session.kind == "i_spy":
        ok = answer in text  # they mentioned the color
        praise = f"I love that {answer} idea!" if ok else f"Can you find something {answer}?"

    return {"ok": ok, "message": praise, "kind": session.kind}


def _token_overlap(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


GAME_KINDS = [
    {"id": "word_of_the_day", "label": "Word", "min_age": 4},
    {"id": "repeat_after_me", "label": "Repeat", "min_age": 4},
    {"id": "phonics", "label": "Sounds", "min_age": 4, "max_age": 6},
    {"id": "spell", "label": "Spell", "min_age": 6},
    {"id": "i_spy", "label": "I spy", "min_age": 4},
]


def games_for_age(age: int) -> list[dict[str, Any]]:
    out = []
    for g in GAME_KINDS:
        if age < int(g.get("min_age", 0)):
            continue
        if "max_age" in g and age > int(g["max_age"]):
            continue
        out.append({"id": g["id"], "label": g["label"]})
    return out
