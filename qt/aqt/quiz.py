# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Multiple-choice quizzes written by an AI model from a deck's cards.

Quizzes are kept separate from reviews: answering quiz questions does not
affect scheduling.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Any

import requests

import aqt
import aqt.main
from anki.collection import Collection, SearchNode
from anki.decks import DeckId
from anki.utils import html_to_text_line
from aqt.operations import QueryOp
from aqt.qt import *
from aqt.utils import (
    disable_help_button,
    restoreGeom,
    saveGeom,
    showInfo,
    showWarning,
    tr,
)
from aqt.webview import AnkiWebView, AnkiWebViewKind

QUIZ_LENGTH = 10
MIN_CARDS = 4
OPTION_COUNT = 4
# keep requests small and cheap; long fields are rarely useful for a question
MAX_FIELD_CHARS = 600
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = f"""\
You write multiple-choice quiz questions that help a student review their \
flashcards. You will receive a JSON array of flashcards, each with an "id", \
a "front" and a "back".

For each flashcard, write one question that tests the same knowledge in a \
fresh way, rather than copying the front word for word. Give exactly \
{OPTION_COUNT} options: one correct answer, and plausible but clearly wrong \
distractors of similar length and style. Write in the same language as the \
flashcards. Skip any flashcard that can't be turned into a sensible question.

Reply with JSON only, in this shape:
{{"questions": [{{"id": <flashcard id>, "question": "...", \
"options": ["...", "...", "...", "..."], \
"answer": <index of the correct option>, \
"explanation": "<one short sentence on why the answer is right>"}}]}}"""


class QuizError(Exception):
    "An error with a message suitable for showing to the user."


@dataclass
class QuizCard:
    front: str
    back: str


@dataclass
class QuizQuestion:
    question: str
    options: list[str]
    answer: int
    explanation: str


# Entry points
##########################################################################


def start_quiz(mw: aqt.main.AnkiQt, deck_id: DeckId | None = None) -> None:
    "Pick cards from a deck (the current one by default) and show a quiz."
    if not mw.pm.ai_api_key() and not show_ai_settings(mw):
        return
    if deck_id is None:
        deck_id = mw.col.decks.get_current_id()
    deck_name = mw.col.decks.name(deck_id)

    def on_cards(cards: list[QuizCard]) -> None:
        if len(cards) < MIN_CARDS:
            showInfo(tr.quiz_not_enough_cards(count=MIN_CARDS), parent=mw)
            return
        api_key = mw.pm.ai_api_key()
        model = mw.pm.ai_model()
        QueryOp(
            parent=mw,
            op=lambda _col: request_questions(cards, api_key, model),
            success=lambda questions: QuizDialog(mw, deck_id, deck_name, questions),
        ).failure(lambda exc: _on_failure(mw, exc)).without_collection().with_progress(
            tr.quiz_generating()
        ).run_in_background()

    QueryOp(
        parent=mw, op=lambda col: pick_cards(col, deck_name), success=on_cards
    ).run_in_background()


def _on_failure(mw: aqt.main.AnkiQt, exc: Exception) -> None:
    if isinstance(exc, QuizError):
        showWarning(str(exc), parent=mw)
    else:
        showWarning(tr.quiz_error_request(error=str(exc)), parent=mw)


def show_ai_settings(mw: aqt.main.AnkiQt) -> bool:
    "Returns true if the user saved an API key."
    dialog = AISettingsDialog(mw)
    return bool(dialog.exec() == QDialog.DialogCode.Accepted and mw.pm.ai_api_key())


# Choosing cards
##########################################################################


def pick_cards(col: Collection, deck_name: str) -> list[QuizCard]:
    """Up to QUIZ_LENGTH random cards from the deck and its subdecks.

    Cards that have already been studied are preferred, as it's more useful to
    be quizzed on material you've seen."""
    deck_search = col.build_search_string(SearchNode(deck=deck_name))
    studied = list(col.find_cards(f"{deck_search} -is:suspended -is:new"))
    unstudied = list(col.find_cards(f"{deck_search} -is:suspended is:new"))
    random.shuffle(studied)
    random.shuffle(unstudied)

    cards: list[QuizCard] = []
    for card_id in [*studied, *unstudied]:
        card = col.get_card(card_id)
        front = html_to_text_line(card.question()).strip()
        # the back usually repeats the front, followed by <hr id=answer>
        back_html = re.split(r"<hr id=answer>", card.answer(), maxsplit=1)[-1]
        back = html_to_text_line(back_html).strip()
        if front and back:
            cards.append(
                QuizCard(front=front[:MAX_FIELD_CHARS], back=back[:MAX_FIELD_CHARS])
            )
        if len(cards) >= QUIZ_LENGTH:
            break
    return cards


# Talking to the API
##########################################################################


def request_questions(
    cards: list[QuizCard], api_key: str, model: str
) -> list[QuizQuestion]:
    flashcards = [
        {"id": idx, "front": card.front, "back": card.back}
        for idx, card in enumerate(cards)
    ]
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(flashcards, ensure_ascii=False)},
        ],
    }
    try:
        resp = requests.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        raise QuizError(tr.quiz_error_network()) from exc

    if resp.status_code == 401:
        raise QuizError(tr.quiz_error_invalid_key())
    if not resp.ok:
        raise QuizError(tr.quiz_error_request(error=_api_error_message(resp)))

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        questions = parse_questions(json.loads(content))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise QuizError(tr.quiz_error_bad_response()) from exc
    if not questions:
        raise QuizError(tr.quiz_error_bad_response())
    return questions


def _api_error_message(resp: requests.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP {resp.status_code}"


def parse_questions(data: Any) -> list[QuizQuestion]:
    """Keep only well-formed questions, and shuffle each one's options, as
    models tend to put the correct answer in the same position."""
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    questions = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        options = item.get("options")
        answer = item.get("answer")
        if not (
            isinstance(question, str)
            and question.strip()
            and isinstance(options, list)
            and len(options) == OPTION_COUNT
            and all(isinstance(opt, str) and opt.strip() for opt in options)
            and len(set(options)) == OPTION_COUNT
            and isinstance(answer, int)
            and 0 <= answer < OPTION_COUNT
        ):
            continue
        correct = options[answer]
        shuffled = random.sample(options, len(options))
        explanation = item.get("explanation")
        questions.append(
            QuizQuestion(
                question=question.strip(),
                options=[opt.strip() for opt in shuffled],
                answer=shuffled.index(correct),
                explanation=explanation.strip() if isinstance(explanation, str) else "",
            )
        )
    return questions[:QUIZ_LENGTH]


# Dialogs
##########################################################################


class AISettingsDialog(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle(tr.quiz_settings_title())
        disable_help_button(self)
        self.setMinimumWidth(460)

        intro = QLabel(tr.quiz_settings_intro())
        intro.setWordWrap(True)

        self.key_edit = QLineEdit(mw.pm.ai_api_key())
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-...")
        self.model_edit = QLineEdit(mw.pm.ai_model())

        storage = QLabel(tr.quiz_settings_key_storage())
        storage.setWordWrap(True)
        get_key = QLabel(tr.quiz_settings_get_key())
        get_key.setOpenExternalLinks(True)

        form = QFormLayout()
        form.addRow(tr.quiz_settings_api_key(), self.key_edit)
        form.addRow(tr.quiz_settings_model(), self.model_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)

        layout = QVBoxLayout()
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(storage)
        layout.addWidget(get_key)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def accept(self) -> None:
        self.mw.pm.set_ai_api_key(self.key_edit.text().strip())
        self.mw.pm.set_ai_model(self.model_edit.text().strip())
        super().accept()


class QuizDialog(QDialog):
    def __init__(
        self,
        mw: aqt.main.AnkiQt,
        deck_id: DeckId,
        deck_name: str,
        questions: list[QuizQuestion],
    ) -> None:
        super().__init__(mw)
        self.mw = mw
        self.deck_id = deck_id
        mw.garbage_collect_on_dialog_finish(self)
        self.setWindowTitle(tr.quiz_window_title(deck=deck_name))
        disable_help_button(self)

        self.web = AnkiWebView(kind=AnkiWebViewKind.QUIZ)
        self.web.set_bridge_command(self._on_bridge_cmd, self)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)
        restoreGeom(self, "quiz", default_size=(640, 640))
        qconnect(self.finished, self._on_finished)

        self.web.stdHtml(
            "<div id=quiz></div>",
            css=["css/quiz.css"],
            js=["js/quiz.js"],
            context=self,
        )
        data = {
            "questions": [q.__dict__ for q in questions],
            "strings": _quiz_strings(len(questions)),
        }
        self.web.eval(f"ankiStartQuiz({json.dumps(data)});")
        self.show()

    def _on_bridge_cmd(self, cmd: str) -> None:
        # defer closing, so the webview isn't cleaned up while it's still
        # handling this message
        if cmd == "close":
            self.mw.progress.single_shot(0, self.reject)
        elif cmd == "again":

            def again() -> None:
                self.reject()
                start_quiz(self.mw, self.deck_id)

            self.mw.progress.single_shot(0, again)

    def _on_finished(self, _code: Any) -> None:
        saveGeom(self, "quiz")
        self.web.cleanup()
        self.web = None  # type: ignore


def _quiz_strings(total: int) -> dict[str, Any]:
    """Translated strings for the quiz page. Strings containing numbers are
    rendered for every possible value, so plurals are handled by Fluent."""
    return {
        "progress": [
            tr.quiz_question_progress(number=number, total=total)
            for number in range(1, total + 1)
        ],
        "score": [
            tr.quiz_score(correct=correct, total=total) for correct in range(total + 1)
        ],
        "next": tr.quiz_next(),
        "seeResults": tr.quiz_see_results(),
        "correct": tr.quiz_correct(),
        "incorrect": tr.quiz_incorrect(),
        "perfect": tr.quiz_result_perfect(),
        "good": tr.quiz_result_good(),
        "keepGoing": tr.quiz_result_keep_going(),
        "newQuiz": tr.quiz_new_quiz(),
        "close": tr.quiz_close(),
    }
