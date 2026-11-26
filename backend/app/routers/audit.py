from __future__ import annotations
from fastapi import APIRouter, Query

from app.db import db, rows_to_list

router = APIRouter(tags=["审计"])


@router.get("/审计")
def list_audit(
    关键词: str | None = None,
    q: str | None = None,
    类别: str | None = None,
    kind: str | None = None,
    动作: str | None = None,
    action: str | None = None,
    关联编号: int | None = None,
    ref_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    keyword = (关键词 or q or "").strip()
    kind_v = 类别 or kind
    action_v = 动作 or action
    ref_v = 关联编号 if 关联编号 is not None else ref_id

    where, params = [], []
    if keyword:
        where.append("(action LIKE ? OR note LIKE ? OR kind LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    if kind_v:
        where.append("kind = ?")
        params.append(kind_v)
    if action_v:
        where.append("action LIKE ?")
        params.append(f"%{action_v}%")
    if ref_v is not None:
        where.append("ref_id = ?")
        params.append(ref_v)

    sql = """
        SELECT id AS 编号, kind AS 类别, ref_id AS 关联编号,
               action AS 动作, created_at AS 时间, note AS 备注
        FROM audit_events
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with db() as conn:
        return rows_to_list(conn.execute(sql, params).fetchall())
