from __future__ import annotations
from fastapi import APIRouter

from app.db import db, rows_to_list, RELEASE_ACTIVE_STATUSES
from app.services.common import RELEASE_SELECT, present_releases

router = APIRouter(tags=["对账"])


@router.get("/对账")
def reconcile():
    active_marks = ",".join("?" for _ in RELEASE_ACTIVE_STATUSES)
    with db() as conn:
        release_stats = {
            "申请数": conn.execute("SELECT COUNT(*) AS c FROM releases").fetchone()["c"],
            "已放行": conn.execute(
                "SELECT COUNT(*) AS c FROM releases WHERE status='已放行'"
            ).fetchone()["c"],
            "已回滚": conn.execute(
                "SELECT COUNT(*) AS c FROM releases WHERE status='已回滚'"
            ).fetchone()["c"],
            "在途": conn.execute(
                f"SELECT COUNT(*) AS c FROM releases WHERE status IN ({active_marks})",
                RELEASE_ACTIVE_STATUSES,
            ).fetchone()["c"],
        }

        # 制品摘要同一判定源：对账的「制品齐全」只认摘要齐全，不认流水线颜色。
        all_rows = conn.execute(RELEASE_SELECT + " ORDER BY r.id DESC").fetchall()
        all_releases = present_releases(all_rows)
        complete = [r for r in all_releases if r["制品齐全"]]
        digest_empty = [r for r in all_releases if r["缺摘要"]]
        digest_invalid = [
            r for r in all_releases if r["摘要状态"] == "格式非法"
        ]
        active_incomplete = [
            r
            for r in all_releases
            if r["状态"] in RELEASE_ACTIVE_STATUSES and not r["制品齐全"]
        ]
        release_stats["制品齐全数"] = len(complete)
        release_stats["缺摘要数"] = len(digest_empty)
        release_stats["摘要非法数"] = len(digest_invalid)
        release_stats["在途缺摘要数"] = len(active_incomplete)

        version_vs_instance = rows_to_list(
            conn.execute(
                """
                SELECT a.name AS 应用, e.code AS 环境,
                       v.version AS 名册版本,
                       GROUP_CONCAT(i.version, ',') AS 实例版本们,
                       SUM(CASE WHEN i.health='探针红' THEN 1 ELSE 0 END) AS 红灯数
                FROM app_env_versions v
                JOIN apps a ON a.id = v.app_id
                JOIN environments e ON e.id = v.env_id
                LEFT JOIN instances i ON i.app_id = v.app_id AND i.env_id = v.env_id
                GROUP BY v.app_id, v.env_id
                ORDER BY a.id, e.sort_order
                """
            ).fetchall()
        )
        promote_count = conn.execute("SELECT COUNT(*) AS c FROM promote_events").fetchone()["c"]
        return {
            "发版统计": release_stats,
            "晋升事件数": promote_count,
            "名册与实例": version_vs_instance,
            # 摘要异常对读：空摘要单 / 在途却不齐全的脏单（硬拒臂下后者恒空）
            "摘要异常单": [
                {
                    "编号": r["编号"],
                    "发版单号": r["发版单号"],
                    "应用": r["应用"],
                    "状态": r["状态"],
                    "制品摘要": r["制品摘要"],
                    "摘要状态": r["摘要状态"],
                    "制品齐全": r["制品齐全"],
                }
                for r in all_releases
                if not r["制品齐全"]
            ],
            "在途缺摘要": [
                {
                    "编号": r["编号"],
                    "发版单号": r["发版单号"],
                    "应用": r["应用"],
                    "状态": r["状态"],
                    "摘要状态": r["摘要状态"],
                }
                for r in active_incomplete
            ],
        }
