import { useEffect, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Badge } from '../ds.js'
import { BOOKING_STATUS, humanPeriod, rub } from '../format.js'
import { useStore, usePageInfo } from '../store.jsx'

const TABS = [['upcoming', 'Предстоящие'], ['active', 'Сейчас'], ['past', 'Прошедшие']]

export default function Bookings() {
  const { me, version } = useStore()
  const [params, setParams] = useSearchParams()
  const tab = TABS.some(([k]) => k === params.get('tab')) ? params.get('tab') : 'upcoming'
  const [list, setList] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!me) return
    let alive = true
    setList(null)
    api.bookings(tab).then((l) => alive && setList(l), (e) => alive && setError(e.message))
    return () => { alive = false }
  }, [me, tab, version])

  usePageInfo(`Мои брони, вкладка «${TABS.find(([k]) => k === tab)[1]}»`
    + (list ? `: ${list.map((b) => `${b.number} ${b.car_name}`).join(', ') || 'пусто'}` : ''))

  if (me === null) return <Navigate to="/login?next=/bookings" replace />

  return (
    <>
      <h1 className="heading">Мои брони</h1>
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className="tab"
            onClick={() => setParams({ tab: k }, { replace: true })}>{label}</button>
        ))}
      </div>
      {error ? <p className="error-text" role="alert">{error}</p>
        : list === null ? <p className="muted">Загружаем…</p>
        : list.length === 0 ? (
          <div className="empty">
            <p className="muted">Здесь пока пусто.</p>
            {tab === 'upcoming' && <Link to="/">Выбрать машину</Link>}
          </div>
        ) : (
          <ul className="booking-list">
            {list.map((b) => {
              const [tone, label] = BOOKING_STATUS[b.status]
              return (
                <li key={b.id}>
                  <Link to={`/bookings/${b.number}`} className="booking-row">
                    <span className="booking-row-main">
                      <span className="title">{b.car_name}</span>
                      <span className="body-sm muted">{b.number} · {humanPeriod(b.from, b.to)}</span>
                    </span>
                    <Badge tone={tone}>{label}</Badge>
                    <span className="data">{rub(b.total)}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
    </>
  )
}
