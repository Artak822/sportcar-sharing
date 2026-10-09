"""Тестовые данные. Запуск: python -m app.seed [--reset]"""
import sys
from datetime import timedelta

from . import db, services

CARS = [
    # id, name, brand, body_type, price_per_day, power, accel, seats, deposit, status
    ("bmw-z4", "BMW Z4 M40i", "BMW", "cabriolet", 24900, 340, 4.5, 2, 100000, "available"),
    ("mustang", "Ford Mustang GT Convertible", "Ford", "cabriolet", 18900, 450, 4.8, 4, 100000, "available"),
    ("boxster", "Porsche 718 Boxster S", "Porsche", "cabriolet", 29500, 350, 4.4, 2, 150000, "available"),
    ("911", "Porsche 911 Carrera S", "Porsche", "coupe", 45000, 450, 3.7, 4, 200000, "available"),
    ("m4", "BMW M4 Competition", "BMW", "coupe", 32000, 510, 3.9, 4, 150000, "available"),
    ("amg-gt", "Mercedes-AMG GT 55", "Mercedes-Benz", "coupe", 49000, 476, 3.9, 4, 200000, "available"),
    ("rs3", "Audi RS 3 Sedan", "Audi", "sedan", 19500, 400, 3.8, 5, 100000, "available"),
    ("supra", "Toyota GR Supra", "Toyota", "coupe", 16900, 340, 4.3, 2, 80000, "service"),
]

LOCATIONS = [
    ("city", "Москва-Сити", "Пресненская наб., 12", "09:00–22:00"),
    ("aero", "Ленинградский", "Ленинградский пр-т, 39", "10:00–21:00"),
]

EXTRAS = [
    ("full_insurance", "Полная страховка", 3500, "day"),
    ("extra_driver", "Второй водитель", 1000, "day"),
    ("child_seat", "Детское кресло", 500, "day"),
    ("delivery", "Доставка по Москве", 3000, "rental"),
]

USERS = [
    # id, name, email, phone_verified, documents_verified
    (1, "Артак", "demo@pitlane.test", 1, 1),
    (2, "Новый клиент", "new@pitlane.test", 1, 0),
    (3, "Другой клиент", "other@pitlane.test", 1, 1),
]


def seed(conn) -> None:
    if conn.execute("SELECT 1 FROM cars LIMIT 1").fetchone():
        return
    now = services.now()
    created = services.iso(now)
    conn.executemany(
        "INSERT INTO cars (id, name, brand, body_type, price_per_day, power, accel, seats, deposit, status,"
        " mileage_limit_km, min_age, min_experience) VALUES (?,?,?,?,?,?,?,?,?,?, 300, ?, 3)",
        [c + (25 if c[4] >= 40000 else 23,) for c in CARS],
    )
    conn.executemany("INSERT INTO locations VALUES (?,?,?,?)", LOCATIONS)
    conn.executemany("INSERT INTO extras VALUES (?,?,?,?)", EXTRAS)
    conn.executemany(
        "INSERT INTO users (id, name, email, phone_verified, documents_verified, created_at) VALUES (?,?,?,?,?,?)",
        [u + (created,) for u in USERS],
    )
    # Porsche Boxster занят на ближайшие выходные — чтобы в поиске был статус «Занят»
    saturday = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).replace(hour=10, minute=0)
    start, end = saturday - timedelta(hours=16), saturday + timedelta(days=2)
    days, price, deposit = 3, 29500, 150000  # 16 ч + 2 суток → 3 суток
    cur = conn.execute(
        "INSERT INTO bookings (user_id, car_id, location_id, start_at, end_at, days, price_per_day, base,"
        " extras_total, total, deposit, status, created_at) VALUES (3, 'boxster', 'city', ?,?,?,?,?,0,?,?, 'paid', ?)",
        (services.iso(start), services.iso(end), days, price, days * price, days * price, deposit, created),
    )
    conn.execute("UPDATE bookings SET number = ? WHERE id = ?", (services.booking_number(cur.lastrowid), cur.lastrowid))


def main() -> None:
    path = db.db_path()
    if "--reset" in sys.argv:
        import os
        if os.path.exists(path):
            os.remove(path)
    conn = db.connect(path)
    db.init(conn)
    seed(conn)
    print(f"База готова: {path}")


if __name__ == "__main__":
    main()
