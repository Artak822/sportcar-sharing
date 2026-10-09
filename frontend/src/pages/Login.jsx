import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../store.jsx'

// Демо-вход без пароля — только для учебного проекта (см. backend/README.md)
const DEMO_USERS = [
  { email: 'demo@pitlane.test', label: 'Демо-клиент', note: 'Документы проверены, можно бронировать' },
  { email: 'new@pitlane.test', label: 'Новый клиент', note: 'Права не загружены — бронь не подтвердится' },
  { email: 'other@pitlane.test', label: 'Другой клиент', note: 'Держит Porsche Boxster на выходные' },
]

export default function Login() {
  const { login } = useStore()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')
  const next = params.get('next')?.startsWith('/') ? params.get('next') : '/'

  async function enter(email) {
    setError('')
    try {
      await login(email)
      navigate(next, { replace: true })
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="narrow">
      <h1 className="heading">Вход</h1>
      <p className="muted">Выберите тестового клиента — пароль не нужен.</p>
      <div className="login-list">
        {DEMO_USERS.map((u) => (
          <button key={u.email} type="button" className="login-user" onClick={() => enter(u.email)}>
            <span className="title">{u.label}</span>
            <span className="body-sm muted">{u.email}</span>
            <span className="body-sm muted">{u.note}</span>
          </button>
        ))}
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  )
}
