"""
DBS Scraping Script
"""

import os
import time
import re
import json
import datetime
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

# Load env settings
load_dotenv('.env')

FIREBASE_CRED_FILE = os.getenv('FIREBASE_CRED_FILE')
FIREBASE_DB_URL = os.getenv('FIREBASE_DB_URL')
DBS_USER_ID = os.getenv('DBS_USER_ID')
DBS_PASSWORD = os.getenv('DBS_PASSWORD')
FIREBASE_CRED_DATA = base64.b64decode(os.getenv('FIREBASE_CRED_DATA')).decode('utf-8')

with open(FIREBASE_CRED_FILE, 'w') as file:
  json.dump(json.loads(FIREBASE_CRED_DATA), file, indent=2)

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_CRED_FILE)
default_app = firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_URL
})

# Create a new Chrome session
chrome_options = Options()
chrome_options.add_argument("--headless")
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
ref = db.reference('otp')
print(ref.get())

# Wait for awhile, sms may be slow sometimes
time.sleep(10)

# Key in the OTP retrieved from Firebase
input_otp = WebDriverWait(driver, 10).until(ec.visibility_of_element_located((By.XPATH, '//*[@id="SMSLoginPin"]')))
button_otp_login = WebDriverWait(driver, 10).until(
    ec.visibility_of_element_located((By.XPATH, '//*[@id="submitButton"]')))
print(ref.get())
input_otp.send_keys(ref.get())
button_otp_login.click()

# Patterns to look for
patterns = {
    "SGD": {
        "MYR": r'(\d*.?\d*) SGD (\d*.?\d*) MYR',
        "AUD": r'(\d*.?\d*) SGD (\d*.?\d*) AUD',
        "GBP": r'(\d*.?\d*) SGD (\d*.?\d*) GBP',
        "USD": r'(\d*.?\d*) SGD (\d*.?\d*) USD',
    }
}

rates = {}

for from_currency, pattern_map in patterns.items():
    for to_currency, pattern in pattern_map.items():
        # Scroll to bottom to make the buttons visible to be clicked
        driver.execute_script('window.scrollTo(0, document.documentElement.offsetHeight - window.innerHeight);', '')
        # Give sometime to scroll
        time.sleep(0.5)
        button_rate = WebDriverWait(driver, 10).until(
            ec.visibility_of_element_located((By.XPATH, f'//*[@id="{to_currency}"]')))
        button_rate.click()
        print(f'Clicked {to_currency}')

        # Click the rate buttons and use regex to capture the rates
        span_rates = WebDriverWait(driver, 10).until(
            ec.visibility_of_element_located((By.XPATH, '//*[@id="exchgRate"]')))
        match = re.match(pattern, span_rates.text)

        if match:
            if from_currency not in rates:
                rates[from_currency] = {to_currency: match.group(2)}
            else:
                rates[from_currency][to_currency] = match.group(2)

# Close the browser window
driver.quit()

# Write rates to json file
today = datetime.datetime.now().strftime("%Y%m%d%H%M")

# Keep a historical file for statistical purposes
with open(f'rates/dbs/dbs_rates_{today}.json', 'w') as fp:
    json.dump(rates, fp, indent=2)

# Latest rates
with open(f'rates/dbs/dbs_rates.json', 'w') as fp:
    json.dump(rates, fp, indent=2)

for from_currency, currency_map in rates.items():
    for to_currency, rate in currency_map.items():
        print(f'1 {from_currency} is to {rate} {to_currency}')

ref = db.reference('rates/dbs')
ref.set(rates)
