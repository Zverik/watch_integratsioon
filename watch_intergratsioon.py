#!/usr/bin/env python3
import requests
import re
import asyncio
import config
from aiogram import Bot, Dispatcher, executor, types
from bs4 import BeautifulSoup


subscribed: set[int] = set()
cookie = ''
polling = True
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot=bot)
last_text = ''
BASE_URL = 'https://iseteenindus.integratsioon.ee/'


async def send(text: str):
    global last_text
    if text == last_text:
        return
    last_text = text
    for u in subscribed:
        await bot.send_message(u, text)


async def poll_integratsioon():
    global polling, cookie
    polling = True
    url = BASE_URL + 'service/search'
    post_data = {
        'serviceTypeCode': "Keelekursus",
        'proficiencyLevelCode': config.LANG_LEVEL,
        'municipalityCode': config.MUNICIPALITY,
        'serviceEventStartDateFrom': "",
        'serviceEventStartDateUntil': "",
    }
    while polling:
        resp = requests.post(url, data=post_data, headers={'Cookie': cookie})
        if resp.status_code != 200:
            await send('Got error code {resp.status_code}.')
        else:
            text = resp.text
            if '<title>Sisenemine</title>' in text:
                await send('Needs new cookie:\n' + BASE_URL)
            elif re.search(r'alert[^"]*">No results', text):
                await send('No results')
            else:
                soup = BeautifulSoup(resp.text, 'html.parser')
                table = soup.find('table', class_='table')
                if not table:
                    await send('There are openings, but could not find the table.')
                else:
                    results = []
                    for tr in table.find_all('tr'):
                        tds = tr.find_all('td')
                        if len(tds) < 4:
                            continue
                        time = re.sub(r'\s+', ' ', tds[0].get_text()).strip()
                        place = re.sub(r'\s+', ' ', tds[2].get_text()).strip()
                        free = re.sub(r'\s+', ' ', tds[3].get_text()).strip()
                        results.append(f'* {time} at {place}, free {free}')
                    await send('There are openings:\n\n' + '\n'.join(results))
        await asyncio.sleep(config.POLLING_INTERVAL)


@dp.message_handler()
async def handle_msg(message: types.Message):
    global cookie, last_text

    if message.from_user.id not in subscribed:
        last_text = ''
        subscribed.add(message.from_user.id)
        await message.answer('Added you to the list.')

    text = message.text.strip()
    if 'JSESSIONID' in text:
        if text.startswith('Cookie'):
            text = text[6:].lstrip(':').strip()
        cookie = text
        last_text = ''
        await message.answer('Saved new cookie.')


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_integratsioon())
    executor.start_polling(dp)
