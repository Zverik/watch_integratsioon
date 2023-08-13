import aiosqlite
import config
import logging
from aiogram import types
from datetime import datetime
from typing import Optional


_db = None


class User:
    fields = 'user_id, level, last_active'

    def __init__(self, row):
        self.user_id = row[0]
        self.level = row[1]
        self.last_active = datetime.fromtimestamp(row[2])


async def get_db():
    global _db
    if _db is not None and _db._running:
        return _db
    _db = await aiosqlite.connect(config.DATABASE)
    _db.row_factory = aiosqlite.Row
    exists_query = ("select count(*) from sqlite_master where type = 'table' "
                    "and name = 'users'")
    async with _db.execute(exists_query) as cursor:
        has_tables = (await cursor.fetchone())[0] == 1
    if not has_tables:
        logging.info('Creating tables')
        q = '''\
        create table users (
            user_id integer primary key,
            level text,
            last_active integer
        )'''
        await _db.execute(q)
        await _db.commit()
    return _db


async def on_shutdown(dp):
    if _db is not None and _db._running:
        await _db.close()


async def find_user(user: types.User) -> User:
    db = await get_db()
    cursor = await db.execute(
        f'select {User.fields} from users where user_id = ?', (user.id,))
    row = await cursor.fetchone()
    u = None if not row else User(row)
    if u:
        await update_active(user)
    return u


async def create_user(user: types.User) -> User:
    db = await get_db()
    await db.execute(
        'insert into users (user_id, last_active) values (?, ?)',
        (user.id, datetime.now().timestamp()))
    await db.commit()
    return await find_user(user)


async def update_active(user: types.User):
    db = await get_db()
    await db.execute(
        'update users set last_active = ? where user_id = ?',
        (datetime.now().timestamp(), user.id))
    await db.commit()


async def delete_user(user: types.User):
    db = await get_db()
    await db.execute('delete from users where user_id = ?', (user.id,))
    await db.commit()


async def set_level(user: types.User, level: Optional[str]):
    db = await get_db()
    if level == '':
        level = None
    await db.execute(
        'update users set level = ? where user_id = ?', (level, user.id))
    await db.commit()


async def get_users(level: str):
    db = await get_db()
    cursor = await db.execute(
        f'select {User.fields} from users where level = ? or level is null', (level,))
    return [User(row) async for row in cursor]
