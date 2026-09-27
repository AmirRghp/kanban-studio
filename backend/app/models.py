from pydantic import BaseModel, ConfigDict, Field, model_validator

# The JSON contract must match frontend/src/lib/kanban.ts field for field, so the wire
# format stays camelCase (`cardIds`) while the Python attributes stay snake_case.
# serialize_by_alias makes model_dump() emit the alias by default, so no call site has
# to remember by_alias=True.
_CONFIG = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class Card(BaseModel):
    id: str
    title: str
    details: str


class Column(BaseModel):
    model_config = _CONFIG

    id: str
    title: str
    card_ids: list[str] = Field(alias="cardIds")


class BoardData(BaseModel):
    model_config = _CONFIG

    columns: list[Column]
    cards: dict[str, Card]

    @model_validator(mode="after")
    def check_references(self) -> "BoardData":
        for key, card in self.cards.items():
            if key != card.id:
                raise ValueError(
                    f"cards key {key!r} does not match the card's own id {card.id!r}"
                )

        for column in self.columns:
            unknown = [cid for cid in column.card_ids if cid not in self.cards]
            if unknown:
                raise ValueError(
                    f"column {column.id!r} references unknown cards: {unknown}"
                )

        # A card may appear in exactly one column. Appearing in two makes it render
        # twice, and dragging one copy moves only that copy, leaving the board
        # inconsistent. A client that appends without removing is enough to cause it.
        placed: set[str] = set()
        duplicated: list[str] = []
        for column in self.columns:
            for card_id in column.card_ids:
                if card_id in placed:
                    duplicated.append(card_id)
                placed.add(card_id)
        if duplicated:
            raise ValueError(f"cards appear in more than one place: {duplicated}")

        return self
