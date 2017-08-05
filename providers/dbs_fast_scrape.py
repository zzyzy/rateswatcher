#!/usr/bin/env python3
#
#   dbs_fast_scrape (DBS *Fast* Scraping script)
#   Written by zzyzy
#
#   This is the faster version of dbs_scrape, also with more currency rates
#   compared to dbs_scrape. There will also be some currency missing like
#   MYR for some reason. As this is a cheap process, it can run more
#   frequently like in every ten minutes or so.
#

import time
import datetime
import json
import os.path
import base64

from lxml import html
import requests

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

from dotenv import load_dotenv

# Load env settings
load_dotenv('.env')

today = datetime.datetime.utcnow().replace(second=0, microsecond=0)

# Initialize Firebase
FIREBASE_CRED_FILE = os.getenv('FIREBASE_CRED_FILE')
FIREBASE_DB_URL = os.getenv('FIREBASE_DB_URL')
FIREBASE_CRED_DATA = base64.b64decode(os.getenv('FIREBASE_CRED_DATA')).decode('utf-8')

with open(FIREBASE_CRED_FILE, 'w') as file:
    json.dump(json.loads(FIREBASE_CRED_DATA), file, indent=2)

cred = credentials.Certificate(FIREBASE_CRED_FILE)
default_app = firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_URL
})


def get_rates():
    """
    Returns the currency rates from DBS forex page
    """
    page = requests.get('https://www.dbs.com.sg/personal/rates-online/foreign-currency-foreign-exchange.page')
    tree = html.fromstring(page.content)

    names = tree.xpath('//th[contains(@class, "column-1 first")]/span/text()')
    rates = tree.xpath('//td[@data-label="Selling TT/OD" and contains(@class, "column-3")]/text()')
    # rates = tree.xpath('/html/body/div[1]/div[4]/div[1]/div/div/div[2]/div/table/tbody/tr[1]/td[1]')

    if len(names) != len(rates):
        raise Exception(f'The size of "names" ({len(names)}) and "rates" ({len(rates)}) do not match')

    return dict(zip(names, rates))


def map_and_filter_currencies(rates):
    """
    Filters the number of currencies needed, as well
    as shortening the key names
    """
    short_names = {
        'Australian Dollar': 'AUD',
        'US Dollar': 'USD',
        'Sterling Pound': 'GBP'
    }

    mapped_names = {}

    # Also helps to round the currency rate to four decimal places
    for long_name, short_name in short_names.items():
        mapped_names[short_name] = round(1 / float(rates[long_name]), 4)

    return mapped_names


def main():
    """
    The scraping commences
    """
    today_str = today.strftime('%Y%m%d%H%M')
    rates_path = 'rates/dbs'
    history_path = f'history/dbs/{today_str}'
    rates = {
        'SGD': map_and_filter_currencies(get_rates())
    }

    # Save a copy for historical/statistical purposes
    history_ref = db.reference(history_path)
    history_ref.set(rates)

    rates_ref = db.reference(rates_path)
    existing_rates = rates_ref.get()

    for base, quotes in rates.items():
        for quote, rate in quotes.items():
            # Latest rates
            existing_rates[base][quote] = rate

            print(f'1 {base} is to {rate} {quote}')

    rates_ref.set(existing_rates)

    return 0


if __name__ == '__main__':
    main()
