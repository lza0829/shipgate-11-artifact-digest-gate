from __future__ import annotations
from fastapi import APIRouter

from app.db import db, rows_to_list, RELEASE_ACTIVE_STATUSES
from app.services.common import RELEASE_SELECT, present_releases

router = APIRouter(tags=["总览"])


@router.get("/总览")
def overview():
    active_marks = ",".join("?" for _ in RELEASE_ACTIVE_STATUSES)
    with db() as conn:
        counts = {}
        for name in ("待入闸", "已入闸", "晋升中", "已放行", "回滚中", "已回滚", "已关闭"):
            counts[name] = conn.execute(
                "SELECT COUNT(*) AS c FROM releases WHERE status=?", (name,)
            ).fetchone()["c"]
        active_rows = conn.execute(
            RELEASE_SELECT
            + f" WHERE r.status IN ({active_marks}) ORDER BY r.id DESC",
            RELEASE_ACTIVE_STATUSES,
        ).fetchall()
        active = present_releases(active_rows)

        # 待入闸但摘要空/非法：硬拒臂下它们绝不可能进入「在途」，
        # 总览单独露出缺摘要格，读侧与写侧同一判定。
        pending_rows = conn.execute(
            RELEASE_SELECT + " WHERE r.status='待入闸' ORDER BY r.id DESC"
        ).fetchall()
        pending = present_releases(pending_rows)
        digest_missing_pending = [r for r in pending if not r["摘要齐全"]]

        # 防御性指标：正常硬拒臂下恒为 0；若非 0 说明出现了历史脏在途单。
        active_digest_missing = [r for r in active if not r["摘要齐全"]]

        versions = rows_to_list(
            conn.execute(
                """
                SELECT a.name AS 应用, e.code AS 环境, e.name AS 环境名,
                       v.version AS 版本, v.updated_at AS 更新时间
                FROM app_env_versions v
                JOIN apps a ON a.id = v.app_id
                JOIN environments e ON e.id = v.env_id
                ORDER BY a.id, e.sort_order
                """
            ).fetchall()
        )
        health = rows_to_list(
            conn.execute(
                """
                SELECT i.id AS 编号, a.name AS 应用, e.code AS 环境, i.version AS 版本,
                       i.health AS 健康, i.release_id AS 发版单编号, i.updated_at AS 更新时间
                FROM instances i
                JOIN apps a ON a.id = i.app_id
                JOIN environments e ON e.id = i.env_id
                ORDER BY a.id, e.sort_order, i.id
                """
            ).fetchall()
        )
        return {
            "分布": counts,
            "在途": active,
            "环境版本": versions,
            "实例": health,
            # 摘要闸读侧暴露
            "摘要待补": digest_missing_pending,
            "缺摘要待入闸数": len(digest_missing_pending),
            "在途缺摘要数": len(active_digest_missing),
            "摘要闸臂": "硬拒",
        }
