"""Choice semantics shared by grading, reports and legacy single-choice data."""


def correct_ids(question):
    return question.get('correct_ids', [question['correct_id']] if question.get('correct_id') else [])


def selected_ids(answer):
    return answer if isinstance(answer, list) else [answer] if isinstance(answer, str) else []


def is_correct(question, answer):
    selected = selected_ids(answer)
    return bool(selected) and len(selected) == len(set(selected)) and set(selected) == set(correct_ids(question))
