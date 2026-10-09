import { useEffect, useRef, useState } from 'react'
import { MONTHS_FULL, days, firstDay, humanDay, parseDay, plural, toDay } from '../format.js'

const WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

/** Две ячейки «Забираете / Возвращаете» и календарь: первый клик — начало, второй — конец. */
export default function DateRange({ from, to, onChange }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState({ from, to })
  const [hover, setHover] = useState(null)
  const [month, setMonth] = useState(() => startOfMonth(parseDay(from)))
  const [count, setCount] = useState(2)
  const root = useRef(null)
  const today = toDay(new Date())
  const min = firstDay()

  function show(field) {
    setDraft(field === 'from' ? { from: null, to: null } : { from, to: null })
    setMonth(startOfMonth(parseDay(field === 'from' ? from : to)))
    // Два месяца, если справа хватает места; в узкой колонке и на телефоне — один
    const left = root.current.getBoundingClientRect().left
    setCount(window.innerWidth - left >= 680 ? 2 : 1)
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    const onDown = (e) => !root.current?.contains(e.target) && setOpen(false)
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  function pick(day) {
    if (!draft.from || day <= draft.from) {
      setDraft({ from: day, to: null })
      return
    }
    onChange({ from: draft.from, to: day })
    setOpen(false)
  }

  // Пока выбирают, ячейки показывают черновик; закрыли не выбрав конец — остаётся прежний диапазон
  const shown = open ? draft : { from, to }
  const end = draft.from && !draft.to && hover > draft.from ? hover : draft.to

  return (
    <div className="daterange" ref={root}>
      <button type="button" className={'cell' + (open && !draft.from ? ' cell-active' : '')} onClick={() => show('from')}
        aria-haspopup="dialog" aria-expanded={open}>
        <span className="cell-label">Забираете</span>
        <span className="cell-value">{shown.from ? humanDay(shown.from) : 'Дата выдачи'}</span>
      </button>
      <button type="button" className={'cell' + (open && draft.from ? ' cell-active' : '')} onClick={() => show('to')}
        aria-haspopup="dialog" aria-expanded={open}>
        <span className="cell-label">Возвращаете</span>
        <span className="cell-value">{shown.to ? humanDay(shown.to) : 'Дата возврата'}</span>
      </button>

      {open && (
        <div className="calendar" role="dialog" aria-label="Выбор дат аренды">
          <div className="calendar-head">
            <button type="button" className="cal-nav" aria-label="Предыдущий месяц"
              disabled={month <= startOfMonth(new Date())} onClick={() => setMonth(addMonths(month, -1))}>‹</button>
            <span className="cal-hint body-sm">{draft.from ? 'Выберите день возврата' : 'Выберите день выдачи'}</span>
            <button type="button" className="cal-nav" aria-label="Следующий месяц" onClick={() => setMonth(addMonths(month, 1))}>›</button>
          </div>
          <div className="calendar-months">
            {Array.from({ length: count }, (_, i) => (
              <Month key={i} month={addMonths(month, i)} today={today} min={min} from={draft.from} to={end}
                onPick={pick} onHover={setHover} />
            ))}
          </div>
          <div className="calendar-foot body-sm">
            <span className="muted">Выдача и возврат в 10:00</span>
            {draft.from && end && <strong>{plural(days(draft.from, end), 'сутки', 'суток', 'суток')}</strong>}
          </div>
        </div>
      )}
    </div>
  )
}

function Month({ month, today, min, from, to, onPick, onHover }) {
  const first = (month.getDay() + 6) % 7 // понедельник — первый
  const total = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const cells = [...Array(first).fill(null), ...Array.from({ length: total }, (_, i) => toDay(new Date(month.getFullYear(), month.getMonth(), i + 1)))]
  return (
    <div className="month">
      <div className="month-title">{MONTHS_FULL[month.getMonth()]} {month.getFullYear()}</div>
      <div className="month-grid" onMouseLeave={() => onHover(null)}>
        {WEEK.map((w, i) => <span key={w} className={'wd' + (i >= 5 ? ' wd-end' : '')}>{w}</span>)}
        {cells.map((d, i) => d === null ? <span key={'e' + i} /> : (
          <button key={d} type="button" disabled={d < min}
            className={'day' + (d === from ? ' day-start' : '') + (d === to ? ' day-end' : '')
              + (from && to && d > from && d < to ? ' day-in' : '') + (d === today ? ' day-today' : '')}
            onClick={() => onPick(d)} onMouseEnter={() => onHover(d)}
            aria-label={humanDay(d)} aria-pressed={d === from || d === to}>
            {Number(d.slice(8))}
          </button>
        ))}
      </div>
    </div>
  )
}

const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1)
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1)
