import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { AgentMessage, Button, CarCard, Input } from '../ds.js'
import { useStore } from '../store.jsx'
import ActionCard, { decide } from './ActionCard.jsx'

const GREETING = 'Здравствуйте. Я консьерж Pitlane: подберу машину, посчитаю стоимость и подготовлю бронь. Ничего не оформляю без вашего подтверждения.'
const STARTERS = ['Хочу кабриолет на выходные, до 30 тысяч в сутки', 'Какой депозит?', 'Мои брони']

export default function Chat({ items, setItems, onReset }) {
  const { page, changed } = useStore()
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [thinking, setThinking] = useState(false)
  const [error, setError] = useState('')
  const feed = useRef(null)

  useEffect(() => { feed.current.scrollTop = feed.current.scrollHeight }, [items, thinking, error])

  async function send(text) {
    text = text.trim()
    if (!text || thinking) return
    setDraft('')
    setError('')
    setThinking(true)
    const pending = { id: 'pending', type: 'user', text }
    setItems((a) => [...a, pending])
    try {
      const { items: fresh } = await api.send(text, page || undefined)
      setItems((a) => [...a.filter((i) => i !== pending), ...fresh])
    } catch (e) {
      setItems((a) => a.filter((i) => i !== pending))
      setDraft(text)
      setError(e.message)
    } finally {
      setThinking(false)
    }
  }

  function replaceAction(action) {
    setItems((a) => a.map((i) => (i.type === 'action' && i.action.action_id === action.action_id ? { ...i, action } : i)))
  }

  async function onDecide(action, verb) {
    const fresh = await decide(api, action, verb, replaceAction)
    if (fresh?.status === 'done') changed() // страницы сайта перечитают брони
  }

  const lastUser = items.findLastIndex((i) => i.type === 'user')
  const lastReplies = items.findLastIndex((i) => i.type === 'replies')
  const chips = items.length === 0 ? STARTERS : lastReplies > lastUser ? items[lastReplies].options : []

  return (
    <>
      <div className="feed" ref={feed} aria-live="polite">
        <AgentMessage role="agent">{GREETING}</AgentMessage>
        {items.map((item) => <Item key={item.id} item={item} navigate={navigate} onDecide={onDecide} />)}
        {thinking && (
          <AgentMessage role="agent">
            <span className="typing-row">
              <span className="typing" aria-hidden="true"><i /><i /><i /></span>
              <span className="typing-text">Думаю…</span>
            </span>
          </AgentMessage>
        )}
        {error && <p className="error-text block" role="alert">{error}</p>}
      </div>
      {(chips.length > 0 || items.length > 0) && (
        <div className="chips">
          {chips.map((c) => <button key={c} type="button" className="chip" disabled={thinking} onClick={() => send(c)}>{c}</button>)}
          {items.length > 0 && <button type="button" className="chip chip-ghost" disabled={thinking} onClick={onReset}>Новый разговор</button>}
        </div>
      )}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(draft) }}>
        <Input aria-label="Сообщение" placeholder="Напишите, что ищете" value={draft} autoComplete="off"
          maxLength={2000} onChange={(e) => setDraft(e.target.value)} />
        <Button type="submit" variant="primary" disabled={!draft.trim() || thinking}>Отправить</Button>
      </form>
      <div className="hint-line">Консьерж предлагает, вы подтверждаете. Оплату и документы он не видит.</div>
    </>
  )
}

function Item({ item, navigate, onDecide }) {
  switch (item.type) {
    case 'user':
      return <AgentMessage role="user">{item.text}</AgentMessage>
    case 'text':
      return <AgentMessage role="agent">{item.text}</AgentMessage>
    case 'cars':
      return (
        <div className="block cars" role="list" aria-label="Подобранные машины">
          {item.cars.map((c) => (
            <CarCard key={c.id} name={c.name} pricePerDay={c.price_per_day} status={c.status}
              imageSrc={c.image_url || undefined} specs={{ power: c.power, accel: c.accel, seats: c.seats }}
              onBook={() => navigate(`/cars/${c.id}`)} />
          ))}
        </div>
      )
    case 'action':
      return <div className="block"><ActionCard action={item.action} onDecide={onDecide} /></div>
    default:
      return null // replies рисуются чипсами под лентой
  }
}
