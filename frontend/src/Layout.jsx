import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useStore } from './store.jsx'
import ChatWidget from './chat/ChatWidget.jsx'

export default function Layout() {
  const { me, logout } = useStore()
  const navigate = useNavigate()
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('pitlane-theme') || 'auto' } catch { return 'auto' }
  })

  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('pitlane-theme', theme) } catch { /* приватный режим */ }
  }, [theme])

  return (
    <div className="site">
      <header className="header">
        <div className="header-in">
          <Link to="/" className="logo">Pitlane</Link>
          <nav className="nav">
            <NavLink to="/" end>Каталог</NavLink>
            <NavLink to="/bookings">Мои брони</NavLink>
          </nav>
          <div className="header-tools">
            <select className="select" aria-label="Тема" value={theme} onChange={(e) => setTheme(e.target.value)}>
              <option value="auto">Авто</option>
              <option value="light">Светлая</option>
              <option value="dark">Тёмная</option>
            </select>
            {me === undefined ? null : me ? (
              <span className="user">
                <span className="user-name">{me.name}</span>
                <button type="button" className="link-btn" onClick={() => logout().then(() => navigate('/'))}>Выйти</button>
              </span>
            ) : (
              <Link to="/login" className="link-btn">Войти</Link>
            )}
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="footer"><div className="footer-in">Pitlane — учебный проект. Оплата и документы — демо.</div></footer>
      <ChatWidget />
    </div>
  )
}
