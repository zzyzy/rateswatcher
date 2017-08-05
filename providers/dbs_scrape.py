#!/usr/bin/env python3
#
#   dbs_scrape (DBS Scraping script)
#   Written by zzyzy
#
#   As MYR is not listed in the DBS forex page, I took it upon myself
#   to extract the MYR rate from their DBS Remittance and Overseas Transfer
#   page.
#
#   Selenium is used to automate the process:
#   1.  Login
#   2.  Navigating to the intended page
#   3.  As there will be OTP required before actually going into the page,
#       an otphelper was built in Android to help facilitate this process
#   4.  When the otp is sent to my phone, it will pass it to Firebase,
#       and this script will use the otp from Firebase to login
#   5.  Now that we're in, let the scraping commence
#

import os
import time
import re
import json
from datetime import datetime
import base64

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.chrome.options import Options

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

from dotenv import load_dotenv

# Some constants
NOT_IN_SCAPING_PERIOD = 1
INVALID_OTP_RECEIVED = 2

# Load env settings
load_dotenv('.env')

# Check if it is in scraping period, typically 10AM to 1159PM (SG time)
# This is to reduce unnecessary runs
# Note: 1159PM was used instead of 12AM because of difficulty
#       with comparing midnight times
SCRAPE_TIME_FROM = os.getenv('SCRAPE_TIME_FROM')
SCRAPE_TIME_TO = os.getenv('SCRAPE_TIME_TO')

today = datetime.utcnow().replace(second=0, microsecond=0)
scrape_time_from = datetime.strptime(SCRAPE_TIME_FROM, '%H%M')
scrape_time_to = datetime.strptime(SCRAPE_TIME_TO, '%H%M')

if today.time() < scrape_time_from.time() or today.time() > scrape_time_to.time():
    print('Not in scraping period')
    quit(NOT_IN_SCAPING_PERIOD)

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

# Retrieve DBS credentials
DBS_USER_ID = os.getenv('DBS_USER_ID')
DBS_PASSWORD = os.getenv('DBS_PASSWORD')

# Create a new Chrome session
chrome_bin = os.getenv('GOOGLE_CHROME_BIN')
chrome_options = Options()
chrome_options.binary_location = chrome_bin
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
# chrome_options.add_argument('--remote-debugging-port=9222')
chromedriver = 'bin/chromedriver'
chromedriver += '.exe' if os.name == 'nt' else ''
driver = webdriver.Chrome(chromedriver, chrome_options=chrome_options)
driver.implicitly_wait(30)
# driver.maximize_window()

# Navigate to the application home page
driver.get('https://internet-banking.dbs.com.sg')

# Login
input_user_id = driver.find_element_by_xpath('//*[@id="UID"]')
input_password = driver.find_element_by_xpath('//*[@id="PIN"]')
button_login = driver.find_element_by_xpath('/html/body/form[1]/div/div[7]/button[1]')

user_id = DBS_USER_ID
password = DBS_PASSWORD

input_user_id.send_keys(user_id)
input_password.send_keys(password)
button_login.click()

# Mouse over "Transfer" and click "DBS Remit and Overseas Transfer"
driver.switch_to.frame('user_area')

tab_transfer = WebDriverWait(driver, 10).until(
    ec.visibility_of_element_located((By.XPATH, '//*[@id="navigation-bar"]/div/ul/li[2]')))
ActionChains(driver).move_to_element(tab_transfer).perform()

menu_dbs_remit = WebDriverWait(driver, 10).until(
    ec.visibility_of_element_located((By.XPATH, '//*[@id="topnav1"]/div[2]/a[6]')))
menu_dbs_remit.click()

# Press "Get OTP via SMS"
driver.switch_to.frame('iframe1')
button_get_otp = WebDriverWait(driver, 10).until(
    ec.visibility_of_element_located((By.XPATH, '//*[@id="regenerateSMSOTP"]')))
button_get_otp.click()

# OTP will be sent and read by otphelper on user's phone, then updated to Firebase
print(today)
ref = db.reference('otp')
otp = ref.get()
print(otp)

# Wait for awhile, sms may be slow sometimes
time.sleep(10)

otp = ref.get()
print(otp)

# To check if the otp date is valid or not
# If the otp date is before current date time
# it means that it is not updated, thus invalid
otp_date = datetime.strptime(otp['date'], '%Y%m%d%H%M')
if otp_date < today:
    print('Invalid otp. Exiting...')
    quit(INVALID_OTP_RECEIVED)

# Key in the OTP retrieved from Firebase
input_otp = WebDriverWait(driver, 10).until(ec.visibility_of_element_located((By.XPATH, '//*[@id="SMSLoginPin"]')))
button_otp_login = WebDriverWait(driver, 10).until(
    ec.visibility_of_element_located((By.XPATH, '//*[@id="submitButton"]')))
input_otp.send_keys(otp['text'])
button_otp_login.click()

# Patterns to look for
patterns = {
    'SGD': {
        'MYR': r'(\d*.?\d*) SGD (\d*.?\d*) MYR',
        'AUD': r'(\d*.?\d*) SGD (\d*.?\d*) AUD',
        'GBP': r'(\d*.?\d*) SGD (\d*.?\d*) GBP',
        'USD': r'(\d*.?\d*) SGD (\d*.?\d*) USD',
    }
}

rates = {}

for base, pattern_map in patterns.items():
    for quote, pattern in pattern_map.items():
        # Scroll to bottom to make the buttons visible to be clicked
        driver.execute_script('window.scrollTo(0, document.documentElement.offsetHeight - window.innerHeight);', '')
        # Give sometime to scroll
        time.sleep(0.5)
        button_rate = WebDriverWait(driver, 10).until(
            ec.visibility_of_element_located((By.XPATH, f'//*[@id="{quote}"]')))
        button_rate.click()
        print(f'Clicked {quote}')

        # Click the rate buttons and use regex to capture the rates
        span_rates = WebDriverWait(driver, 10).until(
            ec.visibility_of_element_located((By.XPATH, '//*[@id="exchgRate"]')))
        match = re.match(pattern, span_rates.text)

        if match:
            if base not in rates:
                rates[base] = {quote: float(match.group(2))}
            else:
                rates[base][quote] = float(match.group(2))

# Close the browser window
driver.quit()

# Write rates to json file or Firebase
today_str = today.strftime('%Y%m%d%H%M')
rates_path = 'rates/dbs'
history_path = f'history/dbs/{today_str}'

# os.makedirs(rates_path, exist_ok=True)
# # Latest rates
# with open(f'{rates_path}/dbs_rates.json', 'w') as fp:
#     json.dump(rates, fp, indent=2)
#
# # Keep a historical file for statistical purposes
# with open(f'{rates_path}/dbs_rates_{today}.json', 'w') as fp:
#     json.dump(rates, fp, indent=2)

rates_ref = db.reference(rates_path)
history_ref = db.reference(history_path)

for base, quotes in rates.items():
    base_ref = rates_ref.child(base)
    history_base_ref = history_ref.child(base)

    for quote, rate in quotes.items():
        # Latest rates
        quote_ref = base_ref.child(quote)
        quote_ref.set(rate)

        # Another copy for historical/statiscal purposes
        quote_ref = history_base_ref.child(quote)
        quote_ref.set(rate)

        print(f'1 {base} is to {rate} {quote}')
