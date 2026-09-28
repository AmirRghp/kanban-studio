import json

import pytest
from pydantic import ValidationError

from app.models import BoardData

# Verbatim shape of `initialData` in frontend/src/lib/kanban.ts. If the frontend changes
# its data model, this test is what should fail.
FRONTEND_BOARD = {
    "columns": [
        {"id": "col-backlog", "title": "Backlog", "cardIds": ["card-1", "card-2"]},
        {"id": "col-discovery", "title": "Discovery", "cardIds": ["card-3"]},
        {"id": "col-progress", "title": "In Progress", "cardIds": ["card-4", "card-5"]},
        {"id": "col-review", "title": "Review", "cardIds": ["card-6"]},
        {"id": "col-done", "title": "Done", "cardIds": ["card-7", "card-8"]},
    ],
    "cards": {
        "card-1": {
            "id": "card-1",
            "title": "Align roadmap themes",
            "details": "Draft quarterly themes with impact statements and metrics.",
        },
        "card-2": {
            "id": "card-2",
            "title": "Gather customer signals",
            "details": "Review support tags, sales notes, and churn feedback.",
        },
        "card-3": {
            "id": "card-3",
            "title": "Prototype analytics view",
            "details": "Sketch initial dashboard layout and key drill-downs.",
        },
        "card-4": {
            "id": "card-4",
            "title": "Refine status language",
            "details": "Standardize column labels and tone across the board.",
        },
        "card-5": {
            "id": "card-5",
            "title": "Design card layout",
            "details": "Add hierarchy and spacing for scanning dense lists.",
        },
        "card-6": {
            "id": "card-6",
            "title": "QA micro-interactions",
            "details": "Verify hover, focus, and loading states.",
        },
        "card-7": {
            "id": "card-7",
            "title": "Ship marketing page",
            "details": "Final copy approved and asset pack delivered.",
        },
        "card-8": {
            "id": "card-8",
            "title": "Close onboarding sprint",
            "details": "Document release notes and share internally.",
        },
    },
}


def test_accepts_the_frontend_board_shape() -> None:
    board = BoardData.model_validate(FRONTEND_BOARD)

    assert len(board.columns) == 5
    assert len(board.cards) == 8
    assert board.columns[0].card_ids == ["card-1", "card-2"]
    assert board.cards["card-1"].title == "Align roadmap themes"


def _without_optional_fields(board: dict) -> dict:
    """Strip the optional card fields so a comparison ignores them when unset.

    The wire format always emits dueDate/labels (as null/[]); the fixtures predate
    them. Comparing the shape without the new fields keeps the drift guard focused on
    the fields the frontend fixture actually has.
    """
    stripped = json.loads(json.dumps(board))
    for card in stripped["cards"].values():
        card.pop("dueDate", None)
        card.pop("labels", None)
    return stripped


def test_serialises_back_to_the_same_json() -> None:
    board = BoardData.model_validate(FRONTEND_BOARD)

    assert _without_optional_fields(board.model_dump()) == FRONTEND_BOARD


def test_survives_a_json_round_trip() -> None:
    board = BoardData.model_validate(FRONTEND_BOARD)

    revived = BoardData.model_validate_json(board.model_dump_json())

    assert _without_optional_fields(revived.model_dump()) == FRONTEND_BOARD


def test_a_card_can_carry_a_due_date_and_labels() -> None:
    board = BoardData.model_validate(
        {
            "columns": [{"id": "c1", "title": "A", "cardIds": ["card-1"]}],
            "cards": {
                "card-1": {
                    "id": "card-1",
                    "title": "T",
                    "details": "D",
                    "dueDate": "2026-03-01",
                    "labels": ["design", "urgent"],
                }
            },
        }
    )

    card = board.cards["card-1"]
    assert card.due_date is not None and card.due_date.isoformat() == "2026-03-01"
    assert card.labels == ["design", "urgent"]

    # Round-trips with the camelCase wire name.
    raw = json.loads(board.model_dump_json())
    assert raw["cards"]["card-1"]["dueDate"] == "2026-03-01"
    assert "due_date" not in raw["cards"]["card-1"]


def test_an_invalid_due_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BoardData.model_validate(
            {
                "columns": [{"id": "c1", "title": "A", "cardIds": ["card-1"]}],
                "cards": {
                    "card-1": {
                        "id": "card-1",
                        "title": "T",
                        "details": "D",
                        "dueDate": "not-a-date",
                    }
                },
            }
        )


def test_wire_format_keeps_the_frontend_spelling() -> None:
    board = BoardData.model_validate(FRONTEND_BOARD)

    raw = json.loads(board.model_dump_json())

    assert "cardIds" in raw["columns"][0]
    assert "card_ids" not in raw["columns"][0]


def test_python_attributes_are_snake_case() -> None:
    board = BoardData.model_validate(FRONTEND_BOARD)

    assert board.columns[0].card_ids == ["card-1", "card-2"]


def test_accepts_an_empty_board() -> None:
    board = BoardData.model_validate({"columns": [], "cards": {}})

    assert board.columns == []


def test_accepts_a_column_with_no_cards() -> None:
    board = BoardData.model_validate(
        {"columns": [{"id": "c1", "title": "Empty", "cardIds": []}], "cards": {}}
    )

    assert board.columns[0].card_ids == []


def test_rejects_a_column_referencing_an_unknown_card() -> None:
    with pytest.raises(ValidationError, match="references unknown cards"):
        BoardData.model_validate(
            {
                "columns": [{"id": "c1", "title": "Todo", "cardIds": ["ghost"]}],
                "cards": {},
            }
        )


def test_rejects_a_cards_key_that_disagrees_with_the_card_id() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        BoardData.model_validate(
            {
                "columns": [{"id": "c1", "title": "Todo", "cardIds": ["card-1"]}],
                "cards": {"card-9": {"id": "card-1", "title": "T", "details": "D"}},
            }
        )


def test_rejects_a_card_appearing_in_two_columns() -> None:
    with pytest.raises(ValidationError, match="more than one place"):
        BoardData.model_validate(
            {
                "columns": [
                    {"id": "c1", "title": "A", "cardIds": ["card-1"]},
                    {"id": "c2", "title": "B", "cardIds": ["card-1"]},
                ],
                "cards": {"card-1": {"id": "card-1", "title": "T", "details": "D"}},
            }
        )


def test_rejects_a_card_repeated_within_one_column() -> None:
    with pytest.raises(ValidationError, match="more than one place"):
        BoardData.model_validate(
            {
                "columns": [
                    {"id": "c1", "title": "A", "cardIds": ["card-1", "card-1"]}
                ],
                "cards": {"card-1": {"id": "card-1", "title": "T", "details": "D"}},
            }
        )


def test_rejects_a_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        BoardData.model_validate({"columns": []})
