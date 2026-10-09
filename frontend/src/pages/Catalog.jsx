import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { CarCard } from '../ds.js'
import DateRange from '../components/DateRange.jsx'
import { BODY_TYPES, days, humanDays, nextWeekend, plural, rub, withTime } from '../format.js'
import { usePageInfo } from '../store.jsx'

const PRICES = [20000, 30000, 50000]
const POWERS = [350, 400, 450]
const SORTS = { price: 'Сначала дешевле', power: 'Сначала мощнее', accel: 'Быстрее разгон' }

export default function Catalog() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const weekend = nextWeekend()
  const f = {
    from: (params.get('from') || weekend.from).slice(0, 10),
    to: (params.get('to') || weekend.to).slice(0, 10),
    body_type: params.get('body_type') || '',
    max_price_per_day: params.get('max_price_per_day') || '',
    min_power: params.get('min_power') || '',
    sort: params.get('sort') || 'price',
  }
  const [cars, setCars] = useState(null)
  const [error, setError] = useState('')
  const key = new URLSearchParams(f).toString()

  useEffect(() => {
    let alive = true
    setError('')
    api.cars({ ...f, from: withTime(f.from), to: withTime(f.to), limit: 50 })
      .then((c) => alive && setCars(c), (e) => alive && setError(e.message))
    return () => { alive = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  const ok = f.from < f.to
  usePageInfo(`Каталог. Даты ${ok ? humanDays(f.from, f.to) + ', выдача и возврат в 10:00' : 'не выбраны'}`
    + (f.body_type ? `, кузов ${BODY_TYPES[f.body_type].toLowerCase()}` : '')
    + (f.max_price_per_day ? `, до ${rub(+f.max_price_per_day)} в сутки` : '')
    + (f.min_power ? `, от ${f.min_power} л. с.` : ''))

  function set(values) {
    const next = new URLSearchParams()
    for (const [k, v] of Object.entries({ ...f, ...values })) if (v && !(k === 'sort' && v === 'price')) next.set(k, v)
    setParams(next, { replace: true })
  }

  const dates = `from=${f.from}&to=${f.to}`
  const free = cars?.filter((c) => c.status === 'available').length
  const filtered = f.body_type || f.max_price_per_day || f.min_power

  return (
    <>
      <section className="hero">
        <h1 className="display">Спорткары в аренду в&nbsp;Москве</h1>
        <p className="body muted">Выберите даты — покажем, какие машины свободны. Или спросите консьержа в&nbsp;чате.</p>
        <div className="search">
          <DateRange from={f.from} to={f.to} onChange={(r) => set(r)} />
          <div className="search-total">
            <span className="cell-label">Срок</span>
            <span className="cell-value">{ok ? plural(days(f.from, f.to), 'сутки', 'суток', 'суток') : '—'}</span>
          </div>
        </div>
        <p className="body-sm muted">Выдача и возврат — в 10:00, аренда считается полными сутками.</p>
      </section>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Кузов">
          {[['', 'Все'], ...Object.entries(BODY_TYPES)].map(([k, v]) => (
            <button key={k} type="button" className="seg" aria-pressed={f.body_type === k} onClick={() => set({ body_type: k })}>{v}</button>
          ))}
        </div>
        <PillSelect label="Цена в сутки" value={f.max_price_per_day} onChange={(v) => set({ max_price_per_day: v })}
          options={[['', 'Любая цена'], ...PRICES.map((p) => [p, `до ${rub(p)}`])]} />
        <PillSelect label="Мощность" value={f.min_power} onChange={(v) => set({ min_power: v })}
          options={[['', 'Любая мощность'], ...POWERS.map((p) => [p, `от ${p} л. с.`])]} />
        {filtered && <button type="button" className="link-btn muted reset" onClick={() => set({ body_type: '', max_price_per_day: '', min_power: '' })}>Сбросить</button>}
      </div>

      {!ok ? <p className="error-text">Дата возврата должна быть позже даты выдачи.</p>
        : error ? <p className="error-text" role="alert">{error}</p>
        : cars === null ? <p className="muted">Загружаем…</p>
        : cars.length === 0 ? <p className="muted">Под эти фильтры машин нет — попробуйте ослабить условия.</p>
        : (
          <>
            <div className="results-head">
              <h2 className="title">Свободно {free} из {cars.length}</h2>
              <PillSelect label="Сортировка" value={f.sort} onChange={(v) => set({ sort: v })} options={Object.entries(SORTS)} plain />
            </div>
            <div className="grid">
              {cars.map((c) => (
                <div key={c.id} className="grid-cell">
                  <CarCard name={c.name} pricePerDay={c.price_per_day} status={c.status}
                    imageSrc={c.image_url || undefined} specs={{ power: c.power, accel: c.accel, seats: c.seats }}
                    onBook={() => navigate(`/cars/${c.id}?${dates}`)} />
                  <Link className="more" to={`/cars/${c.id}?${dates}`}>Характеристики и условия →</Link>
                </div>
              ))}
            </div>
          </>
        )}
    </>
  )
}

function PillSelect({ label, value, onChange, options, plain = false }) {
  return (
    <label className={'pill-select' + (value && !plain ? ' pill-on' : '') + (plain ? ' pill-plain' : '')}>
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  )
}
