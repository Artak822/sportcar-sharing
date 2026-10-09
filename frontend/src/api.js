export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) {
    const e = data?.error
    const message = e?.message || (r.status === 422 ? 'Проверьте поля формы' : 'Сервер не ответил, попробуйте ещё раз')
    throw new ApiError(r.status, e?.code || 'http_' + r.status, message)
  }
  return data
}

function query(params) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  return q.size ? '?' + q : ''
}

export const api = {
  // каталог
  cars: (params) => request('GET', '/api/cars' + query(params)),
  car: (id) => request('GET', `/api/cars/${id}`),
  availability: (id, from, to) => request('GET', `/api/cars/${id}/availability` + query({ from, to })),
  quote: (body) => request('POST', '/api/quote', body),
  extras: () => request('GET', '/api/extras'),
  locations: () => request('GET', '/api/locations'),
  // сессия
  me: () => request('GET', '/api/me'),
  login: (email) => request('POST', '/api/auth/login', { email }),
  logout: () => request('POST', '/api/auth/logout'),
  // брони
  bookings: (status) => request('GET', '/api/bookings' + query({ status })),
  booking: (ref) => request('GET', `/api/bookings/${ref}`),
  pay: (ref) => request('POST', `/api/bookings/${ref}/pay`),
  // действия: черновик → подтверждение. Сайт и агент меняют брони одним путём
  propose: (tool, params) => request('POST', '/api/actions', { tool, params }),
  confirm: (id) => request('POST', `/api/actions/${id}/confirm`),
  cancel: (id) => request('POST', `/api/actions/${id}/cancel`),
  // чат
  chat: () => request('GET', '/api/chat'),
  send: (message, page) => request('POST', '/api/chat', { message, page }),
  resetChat: () => request('DELETE', '/api/chat'),
}
