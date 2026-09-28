import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.ai import (
    PING_PROMPT,
    AiClient,
    AiNotConfigured,
    AiUnavailable,
    ChatRequest,
    get_ai_client,
)
from app.auth import (
    SESSION_COOKIE,
    LoginRequest,
    RegisterRequest,
    SessionUser,
    require_user,
    validate_registration,
)
from app.chat import run_chat
from app.config import get_settings
from app.db import (
    DEMO_PASSWORD,
    DEMO_USERNAME,
    EMPTY_BOARD,
    BoardNotFound,
    RevisionConflict,
    UserExists,
    check_credentials,
    create_board,
    create_user,
    delete_board,
    get_user_id,
    initialise,
    list_boards,
    load_board_with_revision,
    rename_board,
    save_board,
    update_board,
)
from app.models import BoardData

# The built frontend is copied here in the image. It does not exist in a bare checkout.
STATIC_DIR = Path(__file__).parent / "static"

# Matches the default in app/config.py. Surfaced as a startup warning by the lifespan.
INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"

# Revision of the board at read time, in an outgoing header.
REVISION_HEADER = "X-Board-Revision"

logger = logging.getLogger(__name__)


def _board_response(board: BoardData, revision: int) -> Response:
    response = Response(content=board.model_dump_json(), media_type="application/json")
    response.headers[REVISION_HEADER] = str(revision)
    return response


def create_app(
    static_dir: Path,
    db_path: Path,
    session_secret: str | None = None,
) -> FastAPI:
    effective_secret = session_secret or get_settings().session_secret

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Without this, the root logger stays at WARNING and app.logger.info calls,
        # such as the OpenRouter usage line, are silently dropped.
        logging.basicConfig(
            level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
        )
        if effective_secret == INSECURE_DEFAULT_SECRET:
            # Not fatal: this is a local-only MVP. Anyone reachable by others must set
            # SESSION_SECRET, because the default is publicly known.
            logger.warning(
                "SESSION_SECRET is unset or equals the known dev default; session "
                "cookies are forgeable by anyone who can reach this server. Set "
                "SESSION_SECRET in .env for anything not strictly local."
            )
        # Creates the database, migrates old schemas, and seeds the demo user.
        initialise(db_path)
        yield

    app = FastAPI(title="Project Management MVP", lifespan=lifespan)

    # Starlette signs the session cookie; the payload is readable but not forgeable.
    # https_only is off because the MVP is served over plain http on localhost.
    app.add_middleware(
        SessionMiddleware,
        secret_key=effective_secret,
        session_cookie=SESSION_COOKIE,
        same_site="lax",
        https_only=False,
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def _sign_in(request: Request, username: str) -> SessionUser:
        # SessionMiddleware writes the signed cookie, so do not set one by hand.
        request.session["username"] = username
        return SessionUser(username=username)

    @app.post("/api/register")
    def register(credentials: RegisterRequest, request: Request) -> SessionUser:
        problem = validate_registration(credentials.username, credentials.password)
        if problem:
            raise HTTPException(status_code=422, detail=problem)
        try:
            user_id = create_user(db_path, credentials.username, credentials.password)
        except UserExists as exc:
            raise HTTPException(
                status_code=409, detail="That username is already taken."
            ) from exc
        # A new account starts with one clean board rather than an empty workspace.
        create_board(db_path, user_id, "First board", EMPTY_BOARD)
        return _sign_in(request, credentials.username)

    @app.post("/api/login")
    def login(credentials: LoginRequest, request: Request) -> SessionUser:
        if not check_credentials(db_path, credentials.username, credentials.password):
            raise HTTPException(
                status_code=401, detail="Invalid username or password"
            )
        return _sign_in(request, credentials.username)

    @app.post("/api/logout")
    def logout(request: Request, response: Response) -> dict[str, bool]:
        request.session.clear()
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: Annotated[SessionUser, Depends(require_user)]) -> SessionUser:
        return user

    @app.get("/api/boards")
    def boards(user: Annotated[SessionUser, Depends(require_user)]) -> list[dict]:
        return list_boards(db_path, user.username)

    @app.post("/api/boards", status_code=201)
    def create_a_board(
        body: dict[str, str], user: Annotated[SessionUser, Depends(require_user)]
    ) -> dict:
        name = body.get("name", "").strip() or "Untitled board"
        user_id = get_user_id(db_path, user.username)
        assert user_id is not None  # the session names an existing user
        board_id = create_board(db_path, user_id, name, EMPTY_BOARD)
        return {"id": board_id, "name": name, "cardCount": 0}

    @app.put("/api/boards/{board_id}")
    def rename_a_board(
        board_id: int,
        body: dict[str, str],
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> dict[str, str]:
        name = body.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Board name cannot be empty.")
        try:
            rename_board(db_path, user.username, board_id, name)
        except BoardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"name": name}

    @app.delete("/api/boards/{board_id}")
    def delete_a_board(
        board_id: int, user: Annotated[SessionUser, Depends(require_user)]
    ) -> dict[str, bool]:
        try:
            delete_board(db_path, user.username, board_id)
        except BoardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

    # The board data routes are sync defs, not async defs, so Starlette runs the
    # blocking sqlite calls in a threadpool instead of stalling the event loop.
    @app.get("/api/boards/{board_id}/board")
    def get_board(
        board_id: int,
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> Response:
        loaded = load_board_with_revision(db_path, user.username, board_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail="No such board")
        board, revision = loaded
        return _board_response(board, revision)

    @app.put("/api/boards/{board_id}/board")
    def put_board(
        board_id: int,
        board: BoardData,
        request: Request,
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> Response:
        # A board failing validation never reaches this point, so a malformed payload
        # returns 422 and cannot overwrite what is stored.
        expected = _expected_revision(request)
        try:
            save_board(
                db_path, user.username, board_id, board, expected_revision=expected
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except BoardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        current = load_board_with_revision(db_path, user.username, board_id)
        assert current is not None  # we just wrote it
        updated, revision = current
        return _board_response(updated, revision)

    # Legacy aliases for the pre-multi-board routes: the user's first board. They keep
    # any client that predates Part 11 working, and the seeded demo board is always
    # that user's first board.
    def _first_board_id(username: str) -> int:
        user_id = get_user_id(db_path, username)
        assert user_id is not None
        owned = list_boards(db_path, username)
        if not owned:
            raise HTTPException(status_code=404, detail="No board for this user")
        return owned[0]["id"]

    @app.get("/api/board", include_in_schema=False)
    def get_board_legacy(
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> Response:
        return get_board(_first_board_id(user.username), user)

    @app.put("/api/board", include_in_schema=False)
    def put_board_legacy(
        board: BoardData,
        request: Request,
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> Response:
        return put_board(_first_board_id(user.username), board, request, user)

    @app.post("/api/chat", response_model=None)
    def chat(
        req: Request,
        body: ChatRequest,
        client: Annotated[AiClient, Depends(get_ai_client)],
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> Response:
        try:
            result = run_chat(
                db_path,
                user.username,
                body.board_id,
                body.message,
                body.history,
                client,
                expected_revision=_expected_revision(req),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except AiNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AiUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        payload = {
            "reply": result.reply,
            "board": result.board.model_dump(by_alias=True),
            "warnings": result.warnings,
        }
        response = JSONResponse(content=payload)
        response.headers[REVISION_HEADER] = str(result.revision)
        return response

    @app.get("/api/ai/ping")
    def ai_ping(
        client: Annotated[AiClient, Depends(get_ai_client)],
        _: Annotated[SessionUser, Depends(require_user)],
    ) -> dict[str, str]:
        try:
            answer = client.complete([{"role": "user", "content": PING_PROMPT}])
        except AiNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AiUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"answer": answer, "model": client.model}

    @app.get("/api/{rest:path}", include_in_schema=False)
    def unknown_api_route(rest: str) -> None:
        raise HTTPException(status_code=404, detail="Not Found")

    # check_dir=False so the app can be created before the frontend has been built.
    app.mount(
        "/_next",
        StaticFiles(directory=static_dir / "_next", check_dir=False),
        name="next",
    )

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def serve_static(full_path: str) -> FileResponse | PlainTextResponse:
        index = static_dir / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                "The frontend has not been built. Use ./scripts/start.sh, "
                "which builds it inside the image.",
                status_code=503,
            )

        # resolve() collapses ../ segments, so an escape attempt lands outside the
        # static dir and the is_relative_to check routes it to the SPA index, exactly
        # as before. Only paths that resolve INSIDE the static dir can 404 below.
        candidate = (static_dir / full_path).resolve()
        inside = candidate.is_relative_to(static_dir.resolve())

        if inside and full_path:
            if candidate.is_file():
                return FileResponse(candidate)
            # A directory-shaped path is also an SPA route, not a file miss.
            if candidate.is_dir():
                return FileResponse(index)
            if "." in candidate.name:
                # File-shaped (has an extension) but not on disk: a stale asset or a
                # typo, not a route. Serving index.html here would mask the miss.
                return PlainTextResponse("Not Found", status_code=404)

        return FileResponse(index)

    return app


def _expected_revision(request: Request) -> int | None:
    """The client's read revision from If-Match, or None when the client omits it.

    Omitting it keeps older clients working; the frontend always sends it.
    """
    header = request.headers.get("if-match")
    if not header:
        return None
    value = header.strip().strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Malformed If-Match header: {header!r}"
        ) from exc


app = create_app(STATIC_DIR, Path(get_settings().database_path))
