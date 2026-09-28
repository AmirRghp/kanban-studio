import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.ai import AiClient, ChatMessage
from app.db import load_board_with_revision, update_board
from app.models import BoardData
from app.ops import (
    CHAT_RESPONSE_SCHEMA,
    ChatResponse,
    apply_operations,
    normalise_reply,
)

logger = logging.getLogger(__name__)

# The browser trims to this as well. Bounded so the prompt cannot grow without limit.
HISTORY_LIMIT = 20

# Raw model replies are logged when they fail validation, for diagnosability. They can
# echo prompt content, so they are truncated rather than written whole to the logs.
RAW_REPLY_LOG_LIMIT = 400

SYSTEM_RULES = """\
- Use ONLY the column ids and card ids listed above, copied exactly. Never invent an id.
- create_card: column_id, title, details. This adds a new card.
- move_card: card_id and the column_id to move it to. This moves an existing card and
  creates nothing.
- update_card: card_id, title, details. This edits a card where it already is.
- delete_card: card_id.
- rename_column: column_id, title.
- If the request needs no board change, return an empty operations list.
- Put a short human reply in `reply`, in the user's own language."""


@dataclass
class ChatResult:
    reply: str
    board: BoardData
    warnings: list[str] = field(default_factory=list)
    revision: int = 0


def build_messages(
    board: BoardData, message: str, history: list[ChatMessage]
) -> list[dict[str, str]]:
    """The board, the valid ids, the recent conversation, then the new message.

    The system prompt embeds the whole board JSON, so prompt size scales with board
    size; only history is bounded (HISTORY_LIMIT). If boards ever grow enough for that
    to matter, cap or summarise the embedded board here.
    """
    columns = {column.id: column.title for column in board.columns}
    system = (
        "You edit a Kanban board for the user. Reply with structured output only.\n\n"
        f"Current board:\n{board.model_dump_json(by_alias=True)}\n\n"
        f"Valid column ids and titles: {json.dumps(columns)}\n"
        f"Valid card ids: {json.dumps(list(board.cards))}\n\n"
        f"{SYSTEM_RULES}"
    )

    trimmed = history[-HISTORY_LIMIT:]
    # History arrives as ChatMessage models from the API; tests pass plain dicts. Both
    # carry the same two keys.
    history_dicts = [
        m.model_dump() if isinstance(m, ChatMessage) else dict(m) for m in trimmed
    ]
    return [
        {"role": "system", "content": system},
        *history_dicts,
        {"role": "user", "content": message},
    ]


def run_chat(
    db_path: Path,
    username: str,
    board_id: int,
    message: str,
    history: list[ChatMessage],
    client: AiClient,
    expected_revision: int | None = None,
) -> ChatResult:
    """One turn: read the board, ask the model, apply what can be applied, store it.

    The model is asked what to change rather than being trusted to return the whole
    board, so a bad reply costs at most the operations that were skipped, never the
    cards that were already there.
    """
    # The prompt is built from a snapshot read. The change is then applied inside
    # update_board's own transaction, which re-reads the board. With expected_revision
    # set, a board change made between the snapshot and the apply raises
    # RevisionConflict (surfaced as 409) instead of being merged away silently.
    loaded = load_board_with_revision(db_path, username, board_id)
    if loaded is None:
        raise LookupError(f"no board {board_id} for user {username!r}")
    current, snapshot_revision = loaded

    reply = client.complete_json(
        build_messages(current, message, history),
        CHAT_RESPONSE_SCHEMA,
        "chat_response",
    )

    try:
        parsed = ChatResponse.model_validate(normalise_reply(reply))
    except ValueError as exc:
        # Logged so a malformed reply is diagnosable. Truncated; never the API key.
        reply_text = json.dumps(reply) if isinstance(reply, dict) else str(reply)
        logger.warning(
            "Chat reply did not validate: %s. Raw reply: %s",
            exc,
            reply_text[:RAW_REPLY_LOG_LIMIT],
        )
        return ChatResult(
            reply=str(reply.get("reply", "")) or "I could not understand that request.",
            board=current,
            warnings=["The reply could not be read as a set of board changes."],
            revision=snapshot_revision,
        )

    warnings: list[str] = []

    def change(board: BoardData) -> BoardData:
        new_board, skipped = apply_operations(board, parsed.operations)
        warnings.extend(skipped)
        return new_board

    updated, new_revision = update_board(
        db_path, username, board_id, change, expected_revision=expected_revision
    )
    return ChatResult(
        reply=parsed.reply, board=updated, warnings=warnings, revision=new_revision
    )
