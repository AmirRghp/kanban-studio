import pytest

from app.models import BoardData
from app.ops import (
    ChatResponse,
    CreateCard,
    DeleteCard,
    MoveCard,
    RenameColumn,
    UpdateCard,
    apply_operations,
    new_card_id,
)


def board() -> BoardData:
    return BoardData.model_validate(
        {
            "columns": [
                {"id": "c1", "title": "Backlog", "cardIds": ["k1", "k2"]},
                {"id": "c2", "title": "Done", "cardIds": ["k3"]},
            ],
            "cards": {
                "k1": {"id": "k1", "title": "One", "details": "d1"},
                "k2": {"id": "k2", "title": "Two", "details": "d2"},
                "k3": {"id": "k3", "title": "Three", "details": "d3"},
            },
        }
    )


def test_create_card_appends_to_the_target_column() -> None:
    result, warnings = apply_operations(
        board(), [CreateCard(op="create_card", column_id="c1", title="New", details="nd")]
    )

    assert warnings == []
    assert len(result.cards) == 4
    new = [c for c in result.cards.values() if c.title == "New"][0]
    assert result.columns[0].card_ids[-1] == new.id


def test_create_card_uses_a_server_generated_id() -> None:
    result, _ = apply_operations(
        board(), [CreateCard(op="create_card", column_id="c1", title="New", details="d")]
    )

    new_ids = set(result.cards) - {"k1", "k2", "k3"}
    assert len(new_ids) == 1
    assert new_ids.pop().startswith("card-")


def test_two_created_cards_get_distinct_ids() -> None:
    assert new_card_id() != new_card_id()


def test_move_card_appends_to_the_end_of_the_target() -> None:
    result, warnings = apply_operations(
        board(), [MoveCard(op="move_card", card_id="k1", column_id="c2")]
    )

    assert warnings == []
    assert result.columns[0].card_ids == ["k2"]
    assert result.columns[1].card_ids == ["k3", "k1"]


def test_move_card_reorders_within_the_same_column() -> None:
    result, _ = apply_operations(
        board(), [MoveCard(op="move_card", card_id="k1", column_id="c1")]
    )

    assert result.columns[0].card_ids == ["k2", "k1"]


def test_update_card_changes_text_and_keeps_position() -> None:
    result, warnings = apply_operations(
        board(),
        [UpdateCard(op="update_card", card_id="k1", title="Renamed", details="new d")],
    )

    assert warnings == []
    assert result.columns[0].card_ids == ["k1", "k2"]
    assert result.cards["k1"].title == "Renamed"
    assert result.cards["k1"].details == "new d"


def test_delete_card_removes_from_map_and_from_card_ids() -> None:
    result, warnings = apply_operations(
        board(), [DeleteCard(op="delete_card", card_id="k1")]
    )

    assert warnings == []
    assert "k1" not in result.cards
    assert result.columns[0].card_ids == ["k2"]


def test_rename_column_changes_only_the_title() -> None:
    result, warnings = apply_operations(
        board(), [RenameColumn(op="rename_column", column_id="c1", title="Inbox")]
    )

    assert warnings == []
    assert result.columns[0].title == "Inbox"
    assert result.columns[0].card_ids == ["k1", "k2"]
    assert len(result.cards) == 3


def test_operations_apply_in_order() -> None:
    result, _ = apply_operations(
        board(),
        [
            CreateCard(op="create_card", column_id="c1", title="Temp", details="d"),
            RenameColumn(op="rename_column", column_id="c1", title="Inbox"),
        ],
    )

    assert result.columns[0].title == "Inbox"
    assert len(result.columns[0].card_ids) == 3


# ---------------------------------------------------------------- skipping


def test_unknown_card_id_is_skipped_with_a_warning() -> None:
    result, warnings = apply_operations(
        board(), [MoveCard(op="move_card", card_id="ghost", column_id="c2")]
    )

    assert result == board()
    assert len(warnings) == 1
    assert "ghost" in warnings[0]


def test_unknown_column_id_is_skipped_with_a_warning() -> None:
    result, warnings = apply_operations(
        board(), [CreateCard(op="create_card", column_id="ghost", title="X", details="d")]
    )

    assert len(result.cards) == 3
    assert "ghost" in warnings[0]


def test_one_bad_operation_does_not_block_the_good_ones() -> None:
    result, warnings = apply_operations(
        board(),
        [
            MoveCard(op="move_card", card_id="ghost", column_id="c2"),
            RenameColumn(op="rename_column", column_id="c1", title="Inbox"),
        ],
    )

    assert len(warnings) == 1
    assert result.columns[0].title == "Inbox"


def test_deleting_an_unknown_card_is_reported_not_applied() -> None:
    result, warnings = apply_operations(
        board(), [DeleteCard(op="delete_card", card_id="ghost")]
    )

    assert result == board()
    assert "ghost" in warnings[0]


def test_the_result_always_satisfies_the_board_invariants() -> None:
    result, _ = apply_operations(
        board(),
        [
            MoveCard(op="move_card", card_id="k1", column_id="c2"),
            MoveCard(op="move_card", card_id="k1", column_id="c1"),
            DeleteCard(op="delete_card", card_id="k2"),
            CreateCard(op="create_card", column_id="c1", title="Fresh", details="d"),
        ],
    )

    # Re-validating is the point: a board that came out of apply_operations must still
    # be a legal board.
    BoardData.model_validate(result.model_dump(by_alias=True))
    assert result.columns[0].card_ids.count("k1") == 1


# ---------------------------------------------------------------- parsing


def test_chat_response_parses_each_operation_type() -> None:
    parsed = ChatResponse.model_validate(
        {
            "reply": "done",
            "operations": [
                {"op": "create_card", "column_id": "c1", "title": "t", "details": "d"},
                {"op": "move_card", "card_id": "k1", "column_id": "c2"},
                {"op": "update_card", "card_id": "k2", "title": "t2", "details": "d2"},
                {"op": "delete_card", "card_id": "k3"},
                {"op": "rename_column", "column_id": "c1", "title": "Inbox"},
            ],
        }
    )

    assert [type(o).__name__ for o in parsed.operations] == [
        "CreateCard",
        "MoveCard",
        "UpdateCard",
        "DeleteCard",
        "RenameColumn",
    ]


def test_chat_response_rejects_an_unknown_operation() -> None:
    with pytest.raises(ValueError):
        ChatResponse.model_validate(
            {"reply": "x", "operations": [{"op": "destroy_everything"}]}
        )


@pytest.mark.parametrize("key", ["op", "action", "operation", "type", "kind"])
def test_normalise_reply_finds_the_operation_whichever_key_names_it(key: str) -> None:
    from app.ops import normalise_reply

    payload = {
        "reply": "ok",
        "operations": [
            {key: "create_card", "column_id": "c1", "title": "t", "details": "d"}
        ],
    }

    normalised = normalise_reply(payload)

    assert normalised["operations"][0]["op"] == "create_card"
    assert ChatResponse.model_validate(normalised).operations[0].op == "create_card"


def test_normalise_reply_leaves_a_correct_reply_alone() -> None:
    from app.ops import normalise_reply

    payload = {"reply": "ok", "operations": [{"op": "delete_card", "card_id": "k1"}]}

    assert normalise_reply(payload) == payload


def test_normalise_reply_ignores_a_data_field_that_looks_like_an_operation() -> None:
    from app.ops import normalise_reply

    # A card genuinely titled "create_card" must not be mistaken for the discriminator.
    payload = {
        "reply": "ok",
        "operations": [
            {"title": "create_card", "column_id": "c1", "details": "d"}
        ],
    }

    assert normalise_reply(payload) == payload


def test_normalise_reply_leaves_an_ambiguous_reply_alone() -> None:
    from app.ops import normalise_reply

    payload = {
        "reply": "ok",
        "operations": [
            {"action": "delete_card", "kind": "create_card", "card_id": "k1"}
        ],
    }

    assert normalise_reply(payload) == payload


def test_normalise_reply_tolerates_junk_without_raising() -> None:
    from app.ops import normalise_reply

    assert normalise_reply({"reply": "x"}) == {"reply": "x"}
    assert normalise_reply({"operations": "not a list"})["operations"] == "not a list"
    assert normalise_reply({"operations": ["a string"]})["operations"] == ["a string"]
    assert normalise_reply({"operations": [None]})["operations"] == [None]


def test_normalise_reply_handles_several_operations_at_once() -> None:
    from app.ops import normalise_reply

    payload = {
        "reply": "ok",
        "operations": [
            {"action": "create_card", "column_id": "c1", "title": "t", "details": "d"},
            {"op": "delete_card", "card_id": "k1"},
        ],
    }

    normalised = normalise_reply(payload)

    assert [o["op"] for o in normalised["operations"]] == [
        "create_card",
        "delete_card",
    ]


def test_chat_response_accepts_no_operations() -> None:
    parsed = ChatResponse.model_validate({"reply": "Paris.", "operations": []})

    assert parsed.operations == []
