# Kvitto Payments API

Тестовое задание Junior Python (FastAPI): API для создания платежей, расчёта промокода и рассрочки, идемпотентности и обработки банковского webhook.

## Стек

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- PostgreSQL
- pytest + httpx

## 1. Создание базы PostgreSQL

В pgAdmin 4 подключитесь к своему серверу PostgreSQL и создайте базу:

```text
kvitto_db
```

Через Query Tool это можно сделать командой:

```sql
CREATE DATABASE kvitto_db;
```

Если база уже создана, этот шаг можно пропустить.

## 2. Установка

### Windows / PowerShell

Создайте виртуальное окружение на Python 3.12:

```powershell
py -3.12 -m venv .venv
```

Если PowerShell разрешает запуск скриптов, активируйте окружение:

```powershell
.\.venv\Scripts\Activate.ps1
```

Если появляется ошибка ExecutionPolicy, разрешите запуск скриптов только для текущего окна PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Установите зависимости:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Настройка подключения к PostgreSQL

Скопируйте `.env.example` в `.env` и замените `YOUR_PASSWORD` на пароль PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/kvitto_db
```

Если имя пользователя, порт или имя базы отличаются, измените их в строке подключения.

Файл `.env` не должен попадать в GitHub: он добавлен в `.gitignore`.

## 4. Запуск

```bash
uvicorn app.main:app --reload
```

После первого запуска приложение автоматически создаст таблицы `tariffs` и `payments`, а также добавит три тарифа:

- `basic` — 990000 коп. (9 900 ₽)
- `standard` — 1990000 коп. (19 900 ₽)
- `premium` — 2990000 коп. (29 900 ₽)

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 5. Тесты

Запуск тестов:

```bash
python -m pytest -q
```

Тесты используют отдельную SQLite-базу как изолированное тестовое хранилище. Рабочее приложение использует PostgreSQL.

## Эндпоинты

### GET /tariffs

```bash
curl http://127.0.0.1:8000/tariffs
```

### POST /payments — обычная оплата

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id":2,"email":"student@example.com","method":"card"}'
```

### POST /payments — промокод

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id":2,"email":"student@example.com","method":"card","promo_code":"kvitto10"}'
```

### POST /payments — рассрочка

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id":2,"email":"student@example.com","method":"installment","installment_months":3}'
```

Для тарифа `standard` без промокода график на 3 месяца:

```text
[663334, 663333, 663333]
```

### POST /payments — Idempotency-Key

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{"tariff_id":2,"email":"student@example.com","method":"card"}'
```

Первый запрос возвращает `201`. Повторный запрос с тем же `Idempotency-Key` возвращает тот же платёж с кодом `200`, не создавая дубликат.

### GET /payments/{id}

```bash
curl http://127.0.0.1:8000/payments/1
```

### POST /webhooks/bank

```bash
curl -X POST http://127.0.0.1:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id":1,"status":"succeeded"}'
```

Допустимые переходы статусов:

- `pending -> succeeded`
- `pending -> failed`
- `succeeded -> refunded`

Остальные переходы возвращают `409` и не меняют статус платежа.

## Структура проекта

```text
kvitto_payments_api/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   └── services.py
├── tests/
│   ├── conftest.py
│   └── test_payments.py
├── .env.example
├── .gitignore
├── AI_LOG.md
├── README.md
└── requirements.txt
```

## Бизнес-логика

- Все суммы в API и базе хранятся целыми числами в копейках; `float` не используется.
- Промокод `KVITTO10` даёт скидку 10%; регистр не важен.
- Для рассрочки доступны сроки 3, 6 и 12 месяцев.
- Если сумма не делится на срок без остатка, лишние копейки добавляются в первые платежи.
- Новый платёж создаётся со статусом `pending`.
- `Idempotency-Key` хранится в таблице `payments` с ограничением `UNIQUE`.
