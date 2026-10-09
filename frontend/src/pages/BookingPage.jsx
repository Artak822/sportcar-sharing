import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Badge, BookingSummary, Button } from '../ds.js'
import ActionCard, { decide } from '../chat/ActionCard.jsx'
import DateRange from '../components/DateRange.jsx'
import { BOOKING_STATUS, humanDt, humanPeriod, withTime } from '../format.js'
import { useStore, usePageInfo } from '../store.jsx'

export default function BookingPage() {
  const { ref } = useParams()
  const { me, version, changed } = useStore()
  const [b, setB] = useState(null)
  const [extras, setExtras] = useState([])
  const [error, setError] = useState('')
  const [mode, setMode] = useState(null) // null | 'dates' | 'extras'
  const [action, setAction] = useState(null)

  const load = () => api.booking(ref).then(setB, (e) => setError(e.message))
  useEffect(() => { if (me) load() }, [me, ref, version]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.extras().then(setExtras) }, [])

  usePageInfo(b ? `Бронь ${b.number}: ${b.car_name}, ${humanPeriod(b.from, b.to)}, статус ${b.status}` : null)

  if (me === null) return <Navigate to={`/login?next=/bookings/${ref}`} replace />
  if (!b) return error ? <p className="error-text" role="alert">{error}</p> : <p className="muted">Загружаем…</p>

  const [tone, label] = BOOKING_STATUS[b.status]
  const editable = b.status === 'pending_payment' || b.status === 'paid'

  async function pay() {
    setError('')
    try {
      setB(await api.pay(b.number))
      changed()
    } catch (e) {
      setError(e.message)
    }
  }

  // Изменения брони — как у агента: сайт готовит черновик, клиент подтверждает его в карточке
  async function propose(tool, params) {
    setError('')
    try {
      setAction(await api.propose(tool, { booking_id: b.number, ...params }))
      setMode(null)
    } catch (e) {
      setError(e.message)
    }
  }

  async function onDecide(a, verb) {
    const fresh = await decide(api, a, verb, setAction)
    if (fresh?.status === 'done') { await load(); changed() }
  }

  return (
    <>
      <p className="crumbs"><Link to="/bookings">← Мои брони</Link></p>
      <div className="car-head">
        <h1 className="heading">Бронь {b.number}</h1>
        <Badge tone={tone}>{label}</Badge>
      </div>

      <div className="car-page">
        <div className="car-main">
          <BookingSummary car={b.car_name} from={humanDt(b.from)} to={humanDt(b.to)}
            pricePerDay={b.price_per_day} days={b.days}
            extras={b.extras.map((e) => ({ label: e.label, price: e.price }))} deposit={b.deposit} />
          <p className="body-sm muted">Выдача: {b.location}</p>
        </div>

        <aside className="car-side">
          {b.status === 'pending_payment' && (
            <section className="pay">
              <h2 className="title">Оплата</h2>
              <p className="body-sm muted">Бронь ждёт оплаты до {b.hold_until?.slice(11, 16)}. Это демо: деньги не списываются.</p>
              <Button variant="primary" size="lg" block onClick={pay}>Оплатить (демо)</Button>
            </section>
          )}

          {action && <ActionCard action={action} onDecide={onDecide} link={false} />}

          {editable && !(action?.status === 'proposed') && (
            <section className="manage">
              <h2 className="title">Изменить</h2>
              <div className="manage-btns">
                <Button onClick={() => setMode(mode === 'dates' ? null : 'dates')}>Перенести даты</Button>
                <Button onClick={() => setMode(mode === 'extras' ? null : 'extras')}>Услуги</Button>
                <Button variant="ghost" onClick={() => propose('cancel_booking', {})}>Отменить бронь</Button>
              </div>
              {mode === 'dates' && <DatesForm b={b} onSubmit={(p) => propose('change_booking_dates', p)} />}
              {mode === 'extras' && <ExtrasForm b={b} extras={extras} onSubmit={(p) => propose('update_booking_extras', p)} />}
            </section>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
        </aside>
      </div>
    </>
  )
}

function DatesForm({ b, onSubmit }) {
  const [range, setRange] = useState({ from: b.from.slice(0, 10), to: b.to.slice(0, 10) })
  const same = range.from === b.from.slice(0, 10) && range.to === b.to.slice(0, 10)
  return (
    <form className="booking-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ from: withTime(range.from), to: withTime(range.to) }) }}>
      <div className="wide"><DateRange from={range.from} to={range.to} onChange={setRange} /></div>
      <p className="body-sm muted wide">Выдача и возврат — в 10:00.</p>
      <Button type="submit" variant="primary" disabled={same}>Показать изменения</Button>
    </form>
  )
}

function ExtrasForm({ b, extras, onSubmit }) {
  const had = b.extras.map((e) => e.code)
  const [codes, setCodes] = useState(had)
  const add = codes.filter((c) => !had.includes(c))
  const remove = had.filter((c) => !codes.includes(c))
  return (
    <form className="booking-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ add, remove }) }}>
      <fieldset className="extras wide">
        {extras.map((x) => (
          <label key={x.code} className="check">
            <input type="checkbox" checked={codes.includes(x.code)}
              onChange={() => setCodes(codes.includes(x.code) ? codes.filter((c) => c !== x.code) : [...codes, x.code])} />
            <span>{x.name}</span>
          </label>
        ))}
      </fieldset>
      <Button type="submit" variant="primary" disabled={!add.length && !remove.length}>Показать изменения</Button>
    </form>
  )
}
