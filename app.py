#!/usr/bin/env python3
"""Messenger bot server"""

from datetime import datetime
import os
import json
import requests
import base64
from flask import Flask
from flask import request
from lxml import html
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

app = Flask(__name__)

load_dotenv('.env')

FIREBASE_CRED_FILE = os.getenv('FIREBASE_CRED_FILE')
FIREBASE_DB_URL = os.getenv('FIREBASE_DB_URL')
FIREBASE_CRED_DATA = base64.b64decode(os.getenv('FIREBASE_CRED_DATA')).decode('utf-8')
PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN')

with open(FIREBASE_CRED_FILE, 'w') as file:
    json.dump(json.loads(FIREBASE_CRED_DATA), file, indent=2)

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_CRED_FILE)
default_app = firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_URL
})


@app.route('/')
def index():
    """Index"""
    the_time = datetime.today().isoformat()

    return f"""
    <h1>Hello heroku</h1>
    <p>It is currently {the_time}.</p>

    <img src="http://loremflickr.com/600/400">
    """


@app.route('/webhook', methods=['GET'])
def handle_verification():
    """webhook"""
    if request.args['hub.mode'] == 'subscribe' and request.args['hub.verify_token'] == WEBHOOK_TOKEN:
        print('Validating webhook')
        return request.args['hub.challenge'], 200
    else:
        return 'Failed validation. Make sure the validation tokens match.', 403


@app.route('/webhook', methods=['POST'])
def handle_message():
    """
    Handle messages sent by Facebook Messenger to the application
    """
    data = request.get_json()

    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                if messaging_event['message']:
                    sender_id = messaging_event['sender']['id']
                    recipient_id = messaging_event["recipient"]["id"]
                    message = messaging_event['message']

                    print(messaging_event)

                    from_currency = 'SGD'
                    rates_path = 'rates/dbs'
                    ref = db.reference(f'{rates_path}')
                    currencies = ref.get()[from_currency]

                    if 'quick_reply' in message:
                        quick_reply = message['quick_reply']
                        payload = quick_reply['payload']

                        if payload in currencies:
                            send_which_currency(sender_id, currencies, currencies[payload])

                        if payload == 'All':
                            send_which_currency(sender_id,
                                                currencies,
                                                all_currencies(from_currency, currencies))
                    else:
                        send_which_currency(sender_id, currencies)

    return 'OK', 200


def all_currencies(from_currency, currencies):
    response = []

    for to_currency, rate in currencies.items():
        response.append(f'1 {from_currency} is to {rate} {to_currency}')

    return '\n'.join(response)


def send_message(sender_id, message_body):
    return requests.post('https://graph.facebook.com/v2.6/me/messages',
                         params={
                             'access_token': PAGE_ACCESS_TOKEN
                         },
                         headers={'Content-Type': 'application/json'},
                         data=json.dumps({
                             "recipient": {"id": sender_id},
                             "message": message_body
                         }))


def make_quick_reply(content_type, title, payload, image_url=None):
    if content_type == 'text' or content_type == 'location':
        quick_reply_obj = {'content_type': content_type}
    else:
        return None

    if content_type == 'text' and title is not None and payload is not None:
        quick_reply_obj['title'] = title
        quick_reply_obj['payload'] = payload
    else:
        return None

    if image_url is not None:
        quick_reply_obj['image_url'] = image_url

    return quick_reply_obj


def send_which_currency(sender_id, currencies, text=None):
    quick_replies = []

    for currency in currencies:
        quick_replies.append(make_quick_reply('text', currency, currency))

    quick_replies.append(make_quick_reply('text', 'All', 'All'))

    message_body = {
        'text': text if text is not None else 'Hi, which currency rate would you like to know?',
        'quick_replies': quick_replies
    }

    return send_message(sender_id, message_body)


def get_rates():
    """Get rates"""

    page = requests.get('https://www.dbs.com.sg/personal/rates-online/foreign-currency-foreign-exchange.page')
    tree = html.fromstring(page.content)

    names = tree.xpath('//th[contains(@class, "column-1 first")]/span/text()')
    rates = tree.xpath('//td[@data-label="Buying TT" and contains(@class, "column-4")]/text()')

    if len(names) != len(rates):
        raise Exception('The size of "names" and "rates" do not match')

    return dict(zip(names, rates))


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
