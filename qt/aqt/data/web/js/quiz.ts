/* Copyright: Ankitects Pty Ltd and contributors
 * License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */

/* eslint
@typescript-eslint/no-unused-vars: "off",
*/

interface QuizQuestion {
    question: string;
    options: string[];
    answer: number;
    explanation: string;
}

interface QuizStrings {
    // indexed by question number, starting at 0
    progress: string[];
    next: string;
    seeResults: string;
    correct: string;
    incorrect: string;
    // indexed by number of correct answers
    score: string[];
    perfect: string;
    good: string;
    keepGoing: string;
    newQuiz: string;
    close: string;
}

interface QuizData {
    questions: QuizQuestion[];
    strings: QuizStrings;
}

// Called from quiz.py. Question text comes from an AI model, so it's only
// ever inserted with textContent, never as HTML.
function ankiStartQuiz(data: QuizData): void {
    const { questions, strings } = data;
    const root = document.getElementById("quiz");
    let index = 0;
    let correctCount = 0;
    let answered = false;
    let optionButtons: HTMLButtonElement[] = [];

    function el<K extends keyof HTMLElementTagNameMap>(
        tag: K,
        className: string,
        text?: string,
    ): HTMLElementTagNameMap[K] {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function animated(): boolean {
        const classes = document.body.classList;
        return (
            classes.contains("fancy")
            && !classes.contains("reduce-motion")
            && !window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );
    }

    // the progress bar persists between questions, so it can animate
    const progress = el("div", "quiz-progress");
    const progressBar = el("div", "quiz-progress-bar");
    progress.append(progressBar);
    const stage = el("div", "quiz-stage");
    root.append(progress, stage);

    function setProgress(done: number): void {
        progressBar.style.width = `${(done / questions.length) * 100}%`;
    }

    function showQuestion(): void {
        const question = questions[index];
        answered = false;
        setProgress(index);

        const card = el("div", "quiz-card");
        card.append(
            el("div", "quiz-counter", strings.progress[index]),
            el("h2", "quiz-question", question.question),
        );

        const options = el("div", "quiz-options");
        optionButtons = question.options.map((text, i) => {
            const button = el("button", "quiz-option");
            button.style.setProperty("--enter-delay", `${120 + i * 60}ms`);
            button.append(el("span", "quiz-key", String(i + 1)), el("span", "quiz-option-text", text));
            button.addEventListener("click", () => choose(i));
            options.append(button);
            return button;
        });
        card.append(options);

        stage.replaceChildren(card);
    }

    function choose(choice: number): void {
        if (answered) {
            return;
        }
        answered = true;
        const question = questions[index];
        const isRight = choice === question.answer;
        if (isRight) {
            correctCount += 1;
        }

        optionButtons.forEach((button, i) => {
            button.classList.add("locked");
            button.setAttribute("aria-disabled", "true");
            if (i === question.answer) {
                button.classList.add("correct");
            } else if (i === choice) {
                button.classList.add("wrong");
            } else {
                button.classList.add("dimmed");
            }
        });
        setProgress(index + 1);

        const feedback = el("div", `quiz-feedback ${isRight ? "is-correct" : "is-wrong"}`);
        feedback.append(el("strong", "", isRight ? strings.correct : strings.incorrect));
        if (question.explanation) {
            feedback.append(" ", el("span", "", question.explanation));
        }

        const isLast = index === questions.length - 1;
        const next = el("button", "quiz-next", isLast ? strings.seeResults : strings.next);
        next.addEventListener("click", () => {
            index += 1;
            if (isLast) {
                showResults();
            } else {
                showQuestion();
            }
        });

        const card = stage.querySelector(".quiz-card");
        card.append(feedback, next);
        // Enter/Space then activate it natively
        next.focus();
    }

    function showResults(): void {
        const total = questions.length;
        const ratio = correctCount / total;

        const card = el("div", "quiz-card quiz-results");
        const number = el("div", "quiz-score-number", animated() ? "0" : String(correctCount));
        const score = el("div", "quiz-score-total");
        score.append(number, el("span", "quiz-score-out-of", `/${total}`));

        let message = strings.keepGoing;
        if (ratio === 1) {
            message = strings.perfect;
        } else if (ratio >= 0.7) {
            message = strings.good;
        }

        const buttons = el("div", "quiz-result-buttons");
        const again = el("button", "quiz-next", strings.newQuiz);
        again.addEventListener("click", () => pycmd("again"));
        const close = el("button", "", strings.close);
        close.addEventListener("click", () => pycmd("close"));
        buttons.append(again, close);

        card.append(
            score,
            el("div", "quiz-message", message),
            el("div", "quiz-score-text", strings.score[correctCount]),
            buttons,
        );
        stage.replaceChildren(card);
        again.focus();

        if (animated()) {
            countUp(number, correctCount);
            if (ratio >= 0.7) {
                confetti();
            }
        }
    }

    function countUp(node: HTMLElement, target: number): void {
        let shown = 0;
        const timer = setInterval(() => {
            if (shown >= target) {
                clearInterval(timer);
                return;
            }
            shown += 1;
            node.textContent = String(shown);
        }, 90);
    }

    function confetti(): void {
        const colors = [
            "var(--state-new)",
            "var(--state-review)",
            "var(--state-learn)",
            "var(--flag-2)",
            "var(--flag-6)",
            "var(--flag-7)",
        ];
        const layer = el("div", "quiz-confetti");
        for (let i = 0; i < 70; i++) {
            const piece = el("span", "");
            piece.style.left = `${Math.random() * 100}%`;
            piece.style.background = colors[i % colors.length];
            piece.style.animationDelay = `${Math.random() * 400}ms`;
            piece.style.animationDuration = `${1500 + Math.random() * 1200}ms`;
            piece.style.setProperty("--drift", `${(Math.random() - 0.5) * 200}px`);
            piece.style.setProperty("--spin", `${(Math.random() - 0.5) * 1440}deg`);
            layer.append(piece);
        }
        document.body.append(layer);
        setTimeout(() => layer.remove(), 3500);
    }

    document.addEventListener("keydown", (event) => {
        if (answered || event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }
        const number = parseInt(event.key, 10);
        if (number >= 1 && number <= optionButtons.length) {
            event.preventDefault();
            choose(number - 1);
        }
    });

    showQuestion();
}
