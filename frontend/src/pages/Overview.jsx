import React, { useEffect, useState } from 'react'
import { api } from '../api'

function shortDigest(d) {
  if (!d) return ''
  return d.length > 22 ? `${d.slice(0, 14)}…${d.slice(-6)}` : d
}

export default function Overview() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api('/总览').then(setData).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  if (err) return <div className="panel err">{err}</div>
  if (!data) return <div className="panel">加载中</div>
  const d = data.分布 || {}
  const pendingDigest = data.摘要待补 || []
  const activeDirty = data.在途缺摘要数 || 0
  return (
    <div className="panel">
      <h2>总览</h2>
      <div className="grid">
        {Object.entries(d).map(([k, v]) => (
          <div className="stat" key={k}><div className="n">{v}</div><div className="l">{k}</div></div>
        ))}
        <div className={`stat ${data.缺摘要待入闸数 ? 'stat-warn' : ''}`} data-testid="overview-missing-pending">
          <div className="n">{data.缺摘要待入闸数 || 0}</div><div className="l">缺摘要待入闸</div>
        </div>
        <div className={`stat ${activeDirty ? 'stat-bad' : ''}`} data-testid="overview-active-missing">
          <div className="n">{activeDirty}</div><div className="l">在途缺摘要(异常)</div>
        </div>
      </div>

      {pendingDigest.length > 0 && (
        <>
          <h2>摘要待补 · 缺摘要不可入闸</h2>
          <div className="table-wrap" data-testid="overview-digest-pending">
            <table>
              <thead><tr><th>发版单号</th><th>应用</th><th>目标版本</th><th>状态</th><th>摘要状态</th><th>告警</th></tr></thead>
              <tbody>
                {pendingDigest.map((r) => (
                  <tr key={`p-${r.编号}`} data-testid={`overview-pending-${r.编号}`}>
                    <td>{r.发版单号}</td><td>{r.应用}</td><td>{r.目标版本}</td><td>{r.状态}</td>
                    <td><span className="tag tag-warn">缺摘要</span></td>
                    <td className="cell-warn">{r.摘要告警 || '制品摘要为空，禁止入闸'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>在途发版</h2>
      {activeDirty > 0 && (
        <p className="err" role="alert">存在 {activeDirty} 笔在途单缺摘要/摘要非法：不得视为制品齐全，晋升与对账应拦截。</p>
      )}
      <div className="table-wrap">
        <table>
          <thead><tr><th>发版单号</th><th>应用</th><th>目标版本</th><th>制品摘要</th><th>制品齐全</th><th>状态</th><th>当前环境</th><th>流水线</th></tr></thead>
          <tbody>
            {(data.在途 || []).map((r) => (
              <tr key={r.编号} data-testid={`overview-active-${r.编号}`} data-complete={r.制品齐全}>
                <td>{r.发版单号}</td><td>{r.应用}</td><td>{r.目标版本}</td>
                <td className="digest-cell">
                  {r.制品摘要 ? <code title={r.制品摘要}>{shortDigest(r.制品摘要)}</code> : <span className="digest-empty-text">（空）</span>}
                </td>
                <td>
                  {r.制品齐全
                    ? <span className="tag tag-ok">齐全</span>
                    : <span className="tag tag-bad" data-testid="overview-active-warning">缺摘要/非法</span>}
                </td>
                <td>{r.状态}</td><td>{r.当前环境 || '-'}</td><td>{r.流水线}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>各环境版本</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>应用</th><th>环境</th><th>版本</th><th>更新时间</th></tr></thead>
          <tbody>
            {(data.环境版本 || []).map((v, i) => (
              <tr key={i}><td>{v.应用}</td><td>{v.环境}</td><td>{v.版本}</td><td>{v.更新时间}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row"><button type="button" className="secondary" onClick={load}>刷新</button></div>
    </div>
  )
}
