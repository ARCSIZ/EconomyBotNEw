# COTTAVEN RP Economy Bot

Полнофункциональный Telegram-бот экономики для проекта COTTAVEN RP, город Лос-Анджелес.

## Возможности

- личный кабинет, баланс, банковский счёт и виртуальная карта;
- переводы, вклады, кредиты и история баланса;
- крипто-кошелёк BTC / ETH / USDT с обменом и переводами;
- штрафы, государственная казна, суд, законопроекты и указы;
- фракции, компании, бизнесы, недвижимость, транспорт и страховки;
- биржа компаний, казино, уведомления, топ игроков;
- супергруппы: публичные ответы для профиля и баланса, приватные финансовые разделы отправляются в ЛС;
- антиспам 3 секунды на пользователя и команду в группах;
- APScheduler для фоновых начислений и проверок.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=ваш_telegram_id
DATABASE_PATH=cottaven.sqlite3
NEWS_CHANNEL_ID=-1001234567890
USE_PREMIUM_EMOJI=0
```

`USE_PREMIUM_EMOJI=0` оставляет обычные эмодзи и предотвращает ошибку Telegram `ENTITY_TEXT_INVALID`. Если ваши premium emoji ID точно принимаются Bot API, можно поставить `USE_PREMIUM_EMOJI=1`.

Проверка проекта без подключения к Telegram:

```bash
python bot.py --dry-run
```

Запуск:

```bash
python bot.py
```

При запуске бот инициализирует SQLite-базу, создаёт базовые налоговые ставки и правительственную фракцию, регистрирует список команд Telegram и запускает планировщик фоновых задач.

## Команды

`/start`, `/profile`, `/balance`, `/pay`, `/bank`, `/crypto`, `/fines`, `/history`, `/faction`, `/factions`, `/company`, `/companies`, `/businesses`, `/market`, `/realestate`, `/vehicles`, `/stocks`, `/casino`, `/insurance`, `/court`, `/top`, `/gov`, `/whois`, `/settings`, `/help`, `/admin`.

Все пользовательские сообщения и кнопки написаны на русском языке и отправляются в HTML-режиме.
