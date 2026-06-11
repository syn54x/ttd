"""Tokenizer for natural-language time specs.

Turns strings like "yesterday 9-11:30" or "monday 1pm for 3 hours" into a
flat token list the grammar consumes. Unknown words are a ParseError here,
so the user finds typos at the right layer.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from ttd.core.errors import ParseError


class TokenKind(Enum):
    TIME = auto()  # 8, 8:30, 5pm, noon, midnight
    DURATION = auto()  # 2h, 90m, 1h30m, "3 hours"
    DATE = auto()  # 2026-06-09, 6/3, 6/3/2026
    DATE_KEYWORD = auto()  # today, yesterday
    WEEKDAY = auto()  # monday..sunday
    PART_OF_DAY = auto()  # morning, afternoon, evening, tonight
    TO = auto()  # to, until, till, thru, through, -
    FROM = auto()
    AT = auto()
    FOR = auto()
    ON = auto()
    LAST = auto()
    THIS = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    # TIME: (hour, minute, meridiem: 'am'|'pm'|None)
    # DURATION: seconds
    # DATE: (year|None, month, day)
    # WEEKDAY: 0=monday..6=sunday
    # PART_OF_DAY: 'morning'|'afternoon'|'evening'|'night'
    value: Any = None


WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}  # fmt: skip

PARTS_OF_DAY = {
    "morning": "morning",
    "afternoon": "afternoon",
    "evening": "evening",
    "night": "night",
    "tonight": "night",
}

KEYWORDS = {
    "today": (TokenKind.DATE_KEYWORD, "today"),
    "yesterday": (TokenKind.DATE_KEYWORD, "yesterday"),
    "to": (TokenKind.TO, None),
    "until": (TokenKind.TO, None),
    "till": (TokenKind.TO, None),
    "thru": (TokenKind.TO, None),
    "through": (TokenKind.TO, None),
    "from": (TokenKind.FROM, None),
    "at": (TokenKind.AT, None),
    "for": (TokenKind.FOR, None),
    "on": (TokenKind.ON, None),
    "last": (TokenKind.LAST, None),
    "this": (TokenKind.THIS, None),
    "noon": (TokenKind.TIME, (12, 0, "pm")),
    "midnight": (TokenKind.TIME, (0, 0, "am")),
}

_HOURS = r"h|hrs?|hours?"
_MINUTES = r"m|mins?|minutes?"

# Order matters: first match at the current position wins.
_PATTERNS: list[tuple[TokenKind, re.Pattern[str]]] = [
    (TokenKind.DATE, re.compile(r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b")),
    (TokenKind.DATE, re.compile(r"(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{2,4}))?\b")),
    # 1h30m / 1h 30m / 1 hour 30 minutes (minutes part optional)
    (
        TokenKind.DURATION,
        re.compile(rf"(?P<h>\d+(?:\.\d+)?)\s*(?:{_HOURS})(?:\s*(?P<min>\d+)\s*(?:{_MINUTES}))?\b"),
    ),
    (TokenKind.DURATION, re.compile(rf"(?P<min>\d+)\s*(?:{_MINUTES})\b")),
    (
        TokenKind.TIME,
        re.compile(r"(?P<h>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<mer>am|pm|a\.m\.|p\.m\.)?\b"),
    ),
    (TokenKind.TO, re.compile(r"-|–|—")),
]

_WORD = re.compile(r"[a-zA-Z.]+")
_WS = re.compile(r"[\s,]+")


def _numeric_token(kind: TokenKind, match: re.Match[str]) -> Token:
    text = match.group(0)
    if kind == TokenKind.DATE:
        year = int(y) if (y := match.groupdict().get("y")) else None
        if year is not None and year < 100:
            year += 2000
        return Token(kind, text, (year, int(match["m"]), int(match["d"])))
    if kind == TokenKind.DURATION:
        groups = match.groupdict()
        hours = float(groups.get("h") or 0)
        minutes = int(groups.get("min") or 0)
        seconds = round(hours * 3600) + minutes * 60
        if seconds <= 0:
            raise ParseError(f"Duration '{text}' is zero")
        return Token(kind, text, seconds)
    if kind == TokenKind.TIME:
        hour_text = match["h"]
        hour = int(hour_text)
        minute = int(match["min"] or 0)
        meridiem = match["mer"].replace(".", "")[:2] if match["mer"] else None
        if meridiem is None and len(hour_text) == 2 and hour_text[0] == "0":
            meridiem = "24"  # leading zero ("08:30") reads as exact 24-hour time
        if meridiem in ("am", "pm") and not 1 <= hour <= 12:
            raise ParseError(f"'{text}': hour must be 1-12 with am/pm")
        if hour > 23 or minute > 59:
            raise ParseError(f"'{text}' is not a valid time")
        return Token(kind, text, (hour, minute, meridiem))
    return Token(kind, text)


def tokenize(spec: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    text = spec.strip().lower()
    while pos < len(text):
        if ws := _WS.match(text, pos):
            pos = ws.end()
            continue
        for kind, pattern in _PATTERNS:
            if (m := pattern.match(text, pos)) and m.end() > pos:
                tokens.append(_numeric_token(kind, m))
                pos = m.end()
                break
        else:
            if word := _WORD.match(text, pos):
                w = word.group(0).rstrip(".")
                if w in KEYWORDS:
                    kind, value = KEYWORDS[w]
                    tokens.append(Token(kind, w, value))
                elif w in WEEKDAYS:
                    tokens.append(Token(TokenKind.WEEKDAY, w, WEEKDAYS[w]))
                elif w in PARTS_OF_DAY:
                    tokens.append(Token(TokenKind.PART_OF_DAY, w, PARTS_OF_DAY[w]))
                else:
                    raise ParseError(f"Don't understand '{w}' in {spec!r}")
                pos = word.end()
            else:
                raise ParseError(f"Unexpected character '{text[pos]}' in {spec!r}")
    if not tokens:
        raise ParseError("Empty time spec")
    return tokens
