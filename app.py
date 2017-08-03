#!/usr/bin/env python3
"""Messenger bot server"""

from datetime import datetime
import os
import json
import requests
from flask import Flask
from flask import request
from lxml import html
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv('.env')

PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN')


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

                    dbs_rates_json = 'rates/dbs/dbs_rates.json'
                    if os.path.isfile(dbs_rates_json):
                        with open(dbs_rates_json) as file:
                            currencies = json.load(file)['SGD']
                    else:
                        return 'FILE NOT FOUND', 500

                    if 'quick_reply' in message:
                        quick_reply = message['quick_reply']
                        payload = quick_reply['payload']

                        if payload in currencies:
                            send_which_currency(sender_id, currencies, currencies[payload])
                    else:
                        send_which_currency(sender_id, currencies)

    return 'OK', 200


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
