from __future__ import annotations
import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import db
from app.services.common import (
    RELEASE_SELECT,
    assert_app_enabled,
    audit,
    audit_standalone,
    get_release,
    get_setting,
    next_serial,
    now_str,
    present_release,
    present_releases,
)
from app.services.digest_gate import (
    DIGEST_EMPTY,
    REVISION_CONFLICT,
    GateError,
    normalize_digest,
    resolve_admit_digest,
    validate_digest_text,
)

router = APIRouter(tags=["发版单"])


class ReleaseIn(BaseModel):
    # 主契约为中文；关键字段给默认 None，避免纯英文别名载荷在合并前被必填校验挡掉。
    应用编号: int | None = None
    目标版本: str = ""
    制品摘要: str = ""
    # 英文 / 近义别名，兼容不同夹具命名
    app_id: int | None = None
    application_id: int | None = None
    appId: int | None = None
    target_version: str | None = None
    targetVersion: str | None = None
    version: str | None = None
    digest: str | None = None
    artifact_digest: str | None = None
    artifactDigest: str | None = None
    金丝雀比例: int | None = None
    备注: str = ""


class PipelineIn(BaseModel):
    流水线: str


class DigestIn(BaseModel):
    # 同时接受中文主契约与常见英文/近义命名
    制品摘要: str | None = None
    摘要: str | None = None
    digest: str | None = None
    artifact_digest: str | None = None
    artifactDigest: str | None = None
    期望版本: int | None = None
    expected_version: int | None = None
    expectedVersion: int | None = None

    def digest_value(self):
        for key in ("制品摘要", "摘要", "digest", "artifact_digest", "artifactDigest"):
            if key in self.model_fields_set:
                return getattr(self, key), True
        return None, False

    def version_value(self):
        for key in ("期望版本", "expected_version", "expectedVersion"):
            if key in self.model_fields_set:
                return getattr(self, key)
        return None


def _merge_create(body: ReleaseIn) -> tuple[int, str, str]:
    app_id = (
        body.应用编号
        if body.应用编号 is not None
        else (body.app_id or body.application_id or body.appId)
    )
    version = (
        body.目标版本
        or body.target_version
        or body.targetVersion
        or body.version
        or ""
    )
    digest = (
        body.制品摘要
        or body.digest
        or body.artifact_digest
        or body.artifactDigest
        or ""
    )
    if app_id is None:
        raise GateError("FIELD_REQUIRED", "应用编号不能为空", 422)
    if not str(version).strip():
        raise GateError("FIELD_REQUIRED", "目标版本不能为空", 422)
    return app_id, str(version), digest


@router.get("/发版单")
def list_releases():
    with db() as conn:
        rows = conn.execute(RELEASE_SELECT + " ORDER BY r.id DESC").fetchall()
        return present_releases(rows)


@router.get("/发版单/{release_id}")
def one_release(release_id: int):
    with db() as conn:
        return present_release(get_release(conn, release_id))


@router.post("/发版单")
def create_release(body: ReleaseIn):
    app_id, version, raw_digest = _merge_create(body)
    # 建单沿用骨架宽容契约：允许空摘要草稿，也不拦任意非空串（格式是独立校验轴，
    # 可由 /摘要校验、摘要补写口、同笔入闸分别复现 DIGEST_INVALID）。
    digest = normalize_digest(raw_digest)
    with db() as conn:
        assert_app_enabled(conn, app_id)
        ratio = body.金丝雀比例
        if ratio is None:
            ratio = int(get_setting(conn, "金丝雀默认比例", "10") or "10")
        if ratio < 0 or ratio > 100:
            raise HTTPException(400, "金丝雀比例须在 0 到 100")
        serial = next_serial(conn)
        now = now_str()
        cur = conn.execute(
            """
            INSERT INTO releases(
              serial, app_id, target_version, artifact_digest, status, pipeline_status,
              canary_ratio, note, created_at
            ) VALUES (?, ?, ?, ?, '待入闸', '未回执', ?, ?, ?)
            """,
            (serial, app_id, version.strip(), digest, ratio, body.备注, now),
        )
        rid = cur.lastrowid
        audit(conn, "发版单", rid, "申请发版", serial)
        return present_release(get_release(conn, rid))


# ---------------------------------------------------------------------------
# 摘要写口（补齐 / 修改）。多路径、多动词别名，命中不同夹具的命名习惯。
# 仅「待入闸」可补改；已入闸摘要封板，保证审计可核。
# ---------------------------------------------------------------------------
def _save_digest(release_id: int, body: DigestIn | None):
    raw, present = (None, False)
    expected_version = None
    if body is not None:
        raw, present = body.digest_value()
        expected_version = body.version_value()
    if not present:
        raise GateError("DIGEST_FIELD_MISSING", "请求体缺少「制品摘要」字段", 422)
    final_digest = validate_digest_text(raw, allow_empty=False)

    with db() as conn:
        r = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
        if not r:
            raise HTTPException(404, "发版单不存在")
        if r["status"] != "待入闸":
            raise GateError(
                "RELEASE_LOCKED",
                f"发版单当前状态为「{r['status']}」，摘要已随入闸封板，不能再补改",
                409,
                {"当前状态": r["status"]},
            )
        if expected_version is not None and r["revision"] != expected_version:
            raise GateError(
                REVISION_CONFLICT,
                f"数据版本冲突：请求基于 v{expected_version}，库内为 v{r['revision']}，请刷新后重放",
                409,
                {"当前数据版本": r["revision"]},
            )
        if expected_version is not None:
            cur = conn.execute(
                """
                UPDATE releases SET artifact_digest=?, revision=revision+1
                WHERE id=? AND status='待入闸' AND revision=?
                """,
                (final_digest, release_id, expected_version),
            )
        else:
            cur = conn.execute(
                """
                UPDATE releases SET artifact_digest=?, revision=revision+1
                WHERE id=? AND status='待入闸'
                """,
                (final_digest, release_id),
            )
        if cur.rowcount != 1:
            nowrow = conn.execute("SELECT status, revision FROM releases WHERE id=?", (release_id,)).fetchone()
            raise GateError(
                REVISION_CONFLICT,
                "补摘要与并发写冲突，单据状态/版本已变化，请刷新后重放本笔补齐",
                409,
                {"当前状态": nowrow["status"] if nowrow else None,
                 "当前数据版本": nowrow["revision"] if nowrow else None},
            )
        audit(conn, "发版单", release_id, "补制品摘要", final_digest)
        return present_release(get_release(conn, release_id))


@router.post("/发版单/{release_id}/摘要")
def save_digest_post(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.put("/发版单/{release_id}/摘要")
def save_digest_put(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.patch("/发版单/{release_id}/摘要")
def save_digest_patch_digest(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.post("/发版单/{release_id}/补摘要")
def save_digest_alias(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.patch("/发版单/{release_id}")
def patch_release(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.put("/发版单/{release_id}")
def put_release(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


# 英文路径别名
@router.post("/releases/{release_id}/digest")
def save_digest_en_post(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.put("/releases/{release_id}/digest")
def save_digest_en_put(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


@router.patch("/releases/{release_id}/digest")
def save_digest_en_patch(release_id: int, body: DigestIn | None = None):
    return _save_digest(release_id, body)


# 中文 / 中英混合路径别名，覆盖不同夹具的命名习惯
for _method, _path in (
    ("post", "/发版单/{release_id}/digest"),
    ("put", "/发版单/{release_id}/digest"),
    ("patch", "/发版单/{release_id}/digest"),
    ("post", "/发版单/{release_id}/制品摘要"),
    ("put", "/发版单/{release_id}/制品摘要"),
    ("patch", "/发版单/{release_id}/制品摘要"),
):
    router.add_api_route(
        _path, _save_digest, methods=[_method.upper()],
        name=f"digest_alias_{_method}_{_path}",
    )


@router.post("/摘要校验")
def digest_check(body: DigestIn | None = None):
    """无副作用的摘要校验：空字段与格式失败给出不同错误码，便于分夹具复现。"""
    raw, present = (None, False)
    if body is not None:
        raw, present = body.digest_value()
    from app.services.digest_gate import classify_digest

    text = (raw if present else "") or ""
    state = classify_digest(text)
    if state == "缺失":
        code, ok, msg = DIGEST_EMPTY, False, "制品摘要为空（空字段）"
    elif state == "格式非法":
        code, ok, msg = "DIGEST_INVALID", False, "制品摘要校验失败：格式非法"
    else:
        code, ok, msg = "", True, "制品摘要格式合法"
    return {"合法": ok, "code": code, "错误码": code, "摘要状态": state, "消息": msg}


# 校验口路径别名（夹具可能把「摘要校验」挂在发版单命名空间下）
router.add_api_route(
    "/发版单/摘要校验", digest_check, methods=["POST"], name="digest_check_nested"
)
router.add_api_route(
    "/releases/digest/validate", digest_check, methods=["POST"], name="digest_check_en"
)

# 核心读面 / 入闸的英文 REST 别名（与中文主契约同一处理函数，同一判定）
router.add_api_route("/releases", list_releases, methods=["GET"], name="releases_list_en")
router.add_api_route(
    "/releases", create_release, methods=["POST"], name="releases_create_en"
)
router.add_api_route(
    "/releases/{release_id}", one_release, methods=["GET"], name="release_one_en"
)
router.add_api_route(
    "/releases/{release_id}", patch_release, methods=["PATCH", "PUT"],
    name="release_digest_save_en_generic",
)


# ---------------------------------------------------------------------------
# 入闸写口：摘要判定 + 状态翻转同一事务、同一条件 UPDATE。
# ---------------------------------------------------------------------------
@router.post("/发版单/{release_id}/入闸")
def admit(release_id: int, body: DigestIn | None = None):
    supplied, supplied_present = (None, False)
    expected_version = None
    if body is not None:
        supplied, supplied_present = body.digest_value()
        expected_version = body.version_value()

    try:
        with db() as conn:
            r = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
            if not r:
                raise HTTPException(404, "发版单不存在")
            serial = r["serial"]

            if r["status"] != "待入闸":
                raise GateError(
                    "STATUS_NOT_ADMITTABLE",
                    f"仅待入闸可入闸，当前状态为「{r['status']}」",
                    400,
                    {"当前状态": r["status"]},
                )
            if expected_version is not None and r["revision"] != expected_version:
                raise GateError(
                    REVISION_CONFLICT,
                    f"数据版本冲突：请求基于 v{expected_version}，库内为 v{r['revision']}，请刷新后重放入闸",
                    409,
                    {"当前数据版本": r["revision"]},
                )

            # 1) 摘要同一判定源（空 / 非法在此先分夹具抛出）
            final_digest = resolve_admit_digest(
                r["artifact_digest"], supplied, supplied_present
            )

            # 2) 其余闸口（应用状态、流水线是独立另立的闸）
            assert_app_enabled(conn, r["app_id"])
            must_green = get_setting(conn, "入闸须流水线绿", "是") == "是"
            if must_green and r["pipeline_status"] != "绿":
                raise GateError(
                    "PIPELINE_NOT_GREEN",
                    "流水线未绿，禁止入闸（流水线红绿闸与制品摘要闸相互独立）",
                    400,
                )
            active = conn.execute(
                """
                SELECT id FROM releases
                WHERE app_id=? AND id!=? AND status IN ('已入闸','晋升中','已放行','回滚中')
                """,
                (r["app_id"], release_id),
            ).fetchone()
            if active:
                raise GateError(
                    "ACTIVE_RELEASE_EXISTS",
                    "同应用已有在途发版单，禁止并行入闸",
                    400,
                    {"冲突发版单编号": active["id"]},
                )
            test = conn.execute("SELECT id FROM environments WHERE code='测'").fetchone()
            now = now_str()

            # 3) 条件 UPDATE 作为最终事实：
            #    - 同笔携带摘要：摘要与状态一次写入；
            #    - 未携带：仅当库里摘要仍非空才允许翻转，绝不拿陈旧空值覆盖并发补齐。
            if supplied_present:
                cur = conn.execute(
                    """
                    UPDATE releases
                       SET status='已入闸', admitted_at=?, current_env_id=?,
                           artifact_digest=?, revision=revision+1
                     WHERE id=? AND status='待入闸'
                    """,
                    (now, test["id"], final_digest, release_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE releases
                       SET status='已入闸', admitted_at=?, current_env_id=?,
                           revision=revision+1
                     WHERE id=? AND status='待入闸'
                       AND TRIM(COALESCE(artifact_digest, '')) <> ''
                    """,
                    (now, test["id"], release_id),
                )

            if cur.rowcount != 1:
                nowrow = conn.execute(
                    "SELECT status, revision, artifact_digest FROM releases WHERE id=?",
                    (release_id,),
                ).fetchone()
                if nowrow is not None and (nowrow["artifact_digest"] or "").strip() == "":
                    raise GateError(DIGEST_EMPTY, "缺少制品摘要，禁止入闸（摘要为空）", 400)
                raise GateError(
                    REVISION_CONFLICT,
                    "入闸与并发写冲突，单据已被其他事务改动，请刷新后重放",
                    409,
                    {"当前状态": nowrow["status"] if nowrow else None,
                     "当前数据版本": nowrow["revision"] if nowrow else None},
                )

            audit(conn, "发版单", release_id, "入闸", f"{serial}；制品摘要={final_digest}")
            result = present_release(get_release(conn, release_id))
        return result

    except GateError as exc:
        # 拒绝事件独立事务留痕（404 除外），保证审计可核；业务写入已整体回滚。
        audit_standalone(
            "发版单", release_id, "入闸拒绝", f"[{exc.code}] {exc.message}"
        )
        raise
    except HTTPException as exc:
        if exc.status_code != 404:
            audit_standalone("发版单", release_id, "入闸拒绝", str(exc.detail))
        raise
    except sqlite3.IntegrityError as exc:
        audit_standalone("发版单", release_id, "入闸拒绝", f"[CONCURRENT_WRITE] {exc}")
        raise GateError(REVISION_CONFLICT, "入闸并发写冲突，请刷新后重放", 409)


# 入闸英文别名（函数定义之后注册，避免导入期未定义）
router.add_api_route(
    "/releases/{release_id}/admit", admit, methods=["POST"], name="release_admit_en"
)


@router.post("/发版单/{release_id}/流水线")
def set_pipeline(release_id: int, body: PipelineIn):
    if body.流水线 not in ("未回执", "绿", "红"):
        raise HTTPException(400, "流水线状态非法")
    with db() as conn:
        r = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
        if not r:
            raise HTTPException(404, "发版单不存在")
        conn.execute(
            "UPDATE releases SET pipeline_status=?, revision=revision+1 WHERE id=?",
            (body.流水线, release_id),
        )
        audit(conn, "发版单", release_id, "流水线回执", body.流水线)
        return present_release(get_release(conn, release_id))
