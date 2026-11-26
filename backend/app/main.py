from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import PROJECT_NAME
from app.services.digest_gate import GateError
from app.routers import (
    apps,
    audit,
    dashboard,
    environments,
    health,
    promote,
    reconcile,
    releases,
    rollback,
    settings,
    windows,
)
from app.seed import seed_if_empty

seed_if_empty()

app = FastAPI(title=PROJECT_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(GateError)
async def gate_error_handler(request: Request, exc: GateError):
    # detail 保持为中文字符串（旧前端/夹具直接读 detail），
    # 同时在顶层给稳定机器码 code/错误码与附加现状，供并发重放与分夹具断言。
    content = {
        "ok": False,
        "code": exc.code,
        "错误码": exc.code,
        "detail": exc.message,
        "明细": exc.message,
    }
    content.update(exc.extra or {})
    return JSONResponse(status_code=exc.status_code, content=content)

for mod in (
    dashboard,
    apps,
    environments,
    releases,
    promote,
    windows,
    rollback,
    health,
    reconcile,
    settings,
    audit,
):
    app.include_router(mod.router, prefix="/api")


@app.get("/api/健康")
def health_check():
    return {"产品": PROJECT_NAME, "状态": "正常"}
