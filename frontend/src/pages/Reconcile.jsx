import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function Reconcile() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api('/对账').then(setData).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  if (err) return <div className="panel err">{err}</div>
  if (!data) return <div className="panel">加载中</div>
  const s = data.发版统计 || {}
  const anomalies = data.摘要异常单 || []
  return (
    <div className="panel">
      <h2>发布对账</h2>
      <div className="grid">
        {Object.entries(s).map(([k, v]) => (
          <div className={`stat ${k === '在途缺摘要数' && v ? 'stat-bad' : ''}`} key={k}>
            <div className="n">{v}</div><div className="l">{k}</div>
          </div>
        ))}
        <div className="stat"><div className="n">{data.晋升事件数}</div><div className="l">晋升事件数</div></div>
      </div>

      <h2>制品摘要异常对账</h2>
      <p className="hint-line">
        「制品齐全」只认制品摘要非空且合法，与流水线红绿分开对账。硬拒入闸臂下「在途缺摘要数」应为 0；非 0 即半截脏入闸存量。
      </p>
      <div className="table-wrap" data-testid="reconcile-digest-anomalies">
        <table>
          <thead><tr><th>发版单号</th><th>应用</th><th>状态</th><th>制品摘要</th><th>摘要状态</th><th>制品齐全</th></tr></thead>
          <tbody>
            {anomalies.map((r) => (
              <tr key={r.编号} data-testid={`reconcile-anomaly-${r.编号}`}>
                <td>{r.发版单号}</td><td>{r.应用}</td><td>{r.状态}</td>
                <td className="digest-cell">{r.制品摘要 ? <code>{r.制品摘要}</code> : <span className="digest-empty-text">（空）</span>}</td>
                <td><span className={`tag ${r.摘要状态 === '格式非法' ? 'tag-bad' : 'tag-warn'}`}>{r.摘要状态}</span></td>
                <td><span className="tag tag-bad">否</span></td>
              </tr>
            ))}
            {anomalies.length === 0 && (
              <tr><td colSpan={6} className="empty-line">无摘要异常单：所有单据摘要口径一致</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h2>名册与实例</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>应用</th><th>环境</th><th>名册版本</th><th>实例版本们</th><th>红灯数</th></tr></thead>
          <tbody>
            {(data.名册与实例 || []).map((r, i) => (
              <tr key={i}><td>{r.应用}</td><td>{r.环境}</td><td>{r.名册版本}</td><td>{r.实例版本们 || '-'}</td><td>{r.红灯数}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row"><button type="button" className="secondary" onClick={load}>刷新</button></div>
    </div>
  )
}
