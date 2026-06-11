"""The dashboard hero: oversized clock digits that pulse while tracking."""

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Digits, Label

from ttd.core.money import format_hours
from ttd.services.timer import TimerStatus


class BigTimer(Vertical):
    DEFAULT_CSS = """
    BigTimer { height: auto; align: center middle; }
    BigTimer Digits { width: auto; color: $accent; }
    BigTimer.idle Digits { color: $secondary; }
    BigTimer.running.tick Digits { color: $accent 80%; }
    BigTimer #timer-caption { color: $secondary; }
    """

    def compose(self) -> ComposeResult:
        yield Digits("0:00:00", id="timer-digits")
        yield Label("no timer running", id="timer-caption")

    def show_status(self, status: TimerStatus, now: datetime) -> None:
        digits = self.query_one("#timer-digits", Digits)
        caption = self.query_one("#timer-caption", Label)
        if status.timer is None:
            self.set_classes("idle")
            digits.update(format_hours(status.today_seconds))
            caption.update("idle · press s to start · today " + format_hours(status.today_seconds))
        else:
            self.set_classes("running")
            self.toggle_class("tick")  # subtle pulse each refresh
            h, rem = divmod(status.elapsed_seconds, 3600)
            digits.update(f"{h}:{rem // 60:02d}:{rem % 60:02d}")
            where = (
                f"{status.client.slug}/{status.project.slug}"
                if status.client and status.project
                else "?"
            )
            note = f" · {status.timer.note}" if status.timer.note else ""
            caption.update(
                f"▶ {where}{note} · since {status.timer.started_at:%-I:%M%p}".lower()
                + f" · today {format_hours(status.today_seconds)}"
            )
