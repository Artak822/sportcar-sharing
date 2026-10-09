import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

// Сессия клиента и «версия данных»: когда бронь меняется в чате, страницы сайта перечитывают свои данные
const Store = createContext(null)

export function StoreProvider({ children }) {
  const [me, setMe] = useState(undefined) // undefined — проверяем, null — не вошёл
  const [version, setVersion] = useState(0)
  const [page, setPage] = useState(null) // что клиент видит сейчас — подсказка агенту

  const refresh = useCallback(() => api.me().then(setMe, () => setMe(null)), [])
  useEffect(() => { refresh() }, [refresh])

  const value = {
    me, page, setPage, version,
    changed: () => setVersion((v) => v + 1),
    login: async (email) => { await api.login(email); await refresh(); setVersion((v) => v + 1) },
    logout: async () => { await api.logout(); setMe(null); setVersion((v) => v + 1) },
  }
  return <Store.Provider value={value}>{children}</Store.Provider>
}

export const useStore = () => useContext(Store)

/** Страница сообщает агенту, что на ней видно: «Страница машины BMW Z4, даты …». */
export function usePageInfo(text) {
  const { setPage } = useStore()
  useEffect(() => {
    setPage(text)
    return () => setPage(null)
  }, [text, setPage])
}
