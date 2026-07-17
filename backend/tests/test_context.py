from app.services.context import ContextMessage, select_complete_rounds


def test_selects_latest_five_complete_rounds() -> None:
    messages = []
    for index in range(7):
        messages.extend(
            [
                ContextMessage("user", f"u{index}"),
                ContextMessage("assistant", f"a{index}"),
            ]
        )
    selected = select_complete_rounds(messages, 5)
    assert [item.content for item in selected] == [
        "u2", "a2", "u3", "a3", "u4", "a4", "u5", "a5", "u6", "a6"
    ]


def test_ignores_incomplete_round() -> None:
    messages = [
        ContextMessage("user", "complete"),
        ContextMessage("assistant", "answer"),
        ContextMessage("user", "unfinished"),
    ]
    assert [item.content for item in select_complete_rounds(messages)] == ["complete", "answer"]
