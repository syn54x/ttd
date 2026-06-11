"""The -i form engine.

Each mutating command declares its inputs as a Pydantic model whose fields
carry UI metadata in json_schema_extra. interactive_fill() walks the fields
in declared order, skips anything already supplied by flags, prompts for the
rest (questionary), and validates through the same model both paths share.

Commands run inside an event loop (Cyclopts runs them as coroutines), so the
form engine is async end to end; choice providers and backends may be sync or
async — awaitables are awaited.

The prompt layer is injectable so tests can script answers.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from ttd.cli._run import abort
from ttd.core.errors import TtdError


@dataclass
class Question:
    field: str
    widget: str  # text | select | confirm
    message: str
    default: Any = None
    choices: list[str] | None = None
    validate: Callable[[str], bool | str] | None = None
    optional: bool = False


class Backend(Protocol):
    def ask(self, question: Question) -> Any: ...


class QuestionaryBackend:
    async def ask(self, question: Question) -> Any:
        import questionary

        if question.widget == "confirm":
            answer = await questionary.confirm(
                question.message, default=bool(question.default)
            ).ask_async()
        elif question.widget == "select":
            answer = await questionary.select(
                question.message,
                choices=question.choices or [],
                default=question.default if question.default in (question.choices or []) else None,
                use_search_filter=len(question.choices or []) > 6,
                use_jk_keys=False,
            ).ask_async()
        else:
            answer = await questionary.text(
                question.message,
                default="" if question.default is None else str(question.default),
                validate=question.validate,
            ).ask_async()
        if answer is None:  # ctrl-c / esc
            abort()
        return answer


async def _question_for(name: str, field: Any, extra: dict[str, Any]) -> Question:
    widget = extra.get("widget", "text")
    message = extra.get("prompt", name.replace("_", " ").capitalize())
    default = field.default if field.default is not PydanticUndefined else None
    optional = field.default is not PydanticUndefined
    choices = extra.get("choices")
    if callable(choices):
        choices = choices()
        if inspect.isawaitable(choices):
            choices = await choices
    if widget == "select" and not choices:
        raise TtdError(f"No choices available for {message.lower()} — create one first")
    annotation = field.annotation
    if widget == "text" and (annotation is bool or str(annotation) == "bool"):
        widget = "confirm"
    return Question(
        field=name,
        widget=widget,
        message=message,
        default=default,
        choices=choices,
        validate=extra.get("validate"),
        optional=optional,
    )


async def interactive_fill[M: BaseModel](
    model_cls: type[M],
    partial: dict[str, Any],
    backend: Backend | None = None,
) -> M:
    backend = backend or QuestionaryBackend()
    values = {k: v for k, v in partial.items() if v is not None}

    for name, field in model_cls.model_fields.items():
        if name in values:
            continue
        extra = dict(field.json_schema_extra or {})  # type: ignore[arg-type]
        if extra.get("skip"):
            continue
        question = await _question_for(name, field, extra)
        answer = backend.ask(question)
        if inspect.isawaitable(answer):
            answer = await answer
        if isinstance(answer, str):
            answer = answer.strip()
            if answer == "":
                if question.optional:
                    continue  # keep the model default
                raise TtdError(f"{question.message} is required")
        values[name] = answer

    try:
        return model_cls.model_validate(values)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise TtdError(f"Invalid {loc}: {first['msg']}") from exc
