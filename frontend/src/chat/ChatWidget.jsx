import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api.js'
import { useStore } from '../store.jsx'
import Chat from './Chat.jsx'

/** Консьерж поверх любой страницы: кнопка в углу и боковая панель. */
export default function ChatWidget() {
  const { me } = useStore()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(() => {
    try { return sessionStorage.getItem('pitlane-chat') === 'open' } catch { return false }
  })
  const [items, setItems] = useState(null)
  const [error, setError] = useState('')
  const button = useRef(null)

  useEffect(() => {
    try { sessionStorage.setItem('pitlane-chat', open ? 'open' : '') } catch { /* приватный режим */ }
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // История — с сервера: при входе под другим клиентом и при первом открытии
  useEffect(() => {
    setItems(null)
    if (!me || !open) return
    api.chat().then((d) => setItems(d.items), (e) => setError(e.message))
  }, [me?.id, open]) // eslint-disable-line react-hooks/exhaustive-deps

  async function reset() {
    await api.resetChat()
    setItems([])
  }

  function close() {
    setOpen(false)
    button.current?.focus()
  }

  if (pathname === '/login') return null

  return (
    <>
      {!open && (
        <button ref={button} type="button" className="chat-fab" onClick={() => setOpen(true)} aria-label="Открыть чат с консьержем">
          <span className="pl-avatar" aria-hidden="true">AI</span>
          <span>Консьерж</span>
        </button>
      )}
      {open && (
        <aside className="chat-panel" aria-label="Чат с консьержем">
          <header className="chat-top">
            <div className="pl-avatar" aria-hidden="true">AI</div>
            <div>
              <div className="title">Консьерж Pitlane</div>
              <div className="chat-sub body-sm">видит, какую страницу вы смотрите</div>
            </div>
            <button type="button" className="icon-btn" onClick={close} aria-label="Закрыть чат">✕</button>
          </header>
          {me === null ? (
            <div className="chat-empty">
              <p>Консьерж подберёт машину, посчитает стоимость и подготовит бронь. Чтобы начать, войдите.</p>
              <Link className="link-btn" to={`/login?next=${encodeURIComponent(pathname)}`}>Войти</Link>
            </div>
          ) : error ? <p className="chat-empty error-text" role="alert">{error}</p>
            : items === null ? <p className="chat-empty muted">Загружаем…</p>
            : <Chat items={items} setItems={setItems} onReset={reset} />}
        </aside>
      )}
    </>
  )
}
