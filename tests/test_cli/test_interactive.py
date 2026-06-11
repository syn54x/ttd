import pytest
from pydantic import BaseModel, Field

from ttd.cli._interactive import Question, interactive_fill
from ttd.cli._pickers import split_project_choice, validate_timespec
from ttd.core.errors import TtdError


class FakeBackend:
    """Answers questions from a script; records what was asked."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.asked: list[Question] = []

    def ask(self, question: Question):
        self.asked.append(question)
        if question.field not in self.answers:
            raise AssertionError(f"Unexpected prompt for '{question.field}'")
        return self.answers[question.field]


class DemoInput(BaseModel):
    name: str = Field(json_schema_extra={"prompt": "Name"})
    flavor: str = Field(
        json_schema_extra={"prompt": "Flavor", "widget": "select", "choices": ["a", "b"]}
    )
    note: str | None = Field(None, json_schema_extra={"prompt": "Note (optional)"})
    billable: bool = Field(True, json_schema_extra={"prompt": "Billable?"})


async def test_prompts_only_missing_fields():
    backend = FakeBackend({"note": "hi", "billable": False})
    result = await interactive_fill(DemoInput, {"name": "X", "flavor": "a"}, backend)
    assert result.name == "X"
    assert result.note == "hi"
    assert result.billable is False
    assert [q.field for q in backend.asked] == ["note", "billable"]


async def test_prefill_used_as_skip_even_for_falsy_strings():
    backend = FakeBackend({"name": "Y", "note": "", "billable": True})
    result = await interactive_fill(DemoInput, {"flavor": "b"}, backend)
    assert result.flavor == "b"
    assert result.name == "Y"
    assert result.note is None  # blank answer keeps the default


async def test_blank_required_field_errors():
    backend = FakeBackend({"name": "", "flavor": "a", "note": "", "billable": True})
    with pytest.raises(TtdError, match="required"):
        await interactive_fill(DemoInput, {}, backend)


async def test_bool_fields_become_confirm_widgets():
    backend = FakeBackend({"name": "X", "flavor": "a", "note": "", "billable": True})
    await interactive_fill(DemoInput, {}, backend)
    by_field = {q.field: q for q in backend.asked}
    assert by_field["billable"].widget == "confirm"
    assert by_field["flavor"].widget == "select"
    assert by_field["flavor"].choices == ["a", "b"]


async def test_select_with_no_choices_errors():
    class NoChoices(BaseModel):
        pick: str = Field(json_schema_extra={"widget": "select", "choices": lambda: []})

    with pytest.raises(TtdError, match="create one first"):
        await interactive_fill(NoChoices, {}, FakeBackend({}))


async def test_validation_failure_surfaces_as_ttd_error():
    class Strict(BaseModel):
        count: int = Field(json_schema_extra={"prompt": "Count"})

    backend = FakeBackend({"count": "not-a-number"})
    with pytest.raises(TtdError, match="count"):
        await interactive_fill(Strict, {}, backend)


def test_split_project_choice():
    assert split_project_choice("acme/api") == ("api", "acme")
    assert split_project_choice("api") == ("api", None)


def test_timespec_validator():
    assert validate_timespec("today 9am to 5pm") is True
    assert validate_timespec("2h") is True
    assert "Enter a time" in validate_timespec("   ")
    assert isinstance(validate_timespec("banana"), str)
