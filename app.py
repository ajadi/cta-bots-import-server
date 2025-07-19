import os
import json
import hmac
import hashlib
import base64
import requests
import time
from flask import Flask
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Конфигурация из переменных окружения ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
API_PASSPHRASE = os.getenv("API_PASSPHRASE")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Парсим JSON Google credentials из переменной
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDS = json.loads(GOOGLE_CREDENTIALS_JSON)

# --- Flask-приложение ---
app = Flask(__name__)

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

def create_signature(timestamp, method, request_path, body=''):
    message = f'{timestamp}{method.upper()}{request_path}{body}'
    mac = hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def get_bitget_fills():
    timestamp = str(int(time.time() * 1000))
    method = 'GET'
    path = '/api/mix/v1/order/fills?productType=USDT-FUTURES&limit=50'

    sign = create_signature(timestamp, method, path)
    headers = {
        'ACCESS-KEY': API_KEY,
        'ACCESS-SIGN': sign,
        'ACCESS-TIMESTAMP': timestamp,
        'ACCESS-PASSPHRASE': API_PASSPHRASE
    }

    url = f'https://api.bitget.com{path}'
    resp = requests.get(url, headers=headers)
    return resp.json().get('data', [])

def upload_trade(trade, ws):
    date = datetime.fromtimestamp(int(trade['cTime']) / 1000).strftime('%Y-%m-%d %H:%M')
    tp_sl = trade.get('orderType', '')
    roi = trade.get('profitRate', '')
    size = trade.get('size', '')
    profit = trade.get('profit', '')
    ws.append_row([date, tp_sl, roi, size, profit, "Импортировано"])

@app.route('/bitget_to_sheet')
def bitget_to_sheet():
    trades = get_bitget_fills()
    sheet = get_sheet()
    routed = {'MACD-30m': [], 'MACD-1h': [], 'RSI-30m': []}

    for trade in trades:
        algo = trade.get('algoName', '')
        if 'MACD-30m' in algo:
            routed['MACD-30m'].append(trade)
        elif 'MACD-1h' in algo:
            routed['MACD-1h'].append(trade)
        elif 'RSI-30m' in algo:
            routed['RSI-30m'].append(trade)

    for tab_name, trades in routed.items():
        if not trades:
            continue
        ws = sheet.worksheet(tab_name)
        for tr in trades:
            upload_trade(tr, ws)

    return "Импорт завершён", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
