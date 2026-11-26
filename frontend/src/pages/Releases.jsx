import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const DIGEST_HINT = 'sha256:<摘要值>'

function shortDigest(d) {
  if (!d) return ''
  return d.length > 26 ? `${d.slice(0, 16)}…${d.slice(-8)}` : d
}

export default function Releases() {
  const [rows, setRows] = useState([])
  const [apps, setApps] = useState([])
  const [appId, setAppId] = useState('')
  const [ver, setVer] = useState('')
  const [digest, setDigest] = useState('')
  const [err, setErr] = useState('')
  // 每行的摘要草稿（未点保存前只是本地草稿，绝不展示成已保存）
  const [drafts, setDrafts] = useState({})
  const [rowMsg, setRowMsg] = useState({})
  // 入闸回执：成功/失败都如实呈现，失败不绿
  const [receipt, setReceipt] = useState(null)

  const load = async () => {
    const list = await api('/发版单')
    setRows(list)
    const a = await api('/应用')
    setApps(a)
    if (!appId && a[0]) setAppId(String(a[0].编号))
  }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])

  const setDraft = (id, v) => setDrafts((m) => ({ ...m, [id]: v }))
  const setMsg = (id, msg) => setRowMsg((m) => ({ ...m, [id]: msg }))

  const create = async () => {
    setErr('')
    if (!ver.trim()) { setErr('请先填写目标版本'); return }
    try {
      await api('/发版单', {
        method: 'POST',
        body: JSON.stringify({ 应用编号: Number(appId), 目标版本: ver, 制品摘要: digest }),
      })
      setVer(''); setDigest(''); load()
    } catch (e) { setErr(e.message) }
  }

  const pipeline = async (id, status) => {
    setErr('')
    try {
      await api(`/发版单/${id}/流水线`, { method: 'POST', body: JSON.stringify({ 流水线: status }) })
      load()
    } catch (e) { setErr(e.message) }
  }

  const saveDigest = async (r) => {
    setErr(''); setMsg(r.编号, '')
    const value = drafts[r.编号] ?? ''
    try {
      const saved = await api(`/发版单/${r.编号}/摘要`, {
        method: 'POST',
        body: JSON.stringify({ 制品摘要: value }),
      })
      setDrafts((m) => ({ ...m, [r.编号]: '' }))
      setMsg(r.编号, '摘要已保存')
      setRows((list) => list.map((x) => (x.编号 === r.编号 ? saved : x)))
      load()
    } catch (e) {
      // 保存失败：服务端不落任何半截；本地草稿保留在输入框，但不冒充已保存
      setMsg(r.编号, `保存失败：${e.message}`)
    }
  }

  const admit = async (r, { replay = false } = {}) => {
    setErr('')
    setReceipt({ 编号: r.编号, 发版单号: r.发版单号, pending: true, ok: false, message: replay ? '正在重放入闸…' : '入闸处理中…' })
    const draft = (drafts[r.编号] ?? '').trim()
    // 输入框里有内容则同笔带给入闸写口：摘要落库与状态翻转同一事务
    const payload = draft ? { 制品摘要: draft } : {}
    try {
      const saved = await api(`/发版单/${r.编号}/入闸`, { method: 'POST', body: JSON.stringify(payload) })
      setReceipt({
        编号: r.编号, 发版单号: r.发版单号, pending: false, ok: true,
        code: '', 状态: saved.状态, 摘要状态: saved.摘要状态,
        digest: saved.制品摘要, message: `入闸成功：${saved.发版单号} 当前状态「${saved.状态}」，制品摘要${saved.摘要状态}`,
      })
      setDrafts((m) => ({ ...m, [r.编号]: '' }))
      load()
    } catch (e) {
      setReceipt({
        编号: r.编号, 发版单号: r.发版单号, pending: false, ok: false,
        code: e.code, status: e.status, message: e.message,
        replayable: e.code === 'REVISION_CONFLICT',
      })
      load().catch(() => {})
    }
  }

  const missingCount = useMemo(() => rows.filter((r) => r.状态 === '待入闸' && !r.制品齐全).length, [rows])

  return (
    <div className="panel">
      <h2>发版单</h2>
      {err && <p className="err" role="alert">{err}</p>}

      {receipt && (
        <div
          className={`receipt ${receipt.pending ? 'pending' : receipt.ok ? 'ok' : 'bad'}`}
          role={receipt.ok ? 'status' : 'alert'}
          data-testid="admit-receipt"
          data-code={receipt.code || ''}
        >
          <div className="receipt-title">
            入闸回执 · {receipt.发版单号}
            {!receipt.pending && <span className={`tag ${receipt.ok ? 'tag-ok' : 'tag-bad'}`}>{receipt.ok ? '成功' : '被拒'}</span>}
          </div>
          <div>{receipt.message}</div>
          {receipt.digest !== undefined && (
            <div className="receipt-digest">回执摘要：{receipt.digest ? shortDigest(receipt.digest) : '（空）'}</div>
          )}
          {receipt.replayable && (
            <div className="row" style={{ marginTop: 8 }}>
              <button type="button" onClick={() => admit({ 编号: receipt.编号, 发版单号: receipt.发版单号 }, { replay: true })}>
                刷新后重放入闸
              </button>
              <button type="button" className="secondary" onClick={() => load().catch((e) => setErr(e.message))}>先刷新单据</button>
            </div>
          )}
        </div>
      )}

      <div className="row">
        <label>应用
          <select value={appId} onChange={(e) => setAppId(e.target.value)}>
            {apps.map((a) => <option key={a.编号} value={a.编号}>{a.名称}</option>)}
          </select>
        </label>
        <label>目标版本<input value={ver} onChange={(e) => setVer(e.target.value)} placeholder="1.4.0" /></label>
        <label>制品摘要（可留空建草稿）
          <input value={digest} onChange={(e) => setDigest(e.target.value)} placeholder={DIGEST_HINT} />
        </label>
        <button type="button" onClick={create}>申请入闸</button>
        <button type="button" className="secondary" onClick={() => load().catch((e) => setErr(e.message))}>刷新</button>
      </div>

      {missingCount > 0 && (
        <p className="warn-line" role="status" data-testid="release-missing-count">
          当前有 {missingCount} 张待入闸单缺制品摘要：缺摘要硬拒入闸，补齐后方可入闸。
        </p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>发版单号</th><th>应用</th><th>目标版本</th>
              <th className="col-digest">制品摘要（摘要区）</th>
              <th>状态</th><th>流水线</th><th>当前环境</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const draft = drafts[r.编号] ?? ''
              const canEdit = r.状态 === '待入闸'
              return (
                <tr key={r.编号} data-testid={`release-row-${r.编号}`} data-status={r.状态}>
                  <td>{r.发版单号}</td>
                  <td>{r.应用}</td>
                  <td>{r.目标版本}</td>
                  <td className="digest-cell" data-testid={`digest-cell-${r.编号}`} data-state={r.摘要状态}>
                    <div className="digest-line">
                      {r.制品摘要
                        ? <code title={r.制品摘要}>{shortDigest(r.制品摘要)}</code>
                        : <span className="digest-empty-text">（摘要为空）</span>}
                      {r.摘要状态 === '齐全' && <span className="tag tag-ok">摘要齐全</span>}
                      {r.摘要状态 === '缺失' && <span className="tag tag-warn" data-testid="digest-warning">缺摘要</span>}
                      {r.摘要状态 === '格式非法' && <span className="tag tag-bad">摘要校验失败</span>}
                    </div>
                    {r.摘要告警 && <div className="cell-warn" role="alert">{r.摘要告警}</div>}
                    {canEdit && (
                      <div className="digest-edit">
                        <input
                          aria-label={`制品摘要输入 ${r.发版单号}`}
                          value={draft}
                          placeholder={r.制品摘要 ? shortDigest(r.制品摘要) : DIGEST_HINT}
                          onChange={(e) => setDraft(r.编号, e.target.value)}
                        />
                        <button type="button" className="secondary" onClick={() => saveDigest(r)}>
                          {r.制品摘要 ? '保存摘要' : '补摘要'}
                        </button>
                      </div>
                    )}
                    {rowMsg[r.编号] && <div className="cell-msg">{rowMsg[r.编号]}</div>}
                  </td>
                  <td><span className={`status-pill status-${r.状态}`}>{r.状态}</span></td>
                  <td>
                    <span className={`pipe-dot pipe-${r.流水线}`} title={`流水线${r.流水线}`} /> {r.流水线}
                  </td>
                  <td>{r.当前环境 || '-'}</td>
                  <td className="ops-cell">
                    <div className="btn-group" aria-label="流水线回执（独立闸）">
                      <button type="button" className="secondary" onClick={() => pipeline(r.编号, '绿')}>流水线绿</button>{' '}
                      <button type="button" className="danger" onClick={() => pipeline(r.编号, '红')}>流水线红</button>
                    </div>
                    <button type="button" className="admit-btn" onClick={() => admit(r)}>入闸</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="hint-line">
        摘要闸与流水线红绿相互独立：缺摘要一律硬拒入闸；在本行摘要框填写后直接点「入闸」，摘要与入闸同笔成败。
      </p>
    </div>
  )
}
