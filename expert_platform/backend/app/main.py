from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, default_settings
from .schemas import ChatRequest, Credentials, ExpertCreate, NoteCreate
from .services import ConversationService, ExpertService, SessionService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings()
    sessions = SessionService(settings)
    experts = ExpertService(settings)
    conversations = ConversationService(settings, experts)
    app = FastAPI(title="Intelligent Expert Platform API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def current_user(expert_session: str | None = Cookie(default=None)) -> dict:
        user = sessions.resolve(expert_session)
        if not user:
            raise HTTPException(status_code=401, detail="请先登录")
        return user

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/auth/register", status_code=201)
    def register(payload: Credentials) -> dict:
        try:
            user = sessions.users.register(payload.username, payload.password)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"id": user["user_id"], "username": user["username"]}

    @app.post("/api/auth/login")
    def login(payload: Credentials, response: Response) -> dict:
        user = sessions.users.authenticate(payload.username, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = sessions.create(user["user_id"])
        response.set_cookie(
            settings.session_cookie,
            token,
            max_age=settings.session_days * 86400,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return {"id": user["user_id"], "username": user["username"], "vip": "VIP1", "balance": 0}

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response, expert_session: str | None = Cookie(default=None)) -> Response:
        sessions.delete(expert_session)
        response.delete_cookie(settings.session_cookie, path="/")
        return response

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return {"id": user["user_id"], "username": user["username"], "vip": "VIP1", "balance": 0}

    @app.get("/api/experts")
    def list_experts(user: dict = Depends(current_user)) -> dict:
        return {"items": experts.list_experts(user["user_id"])}

    @app.post("/api/experts", status_code=201)
    def create_expert(payload: ExpertCreate, user: dict = Depends(current_user)) -> dict:
        try:
            return experts.create_expert(user["user_id"], payload.name)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/api/experts/{expert_id}")
    def delete_expert(expert_id: str, user: dict = Depends(current_user)) -> dict:
        try:
            count = experts.delete_expert(user["user_id"], expert_id)
            return {"deletedDocuments": count}
        except (ValueError, PermissionError) as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/documents")
    def list_documents(
        expert_id: str = Query("all"),
        search: str = Query(""),
        user: dict = Depends(current_user),
    ) -> dict:
        try:
            items = experts.list_documents(user["user_id"], expert_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        needle = search.strip().casefold()
        if needle:
            items = [item for item in items if needle in item["fileName"].casefold()]
        return {"items": items}

    @app.post("/api/documents", status_code=201)
    async def upload_document(
        expert_id: str,
        file: UploadFile = File(...),
        user: dict = Depends(current_user),
    ) -> dict:
        suffix = Path(file.filename or "upload.bin").suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(await file.read())
            temporary_path = Path(temporary.name)
        try:
            return experts.upload_document(user["user_id"], expert_id, temporary_path, file.filename or "upload.bin")
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, LookupError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=503, detail=f"文件解析或索引失败：{type(error).__name__}") from error
        finally:
            temporary_path.unlink(missing_ok=True)

    @app.delete("/api/documents/{expert_id}/{document_id:path}", status_code=204)
    def delete_document(expert_id: str, document_id: str, user: dict = Depends(current_user)) -> Response:
        try:
            experts.delete_document(user["user_id"], expert_id, document_id)
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return Response(status_code=204)

    @app.get("/api/chat/history")
    def chat_history(session_key: str, user: dict = Depends(current_user)) -> dict:
        return {"items": conversations.history(user["user_id"], session_key)}

    @app.post("/api/chat")
    def chat(payload: ChatRequest, session_key: str, user: dict = Depends(current_user)) -> dict:
        try:
            return conversations.answer(
                user["user_id"], session_key, payload.expert_id, payload.question, payload.advanced
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=503, detail=f"专家检索暂不可用：{type(error).__name__}") from error

    @app.get("/api/stats")
    def stats(session_key: str, user: dict = Depends(current_user)) -> dict:
        messages = conversations.history(user["user_id"], session_key)
        return {
            "questions": sum(item["role"] == "user" for item in messages),
            "answers": sum(item["role"] == "assistant" for item in messages),
            "experts": len({item["expertId"] for item in messages}),
        }

    @app.post("/api/reports/session")
    def report(session_key: str, user: dict = Depends(current_user)) -> dict:
        return conversations.report(user["user_id"], session_key)

    app.state.settings = settings
    app.state.sessions = sessions
    app.state.experts = experts
    return app


app = create_app()
