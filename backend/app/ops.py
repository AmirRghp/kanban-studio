import uuid
from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.models import BoardData, Card


class CreateCard(BaseModel):
    op: Literal["create_card"]
    column_id: str
    title: str
    details: str
    due_date: date | None = None
    labels: list[str] = Field(default_factory=list)


class MoveCard(BaseModel):
    op: Literal["move_card"]
    card_id: str
    column_id: str


class UpdateCard(BaseModel):
    op: Literal["update_card"]
    card_id: str
    title: str
    details: str
    due_date: date | None = None
    labels: list[str] = Field(default_factory=list)

    # update_card replaces the card, so an omitted due_date/labels would wipe the
    # existing ones. `_update_card` reads `model_fields_set` to tell "absent" from
    # "explicitly null": absent keeps what is there, an explicit value sets it. There is
    # no companion boolean field, because nothing would ever set it and the model would
    # have to be trusted to do so.

    @field_validator("labels", mode="before")
    @classmethod
    def _strip_labels(cls, value: object) -> object:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        return value


class DeleteCard(BaseModel):
    op: Literal["delete_card"]
    card_id: str


class RenameColumn(BaseModel):
    op: Literal["rename_column"]
    column_id: str
    title: str


Operation = Annotated[
    Union[CreateCard, MoveCard, UpdateCard, DeleteCard, RenameColumn],
    Field(discriminator="op"),
]


class ChatResponse(BaseModel):
    """What the model is asked to return."""

    reply: str
    operations: list[Operation]


# Sent to the model as the structured-output schema. Derived from the models above so
# the wire contract and the parser cannot drift apart.
CHAT_RESPONSE_SCHEMA = ChatResponse.model_json_schema()


# The operation names the model is allowed to use.
OP_NAMES = frozenset(
    {"create_card", "move_card", "update_card", "delete_card", "rename_column"}
)
# Fields that carry card data rather than naming the operation.
_OPERATION_FIELDS = frozenset({"column_id", "card_id", "title", "details"})


def normalise_reply(payload: dict) -> dict:
    """Recover the `op` discriminator when the model names that field differently.

    Measured against the live model `stealth/space-bunny-alpha`: it returns correct,
    fully schema-shaped replies, but names the discriminator key differently on
    different calls. Observed `op`, `action`, and `operation` for the same request.
    Every other field, including all ids, was correct every time.

    So rather than guess at a list of synonyms, the operation is identified by its
    value, which is always one of the five known names. A reply is only rewritten when
    exactly one non-data field holds a known name, so an ambiguous or unrecognisable
    reply is left alone and still fails validation loudly.
    """
    operations = payload.get("operations")
    if not isinstance(operations, list):
        return payload

    return {**payload, "operations": [_with_op(o) for o in operations]}


def _with_op(operation: object) -> object:
    if not isinstance(operation, dict) or "op" in operation:
        return operation

    candidates = [
        key
        for key, value in operation.items()
        if key not in _OPERATION_FIELDS
        and isinstance(value, str)
        and value in OP_NAMES
    ]
    if len(candidates) != 1:
        return operation

    key = candidates[0]
    return {**operation, "op": operation[key]}


def new_card_id() -> str:
    return f"card-{uuid.uuid4().hex[:12]}"


def apply_operations(
    board: BoardData, operations: list[Operation]
) -> tuple[BoardData, list[str]]:
    """Apply operations in order, collecting a warning for each one that cannot apply.

    Never raises for a bad operation. The model is a free fine-tune and, measured over
    live probes, returns an unusable operation roughly one time in twelve, so the
    contract is that anything invalid is skipped and reported rather than trusted.
    """
    warnings: list[str] = []
    for operation in operations:
        try:
            board = _apply(board, operation)
        except ValueError as exc:
            warnings.append(str(exc))
    return board, warnings


def _apply(board: BoardData, operation: Operation) -> BoardData:
    if isinstance(operation, CreateCard):
        return _create_card(board, operation)
    if isinstance(operation, MoveCard):
        return _move_card(board, operation)
    if isinstance(operation, UpdateCard):
        return _update_card(board, operation)
    if isinstance(operation, DeleteCard):
        return _delete_card(board, operation)
    return _rename_column(board, operation)


def _column_index(board: BoardData, column_id: str) -> int:
    for index, column in enumerate(board.columns):
        if column.id == column_id:
            return index
    raise ValueError(f"skipped: no column with id {column_id!r}")


def _card_or_skip(board: BoardData, card_id: str) -> Card:
    card = board.cards.get(card_id)
    if card is None:
        raise ValueError(f"skipped: no card with id {card_id!r}")
    return card


def _create_card(board: BoardData, operation: CreateCard) -> BoardData:
    index = _column_index(board, operation.column_id)
    # The server owns the id. The model never chooses one.
    card_id = new_card_id()
    card = Card(
        id=card_id,
        title=operation.title,
        details=operation.details,
        due_date=operation.due_date,
        labels=operation.labels,
    )

    columns = list(board.columns)
    columns[index] = columns[index].model_copy(
        update={"card_ids": [*columns[index].card_ids, card_id]}
    )
    return BoardData(columns=columns, cards={**board.cards, card_id: card})


def _move_card(board: BoardData, operation: MoveCard) -> BoardData:
    _card_or_skip(board, operation.card_id)
    target = _column_index(board, operation.column_id)

    # Remove the card from wherever it is, and append it to the target, in one pass.
    columns = []
    for index, column in enumerate(board.columns):
        card_ids = [c for c in column.card_ids if c != operation.card_id]
        if index == target:
            card_ids = [*card_ids, operation.card_id]
        columns.append(column.model_copy(update={"card_ids": card_ids}))

    return BoardData(columns=columns, cards=dict(board.cards))


def _update_card(board: BoardData, operation: UpdateCard) -> BoardData:
    card = _card_or_skip(board, operation.card_id)
    update: dict[str, object] = {
        "title": operation.title,
        "details": operation.details,
    }
    # Only touch a field the reply actually mentioned. `model_fields_set` records the
    # keys the model supplied, so an explicit null still counts as "set it to nothing",
    # which is how a due date gets cleared.
    provided = operation.model_fields_set
    if "due_date" in provided:
        update["due_date"] = operation.due_date
    if "labels" in provided:
        update["labels"] = operation.labels
    updated = card.model_copy(update=update)
    return BoardData(
        columns=list(board.columns),
        cards={**board.cards, operation.card_id: updated},
    )


def _delete_card(board: BoardData, operation: DeleteCard) -> BoardData:
    _card_or_skip(board, operation.card_id)
    cards = {k: v for k, v in board.cards.items() if k != operation.card_id}
    columns = [
        column.model_copy(
            update={
                "card_ids": [c for c in column.card_ids if c != operation.card_id]
            }
        )
        for column in board.columns
    ]
    return BoardData(columns=columns, cards=cards)


def _rename_column(board: BoardData, operation: RenameColumn) -> BoardData:
    index = _column_index(board, operation.column_id)
    columns = list(board.columns)
    columns[index] = columns[index].model_copy(update={"title": operation.title})
    return BoardData(columns=columns, cards=dict(board.cards))
