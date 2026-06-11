"""Markdown invoice rendering (Jinja2)."""

from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ttd.config.schema import Settings
from ttd.core.money import format_money
from ttd.services.invoicing import InvoiceView

_env = Environment(
    loader=PackageLoader("ttd.invoicing", "templates"),
    autoescape=select_autoescape(default=False),
    trim_blocks=False,
    keep_trailing_newline=True,
)


def render_markdown(view: InvoiceView, settings: Settings) -> str:
    currency = view.invoice.currency

    def money(value: Decimal) -> str:
        return format_money(value, currency)

    template = _env.get_template("invoice.md.j2")
    return template.render(
        invoice=view.invoice,
        client=view.client,
        lines=view.lines,
        user=settings.user,
        money=money,
        terms_days=settings.invoice.payment_terms_days,
    )


def write_markdown(view: InvoiceView, settings: Settings, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(view, settings), encoding="utf-8")
    return path
