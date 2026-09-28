import pytest

from app.models import BoardData
from app.ops import (
    CHAT_RESPONSE_SCHEMA,
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


# ---------------------------------------------------------------- due dates and labels


def _operations_from_reply(operation: dict) -> list:
    """Parse one operation the way a real model reply is parsed.

    Constructing `UpdateCard` by hand would skip the step this whole section depends on:
    a due date or label list is only applied when the reply actually mentioned it, and
    that is decided by which keys the parsed model was given. `_update_card` reads
    `model_fields_set`, so a hand-built instance can set fields the model never asked to
    change, and can omit fields it did. Every test that depends on "absent means keep"
    must go through here.
    """
    return ChatResponse.model_validate({"reply": "ok", "operations": [operation]}).operations


def test_a_due_date_from_the_model_is_applied() -> None:
    # The regression test for the silent no-op: the operation carried a due date and a
    # label list, and both have to land on the card. This asserts through the parse path
    # on purpose, because that is the only path a real reply takes.
    result, warnings = apply_operations(
        board(),
        _operations_from_reply(
            {
                "op": "update_card",
                "card_id": "k1",
                "title": "Renamed",
                "details": "d1",
                "due_date": "2026-05-05",
                "labels": ["urgent"],
            }
        ),
    )

    assert warnings == []
    assert result.cards["k1"].title == "Renamed"
    assert result.cards["k1"].due_date is not None
    assert result.cards["k1"].due_date.isoformat() == "2026-05-05"
    assert result.cards["k1"].labels == ["urgent"]


def test_the_due_date_flags_are_not_part_of_the_wire_contract() -> None:
    # The old implementation carried `due_date_set` / `labels_set` booleans that nothing
    # ever set, so the model could never apply a due date. They must not creep back in as
    # fields, least of all ones the model is asked to fill.
    assert "due_date_set" not in CHAT_RESPONSE_SCHEMA["$defs"]["UpdateCard"]["properties"]
    assert "labels_set" not in CHAT_RESPONSE_SCHEMA["$defs"]["UpdateCard"]["properties"]


def test_create_card_can_set_a_due_date_and_labels() -> None:
    result, warnings = apply_operations(
        board(),
        [
            CreateCard(
                op="create_card",
                column_id="c1",
                title="Planned",
                details="d",
                due_date="2026-03-01",
                labels=["design", "urgent"],
            )
        ],
    )

    assert warnings == []
    created = next(card for card in result.cards.values() if card.title == "Planned")
    assert created.due_date is not None and created.due_date.isoformat() == "2026-03-01"
    assert created.labels == ["design", "urgent"]


def test_update_card_keeps_a_due_date_it_does_not_mention() -> None:
    start, _ = apply_operations(
        board(),
        [
            CreateCard(
                op="create_card",
                column_id="c1",
                title="Planned",
                details="d",
                due_date="2026-03-01",
                labels=["design"],
            )
        ],
    )
    created_id = next(k for k, v in start.cards.items() if v.title == "Planned")

    result, warnings = apply_operations(
        start,
        _operations_from_reply(
            {
                "op": "update_card",
                "card_id": created_id,
                "title": "New",
                "details": "x",
            }
        ),
    )

    assert warnings == []
    assert result.cards[created_id].due_date is not None
    assert result.cards[created_id].labels == ["design"]


def test_update_card_clears_a_due_date_only_when_asked() -> None:
    start, _ = apply_operations(
        board(),
        [
            CreateCard(
                op="create_card",
                column_id="c1",
                title="Planned",
                details="d",
                due_date="2026-03-01",
                labels=["design"],
            )
        ],
    )
    created_id = next(k for k, v in start.cards.items() if v.title == "Planned")

    # Built through the model's wire shape, not by hand: the due date is cleared by an
    # explicit null, which `model_fields_set` has to notice.
    cleared, _ = apply_operations(
        start,
        _operations_from_reply(
            {
                "op": "update_card",
                "card_id": created_id,
                "title": "New",
                "details": "x",
                "due_date": None,
                "labels": [],
            }
        ),
    )

    assert cleared.cards[created_id].due_date is None
    assert cleared.cards[created_id].labels == []


def test_update_card_strips_blank_labels_from_the_model() -> None:
    result, _ = apply_operations(
        board(),
        _operations_from_reply(
            {
                "op": "update_card",
                "card_id": "k1",
                "title": "One",
                "details": "d1",
                "labels": ["a", "", "  ", "b"],
            }
        ),
    )

    assert result.cards["k1"].labels == ["a", "b"]


def test_a_due_date_op_survives_the_chat_schema_round_trip() -> None:
    # The schema sent to the model is derived from these models, so an op carrying
    # planning fields must still validate against ChatResponse.
    reply = ChatResponse.model_validate(
        {
            "reply": "ok",
            "operations": [
                {
                    "op": "create_card",
                    "column_id": "c1",
                    "title": "T",
                    "details": "d",
                    "due_date": "2026-03-01",
                    "labels": ["a"],
                }
            ],
        }
    )

    op = reply.operations[0]
    assert op.due_date is not None and op.due_date.isoformat() == "2026-03-01"
    assert op.labels == ["a"]
