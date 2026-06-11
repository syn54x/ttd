"""Grammar over the token stream.

spec      := parts...  (date anchors and one time body, in any order)
date_part := DATE_KEYWORD | [LAST] WEEKDAY | DATE | [THIS] PART_OF_DAY | ON date_part
body      := [FROM] TIME TO TIME
           | [AT] TIME FOR DURATION
           | DURATION [AT TIME]
           | [AT] TIME            (point — valid for --at, not for log)
"""

from dataclasses import dataclass, field

from ttd.core.errors import ParseError
from ttd.parsing.tokens import Token, TokenKind, tokenize

ClockTime = tuple[int, int, str | None]  # hour, minute, meridiem


@dataclass
class ParsedSpan:
    raw: str = ""
    date: tuple[int | None, int, int] | None = None  # (year?, month, day)
    date_keyword: str | None = None  # today | yesterday
    weekday: int | None = None  # 0=monday..6
    last_weekday: bool = False
    part_of_day: str | None = None  # morning|afternoon|evening|night
    start: ClockTime | None = None
    end: ClockTime | None = None
    duration: int | None = None  # seconds
    _date_set: bool = field(default=False, repr=False)

    @property
    def has_body(self) -> bool:
        return self.start is not None or self.duration is not None


class _Parser:
    def __init__(self, tokens: list[Token], raw: str) -> None:
        self.tokens = tokens
        self.raw = raw
        self.i = 0

    def peek(self, offset: int = 0) -> Token | None:
        idx = self.i + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def take(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, kind: TokenKind, what: str) -> Token:
        tok = self.peek()
        if tok is None or tok.kind != kind:
            got = f"'{tok.text}'" if tok else "end of input"
            raise ParseError(f"Expected {what} but found {got} in {self.raw!r}")
        return self.take()

    def parse(self) -> ParsedSpan:
        span = ParsedSpan(raw=self.raw)
        while self.peek() is not None:
            tok = self.peek()
            assert tok is not None
            match tok.kind:
                case TokenKind.DATE_KEYWORD | TokenKind.DATE | TokenKind.WEEKDAY:
                    self._date_part(span)
                case TokenKind.LAST | TokenKind.THIS | TokenKind.ON:
                    self._date_part(span)
                case TokenKind.PART_OF_DAY:
                    self._part_of_day(span)
                case TokenKind.FROM | TokenKind.TIME | TokenKind.AT:
                    self._time_body(span)
                case TokenKind.DURATION | TokenKind.FOR:
                    self._duration_body(span)
                case _:
                    raise ParseError(f"Unexpected '{tok.text}' in {self.raw!r}")
        return span

    def _set_date(self, span: ParsedSpan) -> None:
        if span._date_set:
            raise ParseError(f"More than one date in {self.raw!r}")
        span._date_set = True

    def _date_part(self, span: ParsedSpan) -> None:
        tok = self.take()
        if tok.kind == TokenKind.ON:
            nxt = self.peek()
            if nxt is None or nxt.kind not in (
                TokenKind.DATE,
                TokenKind.DATE_KEYWORD,
                TokenKind.WEEKDAY,
                TokenKind.LAST,
            ):
                raise ParseError(f"Expected a date after 'on' in {self.raw!r}")
            self._date_part(span)
            return
        if tok.kind == TokenKind.THIS:
            part = self.expect(TokenKind.PART_OF_DAY, "'morning'/'afternoon'/'evening'")
            self.i -= 1  # let _part_of_day consume it
            self._part_of_day(span)
            del part
            return
        if tok.kind == TokenKind.LAST:
            day = self.expect(TokenKind.WEEKDAY, "a weekday after 'last'")
            self._set_date(span)
            span.weekday = day.value
            span.last_weekday = True
            return
        self._set_date(span)
        match tok.kind:
            case TokenKind.DATE_KEYWORD:
                span.date_keyword = tok.value
            case TokenKind.DATE:
                span.date = tok.value
            case TokenKind.WEEKDAY:
                span.weekday = tok.value

    def _part_of_day(self, span: ParsedSpan) -> None:
        tok = self.expect(TokenKind.PART_OF_DAY, "a part of day")
        if span.part_of_day is not None:
            raise ParseError(f"More than one part-of-day in {self.raw!r}")
        span.part_of_day = tok.value

    def _require_no_body(self, span: ParsedSpan) -> None:
        if span.has_body:
            raise ParseError(f"More than one time range in {self.raw!r}")

    def _time_body(self, span: ParsedSpan) -> None:
        self._require_no_body(span)
        if (tok := self.peek()) is not None and tok.kind == TokenKind.FROM:
            self.take()
        if (tok := self.peek()) is not None and tok.kind == TokenKind.AT:
            self.take()
        start = self.expect(TokenKind.TIME, "a time")
        span.start = start.value
        nxt = self.peek()
        if nxt is not None and nxt.kind == TokenKind.TO:
            self.take()
            end = self.expect(TokenKind.TIME, "an end time")
            span.end = end.value
        elif nxt is not None and nxt.kind == TokenKind.FOR:
            self.take()
            dur = self.expect(TokenKind.DURATION, "a duration after 'for'")
            span.duration = dur.value
        # else: bare point; resolver decides whether that's allowed

    def _duration_body(self, span: ParsedSpan) -> None:
        self._require_no_body(span)
        if (tok := self.peek()) is not None and tok.kind == TokenKind.FOR:
            self.take()
        dur = self.expect(TokenKind.DURATION, "a duration")
        span.duration = dur.value
        nxt = self.peek()
        if nxt is not None and nxt.kind == TokenKind.AT:
            self.take()
            start = self.expect(TokenKind.TIME, "a time after 'at'")
            span.start = start.value


def parse_spec(spec: str) -> ParsedSpan:
    return _Parser(tokenize(spec), spec).parse()
