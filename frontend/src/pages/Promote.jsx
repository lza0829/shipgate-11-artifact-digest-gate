import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function Promote() {
  const [rows, setRows] = useState([])
  const [rid, setRid] = useState('')
  const [env, setEnv] = useState('预')
  const [err, setErr] = useState('')
  const [receipt, setReceipt] = useState(null)
  const load = async () => {
    const all = await api('/发版单')
    const active = all.filter((r) => ['已入闸', '晋升中'].includes(r.状态))
    setRows(active)
    if (!rid && active[0]) setRid(String(active[0].编号))
  }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])
  const go = async () => {
    setErr(''); setReceipt(null)
    try {
      const saved = await api(`/发版单/${rid}/晋升`, { method: 'POST', body: JSON.stringify({ 目标环境: env }) })
      setReceipt(`晋升回执：${saved.发版单号} → ${env}，当前状态「${saved.状态}」，制品齐全=${saved.制品齐全 ? '是' : '否'}`)
      load()
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h2>环境晋升</h2>
      {err && <p className="err" role="alert">{err}</p>}
      {receipt && <p className="ok-line" role="status">{receipt}</p>}
      <div className="row">
        <label>发版单
          <select value={rid} onChange={(e) => setRid(e.target.value)}>
            {rows.map((r) => <option key={r.编号} value={r.编号}>{r.发版单号} · {r.应用} · {r.当前环境}</option>)}
          </select>
        </label>
        <label>目标环境
          <select value={env} onChange={(e) => setEnv(e.target.value)}>
            <option value="测">测</option>
            <option value="预">预</option>
            <option value="产">产</option>
          </select>
        </label>
        <button type="button" onClick={go}>晋升</button>
        <button type="button" className="secondary" onClick={() => load().catch((e) => setErr(e.message))}>刷新</button>
      </div>
      <p className="hint-line">缺摘要/摘要非法的单据不视为制品齐全，晋升写口会硬拒（与流水线颜色无关）。</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>发版单号</th><th>应用</th><th>目标版本</th><th>制品摘要</th><th>制品齐全</th><th>状态</th><th>当前环境</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.编号} data-complete={r.制品齐全}>
                <td>{r.发版单号}</td><td>{r.应用}</td><td>{r.目标版本}</td>
                <td className="digest-cell">{r.制品摘要 ? <code title={r.制品摘要}>{r.制品摘要.slice(0, 18)}…</code> : <span className="digest-empty-text">（空）</span>}</td>
                <td>{r.制品齐全 ? <span className="tag tag-ok">齐全</span> : <span className="tag tag-bad">不齐全</span>}</td>
                <td>{r.状态}</td><td>{r.当前环境}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
