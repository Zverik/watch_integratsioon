# Watch Integratsioon

This is a simple Telegram bot that watches the list of language courses
on the Integratsiooni Sihtasutus iseteenindus website.

## How to set up

* Run `python -m venv venv` and then `venv/bin/pip install -r requirements.txt`
* Register a new bot with [BotFather](https://t.me/BotFather).
* Copy `config.sample.py` to `config.py` and put the bot token in there.
* Choose language level and municipality on the website and put their values to `config.py`.
* Run the bot: `venv/bin/python watch_integratsioon.py`

## How to get a cookie

* Log in to the [iseteenindus](https://iseteenindus.integratsioon.ee/my-services).
* Open the browser developer console (F12).
* Select the Network tab.
* Click on anything on the page, e.g. "Add services".
* Choose any file from the list in the developer console.
* Scroll the headers list down to `Cookie:`.
* Copy the cookie value in full, from `JSESSIONID` down to the last character.
* Paste the value into Telegram for the bot.

## Author and License

Written by Ilya Zverev, published under ISC license.
