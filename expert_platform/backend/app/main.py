from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.pdf_learning_assistant import ALL_KNOWLEDGE_BASES, ROOT_DIR
from .admin_deletion import AdminDeleteError, DeleteTarget

from .admin import AdminService
from .config import Settings, default_settings
from .schemas import (
    AdminDeleteExecute,
    AdminDeleteTarget,
    ChatRequest,
    ConfirmedDelete,
    Credentials,
    ExpertCreate,
)
from .services import AssistantService, LoginRateLimiter, SessionService

logger = logging.getLogger(__name__)


def _user_payload(user: dict[str, str], *, is_admin: bool = False) -> dict[str, Any]:
    return {
        "id": user["user_id"],
        "username": user["username"],
        "vipLevel": "VIP1",
        "balance": 0,
        "isAdmin": is_admin,
    }


def _safe_error(error: Exception, fallback: str) -> HTTPException:
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=503, detail=fallback)


def create_app(
    settings: Settings | None = None,
    *,
    assistant_factory=None,
    admin_qdrant=None,
) -> FastAPI:
    load_dotenv(ROOT_DIR / ".env")
    settings = settings or default_settings()
    sessions = SessionService(settings)
    assistants = AssistantService(settings, assistant_factory)
    admin = AdminService(settings, assistants, sessions, admin_qdrant)
    login_limiter = LoginRateLimiter(
        settings.login_attempt_limit,
        settings.login_attempt_window_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.temporary_root.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(
        title="Intelligent Expert Platform API",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "object-src 'none'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'"
        )
        if request.url.path.startswith(("/api/auth", "/api/admin")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_user(
        expert_session: str | None = Cookie(default=None),
    ) -> dict[str, str]:
        user = sessions.resolve(expert_session)
        if not user:
            raise HTTPException(status_code=401, detail="请先登录。")
        return user

    def current_assistant(
        user: dict[str, str] = Depends(current_user),
        expert_session: str | None = Cookie(default=None),
    ):
        try:
            if expert_session is None:
                raise ValueError("请先登录。")
            return assistants.get(expert_session, user["user_id"])
        except Exception as error:
            raise _safe_error(error, "专家资源暂不可用，请检查本地服务与模型配置。") from error

    def current_admin(
        user: dict[str, str] = Depends(current_user),
    ) -> dict[str, str]:
        if not sessions.is_admin(user):
            raise HTTPException(status_code=403, detail="当前账号没有后台管理权限。")
        return user

    def require_same_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        request_origin = f"{request.url.scheme}://{host}" if host else ""
        if not origin or origin not in {*settings.allowed_origins, request_origin}:
            raise HTTPException(status_code=403, detail="管理操作的请求来源无效。")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.3.0"}

    @app.post("/api/auth/register", status_code=201)
    def register(payload: Credentials) -> dict[str, Any]:
        try:
            user = sessions.users.register(payload.username, payload.password)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"user": _user_payload(user, is_admin=sessions.is_admin(user))}

    @app.post("/api/auth/login")
    def login(
        payload: Credentials,
        request: Request,
        response: Response,
        expert_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        client_host = request.client.host if request.client else "unknown"
        rate_key = f"{client_host}:{payload.username.strip().casefold()}"
        retry_after = login_limiter.retry_after(rate_key)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="登录尝试过于频繁，请稍后重试。",
                headers={"Retry-After": str(retry_after)},
            )
        try:
            user = sessions.users.authenticate(payload.username, payload.password)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if not user:
            login_limiter.fail(rate_key)
            raise HTTPException(status_code=401, detail="用户名或密码错误。")
        login_limiter.clear(rate_key)
        token = sessions.create(user["user_id"], replace_token=expert_session)
        assistants.discard(expert_session)
        response.set_cookie(
            settings.session_cookie,
            token,
            max_age=settings.session_days * 86_400,
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookie,
            path="/",
        )
        return {"user": _user_payload(user, is_admin=sessions.is_admin(user))}

    @app.post("/api/auth/logout", status_code=204, response_class=Response)
    def logout(
        response: Response,
        expert_session: str | None = Cookie(default=None),
    ) -> Response:
        sessions.delete(expert_session)
        assistants.discard(expert_session)
        response.delete_cookie(settings.session_cookie, path="/")
        response.status_code = 204
        return response

    @app.get("/api/auth/me")
    def me(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return {"user": _user_payload(user, is_admin=sessions.is_admin(user))}

    @app.get("/api/bootstrap")
    def bootstrap(
        user: dict[str, str] = Depends(current_user),
        assistant=Depends(current_assistant),
    ) -> dict[str, Any]:
        return {
            "user": _user_payload(user, is_admin=sessions.is_admin(user)),
            "experts": assistants.experts(assistant),
            "sessionId": assistant.session_id,
        }

    @app.get("/api/experts")
    def list_experts(assistant=Depends(current_assistant)) -> dict[str, Any]:
        return {"items": assistants.experts(assistant)}

    @app.post("/api/experts", status_code=201)
    def create_expert(
        payload: ExpertCreate,
        assistant=Depends(current_assistant),
    ) -> dict[str, Any]:
        try:
            item = assistant.create_knowledge_base(payload.name)
        except Exception as error:
            raise _safe_error(error, "创建专家失败，请稍后重试。") from error
        return {"item": {**item, "kind": "private", "deletable": True}}

    @app.delete("/api/experts/{expert_id}")
    def delete_expert(
        expert_id: str,
        payload: ConfirmedDelete,
        assistant=Depends(current_assistant),
    ) -> dict[str, Any]:
        try:
            result = assistant.delete_knowledge_base(expert_id, confirmed=payload.confirmed)
        except Exception as error:
            raise _safe_error(error, "删除专家失败，请稍后重试。") from error
        return {
            "deletedExpertId": result["id"],
            "deletedDocuments": result["documents_deleted"],
        }

    @app.get("/api/documents")
    def list_documents(
        expert_id: str = Query(ALL_KNOWLEDGE_BASES),
        query: str = Query("", max_length=500),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
        assistant=Depends(current_assistant),
    ) -> dict[str, Any]:
        try:
            return assistants.documents(assistant, expert_id, query, limit, offset)
        except Exception as error:
            raise _safe_error(error, "读取文档失败，请稍后重试。") from error

    @app.post("/api/documents", status_code=201)
    async def upload_document(
        expert_id: str = Form(...),
        file: UploadFile = File(...),
        assistant=Depends(current_assistant),
    ) -> dict[str, Any]:
        if expert_id == ALL_KNOWLEDGE_BASES:
            raise HTTPException(status_code=400, detail="上传前请选择一位具体专家。")
        safe_name = Path(file.filename or "upload.bin").name.replace("\x00", "") or "upload.bin"
        settings.temporary_root.mkdir(parents=True, exist_ok=True)
        size = 0
        with TemporaryDirectory(dir=settings.temporary_root) as directory:
            temporary_path = Path(directory) / safe_name
            try:
                with temporary_path.open("wb") as temporary:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise HTTPException(status_code=413, detail="文件不能超过 50 MB。")
                        temporary.write(chunk)
                if size == 0:
                    raise HTTPException(status_code=400, detail="文件不能为空。")
                assistant.select_knowledge_base(expert_id)
                result = assistant.load_document(temporary_path, knowledge_base_id=expert_id)
                if not result.get("success"):
                    raise HTTPException(status_code=400, detail=str(result.get("message")))
                return {
                    "result": result,
                    **assistants.documents(assistant, expert_id, ""),
                }
            finally:
                await file.close()

    @app.delete("/api/documents/{document_id}", status_code=204)
    def delete_document(
        document_id: str,
        expert_id: str = Query(...),
        confirmed: bool = Query(False),
        assistant=Depends(current_assistant),
    ) -> Response:
        try:
            assistant.delete_document(
                document_id,
                knowledge_base_id=expert_id,
                confirmed=confirmed,
            )
        except Exception as error:
            raise _safe_error(error, "删除文档失败，请稍后重试。") from error
        return Response(status_code=204)

    @app.get("/api/chat/history")
    def chat_history(assistant=Depends(current_assistant)) -> dict[str, Any]:
        return {"items": assistants.history(assistant)}

    @app.post("/api/chat")
    def chat(payload: ChatRequest, assistant=Depends(current_assistant)) -> dict[str, Any]:
        if payload.expert_id == ALL_KNOWLEDGE_BASES:
            raise HTTPException(status_code=400, detail="问答时请选择一位具体专家。")
        try:
            assistant.select_knowledge_base(payload.expert_id)
            expert_name = assistants._expert_name(assistant, payload.expert_id)
            answer = assistant.ask(
                payload.question,
                knowledge_base_id=payload.expert_id,
                use_advanced_search=payload.advanced,
            )
            turn = assistant.conversations[-1]
        except Exception as error:
            logger.error("Chat request failed: %s", type(error).__name__)
            raise _safe_error(error, "专家检索或回答暂不可用，请稍后重试。") from error
        return {
            "message": {
                "id": uuid4().hex,
                "role": "assistant",
                "content": answer,
                "expertId": payload.expert_id,
                "expertName": expert_name,
                "createdAt": turn["created_at"],
            }
        }

    @app.post("/api/reports/monthly")
    def report(assistant=Depends(current_assistant)) -> dict[str, Any]:
        try:
            report_payload = assistant.generate_monthly_personal_report(
                save_to_file=True
            )
            report_payload.pop("conversations", None)
            return {"report": report_payload}
        except Exception as error:
            raise _safe_error(error, "月度总结生成暂不可用，请稍后重试。") from error

    @app.get("/api/admin/overview")
    def admin_overview(_: dict[str, str] = Depends(current_admin)) -> dict[str, Any]:
        try:
            return admin.overview()
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="后台数据暂不可读取。") from error

    @app.get("/api/admin/users")
    def admin_users(
        query: str = Query("", max_length=128),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        _: dict[str, str] = Depends(current_admin),
    ) -> dict[str, Any]:
        return admin.users(query, limit, offset)

    @app.get("/api/admin/experts")
    def admin_experts(
        query: str = Query("", max_length=128),
        user_id: str = Query("", max_length=128),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        _: dict[str, str] = Depends(current_admin),
    ) -> dict[str, Any]:
        return admin.experts(query, user_id, limit, offset)

    @app.get("/api/admin/documents")
    def admin_documents(
        query: str = Query("", max_length=128),
        user_id: str = Query("", max_length=128),
        expert_id: str = Query("", max_length=128),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        _: dict[str, str] = Depends(current_admin),
    ) -> dict[str, Any]:
        return admin.documents(query, user_id, expert_id, limit, offset)

    @app.post("/api/admin/deletions/preview")
    def admin_delete_preview(
        payload: AdminDeleteTarget,
        _: None = Depends(require_same_origin),
        user: dict[str, str] = Depends(current_admin),
    ) -> dict[str, Any]:
        try:
            return admin.preview(
                DeleteTarget(
                    action=payload.action,
                    user_id=payload.user_id,
                    expert_id=payload.expert_id,
                    document_id=payload.document_id,
                ),
                actor_user_id=user["user_id"],
            )
        except AdminDeleteError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            logger.error("Admin deletion preview failed: %s", type(error).__name__)
            raise HTTPException(status_code=503, detail="无法完成删除预检，请检查 Qdrant 状态。") from error

    @app.post("/api/admin/deletions/execute")
    def admin_delete_execute(
        payload: AdminDeleteExecute,
        _: None = Depends(require_same_origin),
        user: dict[str, str] = Depends(current_admin),
    ) -> dict[str, Any]:
        try:
            return admin.execute(
                DeleteTarget(
                    action=payload.action,
                    user_id=payload.user_id,
                    expert_id=payload.expert_id,
                    document_id=payload.document_id,
                ),
                confirmation=payload.confirmation,
                actor_user_id=user["user_id"],
                actor_username=user["username"],
            )
        except AdminDeleteError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            logger.error("Admin deletion failed: %s", type(error).__name__)
            raise HTTPException(status_code=503, detail="删除失败，未报告成功。") from error

    app.state.settings = settings
    app.state.sessions = sessions
    app.state.assistants = assistants
    app.state.admin = admin

    if settings.frontend_dist.is_dir():
        assets = settings.frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str, request: Request) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API 路由不存在。")
            candidate = (settings.frontend_dist / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(settings.frontend_dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(settings.frontend_dist / "index.html")

    return app


app = create_app()
