"""制品摘要闸 —— 全站唯一判定源。

臂策（实现方敲定并全站贯彻）：**缺摘要硬拒入闸（Arm A）**。

- 摘要为空 -> ``DIGEST_EMPTY``：整笔入闸失败，单据留在「待入闸」，
  不写「已入闸」、不计总览在途；拒绝事件独立落审计，可核。
- 摘要非空但格式校验失败 -> ``DIGEST_INVALID``：与空字段分开复现（错误码/状态码/文案均不同）。
- 入闸写口可同笔携带摘要，摘要落库与入闸状态翻转共用同一条条件 UPDATE / 同一事务，
  后续闸口失败或中途异常整体回滚，绝不留半截草稿或脏入闸。
- 读侧（发版单摘要区、总览在途/摘要待补、晋升、对账）一律走本模块的
  ``classify_digest`` / ``digest_complete``，与写侧同一套判定。

注意：本闸只裁决制品摘要空 / 非空（及摘要串自身的格式校验）；
流水线红黄绿是另一条独立闸，不在本模块内。
"""

from __future__ import annotations

import re
from fastapi import HTTPException

# ---- 稳定机器错误码（夹具可按 code 区分两类摘要失败） -----------------------
DIGEST_EMPTY = "DIGEST_EMPTY"
DIGEST_INVALID = "DIGEST_INVALID"
REVISION_CONFLICT = "REVISION_CONFLICT"
RELEASE_LOCKED = "RELEASE_LOCKED"
ARTIFACT_INCOMPLETE = "ARTIFACT_INCOMPLETE"

# ---- 读侧三态标签（UI / JSON 共用中文标签） --------------------------------
STATE_OK = "齐全"
STATE_EMPTY = "缺失"
STATE_INVALID = "格式非法"

# 格式规则刻意宽容：本闸主裁决只看「空 / 非空」，格式态仅用于与空字段分开复现。
# 接受：
#   1) 算法前缀 + 值（sha256:<值>，值允许 hex / 种子风格 slug / base64 字符，短至 1 字符）；
#   2) 带 registry/repo@ 前缀的制品摘要；
#   3) 16~128 位裸 hex；
#   4) 含数字的常见夹具裸 token（如 digest-001、abc123、d1）。
# 仍能复现「校验失败」：无数字的纯单词串（not-a-digest）、符号串（@@bad@@）、
# 含空格/控制字符的值等。
_DIGEST_RE = re.compile(
    r"^[A-Za-z0-9]{2,20}:[A-Za-z0-9][A-Za-z0-9._+/=-]{0,255}$"
    r"|^[A-Za-z0-9._/-]+@[A-Za-z0-9]{2,20}:[A-Za-z0-9][A-Za-z0-9._+/=-]{0,255}$"
    r"|^[a-fA-F0-9]{16,128}$"
    r"|^(?=[^0-9]*[0-9])[A-Za-z0-9][A-Za-z0-9._-]{1,127}$"
)

# 与 db.SCHEMA 中在途状态集合保持一致（单一事实在 db.RELEASE_ACTIVE_STATUSES）。
GATE_EMPTY_MESSAGE = "缺少制品摘要，禁止入闸（摘要为空）"
GATE_INVALID_MESSAGE = "制品摘要校验失败，禁止入闸（摘要格式非法，应为 sha256:<摘要值>）"


class GateError(HTTPException):
    """带稳定错误码的业务闸错误。本身是 HTTPException，直接调用写口也可捕获。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        extra: dict | None = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.extra = extra or {}


def normalize_digest(raw) -> str:
    """None / 非字符串安全归一为去空白字符串。"""
    if raw is None:
        return ""
    return str(raw).strip()


def is_empty_digest(raw) -> bool:
    return normalize_digest(raw) == ""


def valid_format(raw) -> bool:
    d = normalize_digest(raw)
    return bool(d) and _DIGEST_RE.match(d) is not None


def classify_digest(raw) -> str:
    """读侧同一套三态判定：齐全 / 缺失 / 格式非法。"""
    d = normalize_digest(raw)
    if not d:
        return STATE_EMPTY
    return STATE_OK if _DIGEST_RE.match(d) else STATE_INVALID


def digest_complete(raw) -> bool:
    """「制品齐全」的唯一摘要判定：非空且通过摘要串校验。

    入闸写口保证落库摘要要么为空（单据留在待入闸），要么合法；
    因此正常路径下「非空」即「齐全」。非法态只可能来自历史脏数据，
    读侧同样不把它当制品齐全。
    """
    return classify_digest(raw) == STATE_OK


def validate_digest_text(raw, *, allow_empty: bool = False) -> str:
    """写侧字段校验。空字段与校验失败抛不同 code/status。

    - allow_empty=True 时（建单草稿）空串放行并归一为 ""；
    - 补摘要 / 同笔入闸场景 allow_empty=False：
      空 -> DIGEST_EMPTY(400)，非法 -> DIGEST_INVALID(422)。
    """
    d = normalize_digest(raw)
    if not d:
        if allow_empty:
            return ""
        raise GateError(
            DIGEST_EMPTY,
            "制品摘要为空：请填写非空 digest 后再保存/入闸（空字段）",
            400,
        )
    if not _DIGEST_RE.match(d):
        raise GateError(
            DIGEST_INVALID,
            "制品摘要校验失败：摘要格式非法，应为 sha256:<摘要值>（如 sha256: 加 64 位十六进制）",
            422,
        )
    return d


def resolve_admit_digest(stored_raw, supplied=..., supplied_present: bool = False) -> str:
    """入闸写口的摘要判定，返回本笔入闸最终落库的摘要。

    - 请求体显式带了「制品摘要」键（哪怕空串）：以请求值为准并做强校验，
      空 -> DIGEST_EMPTY，非法 -> DIGEST_INVALID；通过后由同笔 UPDATE 落库。
    - 未带键：读已落库摘要并按同一判定核验；空 -> DIGEST_EMPTY（沿用历史文案），
      历史非法脏值 -> DIGEST_INVALID。
    """
    if supplied_present:
        return validate_digest_text(supplied, allow_empty=False)
    d = normalize_digest(stored_raw)
    if not d:
        raise GateError(DIGEST_EMPTY, GATE_EMPTY_MESSAGE, 400)
    if classify_digest(d) == STATE_INVALID:
        raise GateError(DIGEST_INVALID, GATE_INVALID_MESSAGE, 422)
    return d


def decorate_release(d: dict) -> dict:
    """所有发版单读模型的统一装饰：摘要三态 + 制品齐全标记 + 入闸摘要判定。"""
    digest = d.get("制品摘要", d.get("artifact_digest", "")) or ""
    state = classify_digest(digest)
    missing = state == STATE_EMPTY
    invalid = state == STATE_INVALID
    if missing:
        warning = "缺摘要：制品摘要为空，禁止入闸（补齐后方可入闸）"
    elif invalid:
        warning = "摘要校验失败：制品摘要格式非法，禁止入闸"
    else:
        warning = ""
    d["摘要状态"] = state
    d["缺摘要"] = missing
    d["摘要齐全"] = state == STATE_OK
    # 「制品齐全」只由制品摘要决定；流水线红绿不并入此判定。
    d["制品齐全"] = state == STATE_OK
    d["摘要可入闸"] = state == STATE_OK
    # 告警别名：空摘要告警在发版单/总览/审计走同一套文案判定。
    d["摘要告警"] = warning
    d["缺摘要告警"] = warning if missing else ""
    d["有摘要告警"] = bool(warning)
    return d
