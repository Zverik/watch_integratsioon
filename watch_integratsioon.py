#!/usr/bin/env python3
import logging
import requests
import re
import db
import asyncio
import config
from collections import defaultdict
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.callback_data import CallbackData
from typing import List, Dict
from bs4 import BeautifulSoup


bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot=bot)
BASE_URL = 'https://iseteenindus.integratsioon.ee/'
LEVEL_CB = CallbackData('level', 'level')
ALL_LEVELS = ['A2', 'B1', 'B2', 'C1']
HTML = types.ParseMode.HTML


class Course:
    def __init__(self, time, place, free):
        self.time = time
        self.place = place
        self.free = free

    @property
    def line(self):
        return f'* {self.time} at {self.place} (free {self.free})'

    def __eq__(self, other):
        return isinstance(other, Course) and (self.time, self.place) == (other.time, other.place)

    def __hash__(self):
        return hash((self.time, self.place))

    def __str__(self):
        return f'Course("{self.time}", "{self.place}", "{self.free}")'


class State:
    def __init__(self):
        self.polling = True
        self.log_needed = False
        self.last_text = ''
        self.cookie = ''
        self.last_courses = {}


state = State()


async def send_update(level: str, courses: List[Course]):
    global state

    lc = state.last_courses.get(level, set())
    if len(lc) == len(courses):
        equal = True
        for c in courses:
            if c not in lc:
                equal = False
                break
        if equal:
            return

    # Find change from the last
    text = None
    if not courses and lc:
        text = f'No more openings for level {level}.'
    elif courses:
        courses_str = '\n'.join(c.line for c in courses)
        opening = 'is an opening' if len(courses) == 1 else f'are {len(courses)} openings'
        text = f'There {opening} for level {level}:\n\n{courses_str}'
        if not lc:
            text = f'<a href="{BASE_URL}">Quick!</a> ' + text

    state.last_courses[level] = set(courses)
    if text:
        for u in await db.get_users(level):
            await bot.send_message(u.user_id, text, parse_mode=HTML)


async def send_admin(text: str):
    global state
    if text == state.last_text:
        return
    state.last_text = text
    await bot.send_message(config.ADMIN_ID, text)


class ParseException(Exception):
    pass


def parse_website(text: str) -> dict:
    if re.search(r'alert[^"]*">[^<]*[nN]o results', text):
        return {}

    soup = BeautifulSoup(text, 'html.parser')
    table = soup.find('table', class_='table')
    if not table:
        logging.warning('Could not find the openings table: %s', str(soup))
        raise ParseException('There are openings, but could not find the table.')

    courses = defaultdict(list)
    for tr in table.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 4:
            continue
        time = re.sub(r'\s+', ' ', tds[0].get_text()).strip()
        service = re.sub(r'\s+', ' ', tds[1].get_text()).strip()
        place = re.sub(r'\s+', ' ', tds[2].get_text()).strip()
        free = re.sub(r'\s+', ' ', tds[3].get_text()).strip()
        m = re.search(r'\s([ABC][12])', service)
        if not m:
            raise ParseException(f'Cannot parse service for level: "{service}"')
        else:
            courses[m.group(1)].append(Course(time, place, free))
    return courses


def query_integratsioon(type_code='Keelekursus', municipality=None) -> str:
    global state
    url = BASE_URL + 'service/search'
    post_data = {
        'serviceTypeCode': type_code,
        'proficiencyLevelCode': '',
        'municipalityCode': config.MUNICIPALITY if municipality is None else municipality,
        'serviceEventStartDateFrom': "",
        'serviceEventStartDateUntil': "",
    }
    resp = requests.post(url, data=post_data, headers={'Cookie': state.cookie})
    if resp.status_code != 200:
        raise ParseException('Got error code {resp.status_code}.')
    text = resp.text
    if '<title>Sisenemine</title>' in text:
        state.cookie = ''
        raise ParseException('Needs new cookie:\n' + BASE_URL)
    return text


async def poll_integratsioon():
    global state
    state.polling = True
    while state.polling:
        if not state.cookie:
            # No point in doing the requests if we don't have the cookie.
            await send_admin('Needs new cookie:\n' + BASE_URL)
        else:
            try:
                text = query_integratsioon()
                courses = parse_website(text)
                for level in ALL_LEVELS:
                    await send_update(level, courses.get(level, []))
                if state.log_needed:
                    logging.info(text)
                    courses_len = sum([len(c) for c in courses.values()])
                    await send_admin(f'Check the log for {courses_len} openings!')
                    state.log_needed = False
            except ParseException as e:
                await send_admin(str(e))
            except Exception as e:
                await send_admin(f'Exception happened: {e}')
        await asyncio.sleep(config.POLLING_INTERVAL)


@dp.message_handler(commands=['start'])
async def welcome(message: types.Message):
    user = await db.find_user(message.from_user)
    if not user:
        user = await db.create_user(message.from_user)
        await message.answer(
            'Hi! This bot will notify you the moment anything changes '
            'on the Integratsioon website. Send /stop to unsubscribe.')
    return await level_question(message)


@dp.message_handler(commands=['stop'])
async def unsubscribe(message: types.Message):
    user = await db.find_user(message.from_user)
    if not user:
        return await message.answer('You are already not subscribed.')
    await db.delete_user(message.from_user)
    await message.answer('Unsubscribed you. Send /start to subscribe again.')


def make_level_keyboard():
    kbd = types.InlineKeyboardMarkup(row_width=len(ALL_LEVELS))
    kbd.add(
        *[types.InlineKeyboardButton(level, callback_data=LEVEL_CB.new(level=level))
          for level in ALL_LEVELS],
    )
    kbd.add(types.InlineKeyboardButton('All levels', callback_data=LEVEL_CB.new(level='')))
    return kbd


@dp.message_handler(commands=['level'])
async def level_question(message: types.Message):
    user = await db.find_user(message.from_user)
    if not user:
        return await welcome(message)
    level = 'all language levels' if not user.level else f'level {user.level}'
    await bot.send_message(
        message.from_user.id,
        f'You are subscribed to {level}. Choose another if you want.',
        parse_mode=HTML,
        reply_markup=make_level_keyboard())


@dp.callback_query_handler(LEVEL_CB.filter())
async def handle_level(query: types.CallbackQuery, callback_data: Dict[str, str]):
    user = await db.find_user(query.from_user)
    if not user:
        await query.answer('Cannot find you, try /start')
        return
    new_level = callback_data['level'] or None
    await db.set_level(query.from_user, new_level)
    await bot.send_message(
        query.from_user.id,
        f'Watching for courses for language level {new_level or "any"}')


@dp.message_handler(commands=['log'])
async def print_log(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    global state
    state.log_needed = True
    await message.answer('Go check the logs on server with sudo journalctl -u integratsioon')


@dp.message_handler(commands=['health'])
async def check_health(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        text = query_integratsioon(type_code='Suhtluspraktika', municipality='')
        dcourses = parse_website(text)
        if not dcourses:
            text = query_integratsioon(type_code='', municipality='')
            dcourses = parse_website(text)
        courses = sum(dcourses.values(), start=[])
        courses_str = '\n'.join(c.line for c in courses)
        resp = f'There are {len(courses)} openings:\n\n{courses_str or "nothing"}'
        await message.answer(resp)
    except ParseException as e:
        await send_admin(str(e))
    except Exception as e:
        await send_admin(f'Exception happened: {e}')


@dp.message_handler()
async def handle_msg(message: types.Message):
    if message.from_user.is_bot:
        return
    if message.from_user.id != config.ADMIN_ID:
        user = await db.find_user(message.from_user)
        if not user:
            await message.answer('Send /start to subscribe.')
        return

    global state

    text = message.text.strip()
    if 'JSESSIONID' in text:
        if text.startswith('Cookie'):
            text = text[6:].lstrip(':').strip()
        state.cookie = text
        await message.answer('Saved new cookie.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_integratsioon())
    executor.start_polling(dp, skip_updates=True, on_shutdown=db.on_shutdown)
