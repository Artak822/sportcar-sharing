export const NBSP = ' '
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export const rub = (n) => n.toLocaleString('ru-RU') + NBSP + '₽'

// Время на сайте — московское в формате API: 2026-10-17T10:00 (как у <input type="datetime-local">)
export function toLocal(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export function humanDt(s) {
  const d = new Date(s)
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()}${NBSP}${MONTHS[d.getMonth()]}, ${s.slice(11, 16)}`
}

export const humanPeriod = (from, to) => `${humanDt(from)} — ${humanDt(to)}`

// Даты без времени: на сайте клиент выбирает только дни, выдача и возврат — в 10:00
export const PICKUP_TIME = '10:00'
export const MONTHS_FULL = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

export const toDay = (d) => toLocal(d).slice(0, 10)
export const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d) }
export const withTime = (day) => `${day.slice(0, 10)}T${PICKUP_TIME}`
export const days = (from, to) => Math.round((parseDay(to) - parseDay(from)) / 864e5)
export function humanDay(s) {
  const d = parseDay(s)
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()}${NBSP}${MONTHS[d.getMonth()]}`
}
export const humanDays = (from, to) => `${humanDay(from)} — ${humanDay(to)}`
export const plural = (n, one, few, many) =>
  `${n}${NBSP}${n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many}`

// Первый день, который ещё можно выбрать: сегодня — только пока не наступили 10:00
export function firstDay(now = new Date()) {
  const d = new Date(now)
  if (toLocal(now).slice(11) >= PICKUP_TIME) d.setDate(d.getDate() + 1)
  return toDay(d)
}

// Даты из адреса: прошедшие или кривые заменяем ближайшими выходными
export function pickDates(params) {
  const from = params.get('from')?.slice(0, 10)
  const to = params.get('to')?.slice(0, 10)
  return from && to && from >= firstDay() && from < to ? { from, to } : nextWeekend()
}

export function nextWeekend(now = new Date()) {
  const sat = new Date(now)
  sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7 || 7))
  const mon = new Date(sat)
  mon.setDate(sat.getDate() + 2)
  return { from: toDay(sat), to: toDay(mon) }
}

export const BODY_TYPES = { coupe: 'Купе', cabriolet: 'Кабриолет', sedan: 'Седан' }

export const BOOKING_STATUS = {
  pending_payment: ['agent', 'Ждёт оплаты'],
  paid: ['available', 'Оплачена'],
  active: ['available', 'Идёт аренда'],
  completed: ['neutral', 'Завершена'],
  cancelled: ['neutral', 'Отменена'],
  expired: ['neutral', 'Истекла'],
}
