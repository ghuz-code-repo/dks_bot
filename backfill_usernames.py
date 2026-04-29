"""
Одноразовый скрипт: подтягивает Telegram @username для всех договоров,
у которых уже сохранён telegram_id, но не сохранён username.

Использование (локально или в контейнере):
    python backfill_usernames.py            # обычный режим
    python backfill_usernames.py --dry-run  # только показать, не сохранять
    python backfill_usernames.py --force    # перезаписать существующие username

Внутри docker:
    docker compose exec dks_bot python backfill_usernames.py
"""

import argparse
import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from config import BOT_TOKEN
from database.models import Contract
from database.session import SessionLocal, init_db
from utils.language import build_tg_href


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_usernames")


async def fetch_username(bot: Bot, telegram_id: int) -> tuple[str | None, str | None]:
    """Возвращает (username, error). username может быть None, если у юзера его нет."""
    try:
        chat = await bot.get_chat(telegram_id)
        return chat.username, None
    except TelegramRetryAfter as e:
        logger.warning("Rate limit, ждём %s сек.", e.retry_after)
        await asyncio.sleep(e.retry_after + 1)
        return await fetch_username(bot, telegram_id)
    except TelegramAPIError as e:
        return None, str(e)


async def main(dry_run: bool, force: bool) -> int:
    init_db()  # на случай, если миграция ещё не применена

    with SessionLocal() as session:
        query = session.query(Contract).filter(Contract.telegram_id.isnot(None))
        if not force:
            query = query.filter(
                (Contract.username.is_(None)) | (Contract.username == "")
                | (Contract.href.is_(None)) | (Contract.href == "")
            )
        contracts = query.all()

        # Уникальные telegram_id, чтобы не дёргать API дважды
        unique_ids = sorted({c.telegram_id for c in contracts})
        logger.info(
            "Найдено %d договоров, %d уникальных telegram_id для обработки",
            len(contracts),
            len(unique_ids),
        )

        if not unique_ids:
            logger.info("Нечего делать.")
            return 0

        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties())
        username_by_id: dict[int, str | None] = {}
        errors: dict[int, str] = {}

        try:
            for i, tg_id in enumerate(unique_ids, 1):
                username, err = await fetch_username(bot, tg_id)
                if err:
                    errors[tg_id] = err
                    logger.warning("[%d/%d] tg_id=%s: ошибка: %s", i, len(unique_ids), tg_id, err)
                else:
                    username_by_id[tg_id] = username
                    if username:
                        logger.info(
                            "[%d/%d] tg_id=%s -> @%s (https://t.me/%s)",
                            i, len(unique_ids), tg_id, username, username,
                        )
                    else:
                        # У пользователя нет публичного @username — даём tg:// ссылку.
                        # Она кликабельна только внутри Telegram-клиента.
                        logger.info(
                            "[%d/%d] tg_id=%s -> <без username> | tg://user?id=%s",
                            i, len(unique_ids), tg_id, tg_id,
                        )
                # Бережём rate limit (Telegram: ~30 запросов/сек, get_chat дешёвый, но не злоупотребляем)
                await asyncio.sleep(0.05)
        finally:
            await bot.session.close()

        updated = 0
        for c in contracts:
            if c.telegram_id not in username_by_id:
                continue
            new_username = username_by_id[c.telegram_id]
            new_href = build_tg_href(c.telegram_id, new_username)

            changed = False
            # username не затираем пустотой, если у пользователя его нет
            if new_username and c.username != new_username:
                c.username = new_username
                changed = True
            # href можно проставить всегда (хотя бы tg://user?id=...)
            if new_href and c.href != new_href:
                c.href = new_href
                changed = True
            if changed:
                updated += 1

        if dry_run:
            logger.info("DRY-RUN: было бы обновлено %d договоров. Изменения НЕ сохранены.", updated)
            session.rollback()
        else:
            session.commit()
            logger.info("Обновлено %d договоров.", updated)

        if errors:
            logger.warning(
                "Ошибки при опросе %d telegram_id (например, бот не общался с пользователем "
                "или пользователь заблокировал бота). Примеры: %s",
                len(errors),
                list(errors.items())[:5],
            )

        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="не сохранять изменения в БД")
    parser.add_argument(
        "--force",
        action="store_true",
        help="перезаписать username даже у договоров, где он уже есть",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run, force=args.force)))
