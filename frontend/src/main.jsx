import './ds.js'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './Layout.jsx'
import { StoreProvider } from './store.jsx'
import Catalog from './pages/Catalog.jsx'
import CarPage from './pages/CarPage.jsx'
import Bookings from './pages/Bookings.jsx'
import BookingPage from './pages/BookingPage.jsx'
import Login from './pages/Login.jsx'
import NotFound from './pages/NotFound.jsx'
import './app.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <StoreProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Catalog />} />
            <Route path="cars/:id" element={<CarPage />} />
            <Route path="bookings" element={<Bookings />} />
            <Route path="bookings/:ref" element={<BookingPage />} />
            <Route path="checkout/:ref" element={<BookingPage />} />
            <Route path="login" element={<Login />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </StoreProvider>
    </BrowserRouter>
  </StrictMode>,
)
