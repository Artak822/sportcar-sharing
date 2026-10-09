-- Pitlane: схема базы. Деньги — целые рубли, время — ISO-строки 'YYYY-MM-DDTHH:MM' (московское).

CREATE TABLE IF NOT EXISTS users (
  id                 INTEGER PRIMARY KEY,
  name               TEXT NOT NULL,
  email              TEXT NOT NULL UNIQUE,
  phone_verified     INTEGER NOT NULL DEFAULT 0,
  documents_verified INTEGER NOT NULL DEFAULT 0,
  created_at         TEXT NOT NULL
);

-- scope: web — браузер клиента, agent — токен, который получает чат-агент.
-- Агентский токен не может подтверждать действия и платить.
CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  scope      TEXT NOT NULL CHECK (scope IN ('web', 'agent')),
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  address TEXT NOT NULL,
  hours   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cars (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  brand             TEXT NOT NULL,
  body_type         TEXT NOT NULL CHECK (body_type IN ('coupe', 'cabriolet', 'sedan')),
  price_per_day     INTEGER NOT NULL CHECK (price_per_day > 0),
  power             INTEGER NOT NULL,
  accel             REAL NOT NULL,
  seats             INTEGER NOT NULL,
  deposit           INTEGER NOT NULL,
  mileage_limit_km  INTEGER NOT NULL,
  min_age           INTEGER NOT NULL,
  min_experience    INTEGER NOT NULL,
  image_url         TEXT,
  -- «Занят» не хранится: он считается по броням на конкретные даты
  status            TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'service'))
);

CREATE TABLE IF NOT EXISTS extras (
  code  TEXT PRIMARY KEY,
  name  TEXT NOT NULL,
  price INTEGER NOT NULL,
  per   TEXT NOT NULL CHECK (per IN ('day', 'rental'))
);

CREATE TABLE IF NOT EXISTS bookings (
  id            INTEGER PRIMARY KEY,
  number        TEXT UNIQUE,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  car_id        TEXT NOT NULL REFERENCES cars(id),
  location_id   TEXT NOT NULL REFERENCES locations(id),
  start_at      TEXT NOT NULL,
  end_at        TEXT NOT NULL,
  days          INTEGER NOT NULL,
  price_per_day INTEGER NOT NULL,
  base          INTEGER NOT NULL,
  extras_total  INTEGER NOT NULL,
  total         INTEGER NOT NULL,
  deposit       INTEGER NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('pending_payment', 'paid', 'active', 'completed', 'cancelled', 'expired')),
  hold_until    TEXT,
  created_at    TEXT NOT NULL,
  CHECK (end_at > start_at)
);
CREATE INDEX IF NOT EXISTS bookings_car_period ON bookings (car_id, start_at, end_at);
CREATE INDEX IF NOT EXISTS bookings_user ON bookings (user_id);

-- Цена услуги фиксируется на момент брони
CREATE TABLE IF NOT EXISTS booking_extras (
  booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  code       TEXT NOT NULL REFERENCES extras(code),
  price      INTEGER NOT NULL,
  PRIMARY KEY (booking_id, code)
);

-- Черновики действий агента. Выполняются только после подтверждения клиентом.
CREATE TABLE IF NOT EXISTS actions (
  id         TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  tool       TEXT NOT NULL,
  params     TEXT NOT NULL,          -- JSON
  summary    TEXT NOT NULL,          -- JSON: title, details, note — то, что рисует AgentAction
  status     TEXT NOT NULL CHECK (status IN ('proposed', 'running', 'done', 'failed', 'cancelled', 'expired')),
  result     TEXT,                   -- JSON
  error      TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS actions_user ON actions (user_id);

CREATE TABLE IF NOT EXISTS manager_requests (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  topic      TEXT NOT NULL,
  message    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
