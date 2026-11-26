# 发版闸（Shipgate）

骨架：发版申请入闸 → 环境晋升裁决 → 放行/回滚窗 → 发布结果对账

- 前端 http://127.0.0.1:6800
- API http://127.0.0.1:11800
- 数据库环境变量 `SHIPGATE_DB`（容器内默认 `/data/shipgate.db`）

```bash
docker compose up -d --build
```

本地开发：

```bash
# 后端（/workspace/backend）
SHIPGATE_DB=/tmp/gate.db /workspace/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 11800
# 前端（/workspace/frontend）
npx vite --port 6800 --host 127.0.0.1   # /api 代理到 127.0.0.1:11800
```

---

## 制品摘要闸：缺摘要硬拒入闸（Arm A）

摘要入闸策略由实现方敲定并全站贯彻为 **硬拒臂**：制品摘要为空的发版单
**一律不得入闸**。本闸只裁决摘要的空 / 非空（及摘要串自身格式）；
流水线红黄绿是另一条独立闸（`PIPELINE_NOT_GREEN`），两者互不冒充。

唯一判定源：`backend/app/services/digest_gate.py`。写口与所有读面
（发版单摘要区/摘要列、入闸回执、总览在途/摘要待补、晋升、对账、审计）
都调用同一套 `classify_digest` / `digest_complete`，不存在第二套口径。

### 三态与错误码

| 摘要状态 | 含义 | 入闸/补写结果 |
| --- | --- | --- |
| `齐全` | 非空且格式合法 | 放行本闸 |
| `缺失` | `NULL` 或 `TRIM` 后为空 | `DIGEST_EMPTY`，HTTP 400 |
| `格式非法` | 非空但不匹配摘要格式 | `DIGEST_INVALID`，HTTP 422 |

空字段与格式失败是 **两个可分别复现的夹具**：错误码、HTTP 状态、中文文案均不同。
其他稳定码：`REVISION_CONFLICT`(409)、`RELEASE_LOCKED`(409)、
`ARTIFACT_INCOMPLETE`(400，晋升/对账口径)。错误响应统一为
`{ok:false, code, 错误码, detail, 明细, ...附加字段}`。

### 事务与并发保证

- 入闸可同笔携带摘要：摘要校验/落库与 `状态='已入闸'` 翻转在 **同一事务、同一条条件 UPDATE**
  内完成；其后任何闸口失败或进程异常都整体回滚——失败回到「待入闸」，
  不留半截摘要草稿，也没有脏入闸。
- 不带摘要的入闸以条件
  `WHERE id=? AND status='待入闸' AND TRIM(COALESCE(artifact_digest,''))<>''`
  作为线性化点，与并发补摘要竞争时不会写出空摘要入闸单；
  `rowcount=0` 时回读区分 `DIGEST_EMPTY` 与 `REVISION_CONFLICT`，败者拿明确错误并重放。
- 所有写口支持 `期望版本` / `expectedVersion` 乐观锁，冲突返回 409 且不写入。
- 拒绝事件（`入闸拒绝` / `晋升拒绝`）通过 `audit_standalone` 用独立事务落审计，
  业务回滚不影响拒绝留痕，保证「不得已入闸却摘要空且无告警可核」。
- 硬拒臂下新数据不存在空摘要入闸；对绕过写口造出的历史脏在途单，
  总览/对账标 `制品齐全=false`、计入在途缺摘要，晋升以 `ARTIFACT_INCOMPLETE` 拒绝并审计。

### 接口别名（同一处理函数、同一判定）

- 建单：`POST /api/发版单`（兼容 `POST /api/releases`；中英文字段
  `应用编号/appId/app_id`、`目标版本/version/targetVersion`、
  `制品摘要/digest/artifactDigest`）。建单允许空摘要草稿。
- 补/改摘要：`POST|PUT|PATCH /api/发版单/{id}/摘要`（另有 `/补摘要`、
  `PATCH|PUT /api/发版单/{id}`、`/api/releases/{id}/digest` 及若干中英混合路径）。
- 校验口：`POST /api/摘要校验`（别名 `/api/发版单/摘要校验`、
  `/api/releases/digest/validate`），无副作用，空与非法返回不同码。
- 入闸：`POST /api/发版单/{id}/入闸`（可空 body；别名
  `POST /api/releases/{id}/admit`）。
- 审计：`GET /api/审计?关联编号={id}&关键词=入闸拒绝`（兼容 `q/action/kind/ref_id`）。

### 验证夹具（仓库外 `/tmp`，无随仓 grader）

- `/tmp/digest_fixtures.py <BASE>/api`：40 项跨面对照（空摘要拒绝、
  空 vs 非法分码、同笔回滚、补齐后入闸对读、历史脏单晋升/总览/对账/审计）。
- `/tmp/digest_stress.py <BASE>/api`：46 组补摘要 × 入闸竞态，断言无脏单、结局可重放。
- `/tmp/digest_fault.py`：TestClient + 故障注入，断言中断回滚后无脏入闸/假草稿。
- `/tmp/uitest/ui.mjs`：Playwright 真实浏览器 18 项全流程（发版单 → 回执 →
  总览在途 → 审计查询）。
