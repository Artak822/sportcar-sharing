import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="narrow">
      <h1 className="heading">Страница не найдена</h1>
      <p><Link to="/">Вернуться в каталог</Link></p>
    </div>
  )
}
