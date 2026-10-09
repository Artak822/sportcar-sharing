import { Link } from 'react-router-dom'
import { AgentAction } from '../ds.js'

const STATUS_NOTE = {
  expired: 'Черновик устарел — подготовьте его заново.',
  cancelled: 'Отменено, ничего не изменилось.',
  running: 'Выполняем…',
}

/** Карточка черновика действия. Кнопки идут на сервер напрямую — подтверждает только сам клиент. */
export default function ActionCard({ action, onDecide, link = true }) {
  const { summary, status, result } = action
  const note = status === 'done' ? result?.note
    : status === 'failed' ? action.error
    : STATUS_NOTE[status] ?? summary.note
  const details = summary.details.map((d) => (d.label === 'Итого' ? { ...d, value: <strong className="pl-num">{d.value}</strong> } : d))
  const booking = status === 'done' ? result?.number : null

  return (
    <div className="action-card">
      <AgentAction title={summary.title} status={status === 'expired' ? 'cancelled' : status}
        statusBadge={status !== 'done'} details={details} note={note}
        onConfirm={() => onDecide(action, 'confirm')} onCancel={() => onDecide(action, 'cancel')} />
      {booking && link && <Link className="more" to={`/bookings/${booking}`}>Открыть бронь {booking}</Link>}
    </div>
  )
}

/** Подтвердить или отменить черновик; replace получает новое состояние карточки. */
export async function decide(api, action, verb, replace) {
  replace({ ...action, status: 'running' })
  try {
    const fresh = await api[verb](action.action_id)
    replace(fresh)
    return fresh
  } catch (e) {
    replace({ ...action, status: 'failed', error: e.message })
    return null
  }
}
