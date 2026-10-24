quiz-menu-quiz-me = Quiz Me on Current Deck...
quiz-menu-ai-settings = AI Settings...
quiz-overview-button = Quiz Me
quiz-window-title = Quiz: { $deck }
quiz-generating = Writing quiz questions...

## AI settings dialog

quiz-settings-title = AI Settings
quiz-settings-intro = Quizzes are written by OpenAI's API. When you start a quiz, the text of some of the deck's cards is sent to OpenAI, and usage is billed to your OpenAI account.
quiz-settings-api-key = OpenAI API key
quiz-settings-model = Model
quiz-settings-key-storage = Your key is stored only on this computer and is never synced.
quiz-settings-get-key = <a href="https://platform.openai.com/api-keys">Get an API key</a>

## Errors

quiz-not-enough-cards = This deck needs at least { $count } cards with text to make a quiz.
quiz-error-invalid-key = OpenAI didn't accept your API key. You can change it in Tools > AI Settings.
quiz-error-network = Couldn't reach OpenAI. Please check your internet connection and try again.
quiz-error-request = The quiz couldn't be created: { $error }
quiz-error-bad-response = The AI's reply couldn't be turned into a quiz. Please try again.

## Quiz screen

# Shown above each question, eg "Question 3 of 10"
quiz-question-progress = Question { $number } of { $total }
quiz-next = Next
quiz-see-results = See Results
quiz-correct = Correct!
quiz-incorrect = Not quite.
quiz-score = { $correct } out of { $total } correct
quiz-result-perfect = Perfect score!
quiz-result-good = Nice work!
quiz-result-keep-going = Keep practicing, you'll get there.
quiz-new-quiz = New Quiz
quiz-close = Close
