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

# --- Переменные окружения ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
API_PASSPHRASE = os.getenv("API_PASSPHRASE")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDS = json.loads(GOOGLE_CREDENTIALS_JSON)

# --- Flask ---
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
    path = '/api/mix/v1/order/fills'
    query = '?productType=umcbl&limit=50'
    body = ''

    sign = create_signature(timestamp, method, path + query, body)
    headers = {
        'ACCESS-KEY': API_KEY,
        'ACCESS-SIGN': sign,
        'ACCESS-TIMESTAMP': timestamp,
        'ACCESS-PASSPHRASE': API_PASSPHRASE,
        'Content-Type': 'application/json',
        'locale': 'en-US'
    }

    url = f'https://api.bitget.com{path}{query}'
    resp = requests.get(url, headers=headers)

    try:
        result = resp.json()
        print("Bitget API response:", result, flush=True)
        if 'data' in result and isinstance(result['data'], list):
            return result['data']
        else:
            return []
    except Exception as e:
        print("Bitget API response error:", e, flush=True)
        print("Raw response:", resp.text, flush=True)
        return []

def upload_trade(trade, ws):
    try:
        date = datetime.fromtimestamp(int(trade['cTime']) / 1000).strftime('%Y-%m-%d %H:%M')
        tp_sl = trade.get('orderType', '')
        roi = trade.get('profitRate', '')
        size = trade.get('size', '')
        profit = trade.get('profit', '')
        ws.append_row([date, tp_sl, roi, size, profit, "Импортировано"])
    except Exception as e:
        print("Ошибка при записи строки:", e, flush=True)

@app.route('/bitget_to_sheet')
def bitget_to_sheet():
    try:
        trades = get_bitget_fills()
        if not trades:
            return "Нет сделок или ошибка Bitget API", 200

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

        for tab_name, trades_list in routed.items():
            if not trades_list:
                continue
            ws = sheet.worksheet(tab_name)
            for tr in trades_list:
                upload_trade(tr, ws)

        return "Импорт завершён", 200
    except Exception as e:
        print("Ошибка общего уровня:", e, flush=True)
        return f"Ошибка: {str(e)}", 500

@app.route('/')
def home():
    return "Сервер работает. Используй /bitget_to_sheet", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
