# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from typing import Any

import pytest

from aqt.quiz import QUIZ_LENGTH, parse_questions


def make_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": 0,
        "question": "What is the capital of France?",
        "options": ["Paris", "Lyon", "Marseille", "Nice"],
        "answer": 0,
        "explanation": "Paris has been the capital since 987.",
    }
    item.update(overrides)
    return item


def test_parse_questions_answer_still_points_at_correct_option_after_shuffle() -> None:
    for _ in range(20):
        [question] = parse_questions({"questions": [make_item(answer=2)]})

        assert question.options[question.answer] == "Marseille"
        assert sorted(question.options) == ["Lyon", "Marseille", "Nice", "Paris"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"options": ["Paris", "Lyon", "Marseille"]},
        {"options": ["Paris", "Paris", "Lyon", "Nice"]},
        {"options": ["Paris", "", "Lyon", "Nice"]},
        {"options": ["Paris", 2, "Lyon", "Nice"]},
        {"answer": 4},
        {"answer": "0"},
        {"question": "  "},
    ],
)
def test_parse_questions_drops_malformed_question(overrides: dict[str, Any]) -> None:
    questions = parse_questions(
        {"questions": [make_item(**overrides), make_item(question="Kept?")]}
    )

    assert [q.question for q in questions] == ["Kept?"]


@pytest.mark.parametrize(
    "data", [[make_item()], {"questions": "none"}, {"items": [make_item()]}]
)
def test_parse_questions_returns_nothing_for_unexpected_shape(data: Any) -> None:
    assert parse_questions(data) == []


def test_parse_questions_uses_empty_explanation_when_missing() -> None:
    [question] = parse_questions({"questions": [make_item(explanation=None)]})

    assert question.explanation == ""


def test_parse_questions_caps_quiz_length() -> None:
    items = [make_item(question=f"Q{i}") for i in range(QUIZ_LENGTH + 5)]

    assert len(parse_questions({"questions": items})) == QUIZ_LENGTH
