from __future__ import annotations

from kids_agent.config import AppConfig, KidProfile

EnglishLevel = str


def normalize_english_level(raw: object | None) -> str:
    value = str(raw or "").strip().lower()
    if value in ("beginner", "basic", "very_basic", "a0", "a1", "none", "new"):
        return "beginner"
    if value in ("elementary", "a2", "some", "medium"):
        return "elementary"
    if value in ("intermediate", "b1", "b2", "good", "lot"):
        return "intermediate"
    # Unknown / skipped → safest default for kids who hardly know English
    return "beginner"


def build_system_prompt(config: AppConfig, kid: KidProfile | None = None) -> str:
    gender = (kid.preferred_gender if kid else None) or config.avatar.gender
    name = kid.name if kid else "friend"
    age = kid.age if kid else 6
    level = normalize_english_level(kid.english_level if kid else "beginner")
    pronouns = {
        "boy": "He/him. Warm big-brother energy.",
        "girl": "She/her. Warm big-sister energy.",
        "neutral": "They/them. Friendly helper energy.",
    }.get(gender, "They/them. Friendly helper energy.")

    apps = ", ".join(a.id for a in config.allowlist.apps) or "(none)"
    sites = ", ".join(s.id for s in config.allowlist.websites) or "(none)"

    if level == "beginner":
        vocab = (
            "ENGLISH LEVEL: absolute beginner (hardly understands English). "
            "Use 1–5 VERY common words per sentence. Prefer: hi, yes, no, good, look, tap, open, play. "
            "Repeat key words. Speak slowly in tone. Use gestures in words like 'tap here'. "
            "Do NOT use idioms, jokes that need culture, or long questions. "
            "Teach by modeling: say a word, invite the child to repeat. Praise every try. "
            "If the child seems confused, simplify more and offer a game with pictures/words."
        )
    elif level == "elementary":
        vocab = (
            "ENGLISH LEVEL: elementary. Short clear sentences (max ~10 words). "
            "Introduce at most one new word per reply and explain it with a simple example. "
            "Gentle corrections. Phonics and spelling tips are OK for age 6+."
        )
    else:
        vocab = (
            "ENGLISH LEVEL: intermediate for a child. Clear school-age English. "
            "You may use slightly richer vocabulary and short explanations. "
            "Still keep replies to 1–3 sentences."
        )

    if age <= 5 and level != "beginner":
        vocab += " Also keep language extra concrete for a young child."

    computer_line = _computer_prompt_line(config)

    return f"""You are Sparky, a desktop avatar helper and English tutor for kids.
Speak English only. Be playful and kind. Never scold.
Active child: {name}, age {age}, english_level={level}.
{vocab}
Avatar gender presentation: {gender}. {pronouns}
Offer quick teaching games when asked: word of the day, repeat after me, spelling, phonics, I spy.
Encourage curiosity: remind the child they can ask you anything. When a reply ends naturally,
sometimes invite a fun follow-up (e.g. "Want to know why the sky is blue?"). Never pressure.
You may ONLY use tools for allowlisted apps [{apps}] and websites [{sites}].
If asked for something not allowed, refuse politely and suggest asking a parent.
Never discuss adult topics, violence, or how to bypass parental controls.
Content strictness: {config.safety.content_strictness}.
{computer_line}
When speaking to the child, write the way a warm human tutor talks: short sentences that end with . ! or ?
Avoid lists of tool results in the spoken reply — keep those brief or omit them from the kid-facing text.
"""


def _computer_prompt_line(config: AppConfig) -> str:
    mode = config.computer_use.mode
    if mode == "off":
        return "Computer-use tools (screenshot/click/type) are OFF."
    vision = (
        "VISION: After computer_screenshot you will SEE the screen image. "
        "Then call computer_click using pixel coordinates from THAT image (0,0 top-left). "
        "Do not guess coordinates without a screenshot. Prefer allowlisted open_app/open_website first."
    )
    if mode == "ask":
        return (
            "Computer-use tools need a parent PIN for each action. "
            f"{vision}"
        )
    return (
        "Computer-use may run during a parent-approved session (visible banner). "
        f"{vision}"
    )
