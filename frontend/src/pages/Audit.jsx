import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function Audit() {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  const [kw, setKw] = useState('')
  const [appliedKw, setAppliedKw] = useState('')
  const [onlyDeny, setOnlyDeny] = useState(false)

  const load = (keyword = appliedKw, deny = onlyDeny) => {
    const params = new URLSearchParams()
    if (keyword) params.set('关键词', keyword)
    if (deny) params.set('动作', '拒绝')
    const qs = params.toString()
    return api(`/审计${qs ? `?${qs}` : ''}`).then(setRows).catch((e) => setErr(e.message))
  }
  useEffect(() => { load('') }, [])

  const submit = (e) => {
    if (e) e.preventDefault()
    setAppliedKw(kw.trim())
    load(kw.trim(), onlyDeny)
  }
  const toggleDeny = () => {
    const next = !onlyDeny
    setOnlyDeny(next)
    load(appliedKw, next)
  }

  return (
    <div className="panel">
      <h2>审计流水</h2>
      {err && <p className="err">{err}</p>}
      <form className="row audit-search" onSubmit={submit} role="search">
        <label>审计查询
          <input
            aria-label="审计关键词"
            value={kw}
            placeholder="单号 / 动作 / 备注，如 入闸拒绝、DIGEST_EMPTY、摘要"
            onChange={(e) => setKw(e.target.value)}
          />
        </label>
        <button type="submit">查询</button>
        <button type="button" className={onlyDeny ? '' : 'secondary'} aria-pressed={onlyDeny} onClick={toggleDeny}>
          {onlyDeny ? '只看拒绝中 ✓' : '只看拒绝事件'}
        </button>
        <button type="button" className="secondary" onClick={() => { setKw(''); setAppliedKw(''); setOnlyDeny(false); load('', false) }}>
          重置
        </button>
        <button type="button" className="secondary" onClick={() => load()}>刷新</button>
      </form>
      <p className="hint-line" data-testid="audit-count">共 {rows.length} 条（最近 200 条内查询）</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>类别</th><th>动作</th><th>关联</th><th>备注</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.编号}
                data-testid={`audit-row-${r.编号}`}
                data-action={r.动作}
                className={String(r.动作 || '').includes('拒绝') ? 'audit-deny' : ''}
              >
                <td>{r.时间}</td>
                <td>{r.类别}</td>
                <td>{r.动作}</td>
                <td>{r.关联编号 || '-'}</td>
                <td className="audit-note">{r.备注}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="empty-line">没有匹配的审计记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
