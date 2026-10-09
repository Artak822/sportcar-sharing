import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Badge, BookingSummary, SpecList } from '../ds.js'
import DateRange from '../components/DateRange.jsx'
import { BODY_TYPES, humanDay, humanDays, humanDt, pickDates, rub, withTime } from '../format.js'
import { useStore, usePageInfo } from '../store.jsx'

export default function CarPage() {
  const { id } = useParams()
  const { me, version } = useStore()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { from, to } = pickDates(params)
  const location = params.get('location') || ''
  const extras = params.get('extras')?.split(',').filter(Boolean) ?? []

  const [car, setCar] = useState(null)
  const [catalog, setCatalog] = useState({ extras: [], locations: [] })
  const [avail, setAvail] = useState(null)
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState('')
  const [booking, setBooking] = useState(false)

  useEffect(() => {
    api.car(id).then(setCar, (e) => setError(e.message))
    Promise.all([api.extras(), api.locations()]).then(([extras, locations]) => setCatalog({ extras, locations }))
  }, [id])

  const ok = from < to
  const extrasKey = extras.join(',')
  useEffect(() => {
    if (!ok) return
    let alive = true
    setError('')
    Promise.all([api.availability(id, withTime(from), withTime(to)), api.quote({ car_id: id, from: withTime(from), to: withTime(to), extras })]).then(
      ([a, q]) => { if (alive) { setAvail(a); setQuote(q) } },
      (e) => alive && setError(e.message))
    return () => { alive = false }
  }, [id, from, to, extrasKey, ok, version]) // eslint-disable-line react-hooks/exhaustive-deps

  usePageInfo(car ? `Страница машины ${car.name} (car_id ${car.id}), даты ${ok ? humanDays(from, to) + ', выдача и возврат в 10:00' : 'не выбраны'}`
    + (avail ? (avail.available ? ', свободна' : ', занята') : '') : null)

  function set(values) {
    const next = new URLSearchParams(params)
    next.set('from', from)
    next.set('to', to)
    for (const [k, v] of Object.entries(values)) v ? next.set(k, v) : next.delete(k)
    setParams(next, { replace: true })
  }

  function toggleExtra(code) {
    set({ extras: (extras.includes(code) ? extras.filter((c) => c !== code) : [...extras, code]).join(',') })
  }

  // «Забронировать» на сайте — тот же путь, что у агента: черновик, затем подтверждение клиентом (это нажатие)
  async function book() {
    if (!me) {
      navigate('/login?next=' + encodeURIComponent(window.location.pathname + window.location.search))
      return
    }
    if (!location) {
      setError('Выберите точку выдачи')
      return
    }
    setBooking(true)
    setError('')
    try {
      const draft = await api.propose('create_booking', { car_id: id, from: withTime(from), to: withTime(to), location_id: location, extras })
      const done = await api.confirm(draft.action_id)
      if (done.status === 'done') navigate(`/bookings/${done.result.number}`)
      else setError(done.error || 'Не получилось оформить бронь')
    } catch (e) {
      setError(e.message)
    } finally {
      setBooking(false)
    }
  }

  if (!car) return error ? <p className="error-text" role="alert">{error}</p> : <p className="muted">Загружаем…</p>

  const service = car.status === 'service'
  const free = avail?.available && !service

  return (
    <>
      <p className="crumbs"><Link to={`/?from=${from}&to=${to}`}>← Каталог</Link></p>
      <div className="car-page">
        <div className="car-main">
          <div className="car-photo">
            {car.image_url ? <img src={car.image_url} alt={car.name} /> : <span>фото 16:9</span>}
          </div>
          <div className="car-head">
            <h1 className="heading">{car.name}</h1>
            <Badge tone={service ? 'service' : avail ? (free ? 'available' : 'booked') : 'neutral'}>
              {service ? 'На обслуживании' : !avail ? '…' : free ? 'Свободна на эти даты' : 'Занята на эти даты'}
            </Badge>
          </div>
          <SpecList items={[
            { label: 'Мощность', value: car.power, unit: 'л. с.' },
            { label: '0–100 км/ч', value: String(car.accel).replace('.', ','), unit: 'с' },
            { label: 'Мест', value: car.seats },
            { label: 'Кузов', value: BODY_TYPES[car.body_type] },
          ]} />
          <section className="terms">
            <h2 className="title">Условия аренды</h2>
            <dl className="terms-list">
              <dt>Депозит</dt><dd>{rub(car.deposit)}, блокируем на карте при выдаче и возвращаем после сдачи</dd>
              <dt>Пробег</dt><dd>{car.mileage_limit_km} км в сутки, сверх лимита — 50 ₽/км</dd>
              <dt>Водитель</dt><dd>от {car.min_age} лет, стаж от {car.min_experience} лет</dd>
              <dt>Отмена</dt><dd>бесплатно до оплаты; оплаченную — не позже чем за 24 часа до начала</dd>
            </dl>
          </section>
        </div>

        <aside className="car-side">
          <div className="booking-form">
            <div className="wide"><DateRange from={from} to={to} onChange={set} /></div>
            <label className="filter wide">
              <span className="label">Точка выдачи</span>
              <select className="control" value={location} onChange={(e) => set({ location: e.target.value })}>
                <option value="">Выберите</option>
                {catalog.locations.map((l) => <option key={l.id} value={l.id}>{l.name}, {l.address} ({l.hours})</option>)}
              </select>
            </label>
            <fieldset className="extras wide">
              <legend className="label">Дополнительно</legend>
              {catalog.extras.map((x) => (
                <label key={x.code} className="check">
                  <input type="checkbox" checked={extras.includes(x.code)} onChange={() => toggleExtra(x.code)} />
                  <span>{x.name}</span>
                  <span className="muted pl-num">{rub(x.price)}{x.per === 'day' ? ' /сут.' : ''}</span>
                </label>
              ))}
            </fieldset>
          </div>

          {!ok ? <p className="error-text">Дата возврата должна быть позже даты выдачи.</p> : quote && (
            <BookingSummary car={car.name} from={humanDay(quote.from) + ', 10:00'} to={humanDay(quote.to) + ', 10:00'}
              pricePerDay={quote.price_per_day} days={quote.days}
              extras={quote.extras.map((e) => ({ label: e.label, price: e.price }))} deposit={quote.deposit}
              onConfirm={free && !booking ? book : undefined}
              confirmLabel={me ? 'Забронировать' : 'Войти и забронировать'} />
          )}
          {ok && avail && !free && !service && (
            <p className="body-sm muted">
              Машина занята на эти даты{avail.next_available_from && `, освободится ${humanDt(avail.next_available_from)}`}.
            </p>
          )}
          {booking && <p className="body-sm muted">Оформляем…</p>}
          {error && <p className="error-text" role="alert">{error}</p>}
          <p className="body-sm muted">После брони машина держится за вами 30 минут до оплаты.</p>
        </aside>
      </div>
    </>
  )
}
