import requests
import hmac
import hashlib
from urllib import parse
from requests import Request
import logging
from time import sleep
import time

import pandas as pd
from sortedcontainers.sorteddict import SortedDict as sd

from cryptofeed.rest.api import API, request_retry
from cryptofeed.defines import BINANCE_FUTURES as BINANCE_ID, SELL, BUY, BID, ASK
from cryptofeed.standards import pair_std_to_exchange

LOG = logging.getLogger('rest')
RATE_LIMIT_SLEEP = 1


class Binance(API):
    ID = BINANCE_ID

    api = 'https://fapi.binance.com'

    def __init__(self, config, sandbox=False, **kwargs):
        super().__init__(config, sandbox, **kwargs)
        if 'recv_window' in kwargs:
            self.recv_window = kwargs['recv_window']
        else:
            self.recv_window = 5000

    def _get(self, command: str, params=None, retry=None, retry_wait=0):
        url = f"{self.api}{command}"

        @request_retry(self.ID, retry, retry_wait)
        def helper():
            resp = requests.get(url, params={} if not params else params)
            self._handle_error(resp, LOG)
            return resp.json()

        return helper()

    def all_balances(self):
        parameters = f'recvWindow={self.recv_window}&timestamp={int(round(time.time()) * 1000)}'
        sig, req = self._sign(parameters)
        while True:
            r = requests.get(f"{self.api}/fapi/v2/balance?{parameters}&signature={sig}", headers=req.headers)
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)

            data = r.json()
            if data == []:
                LOG.warning("%s: No data", self.ID)

            return data

    def funding_payments(self, symbol=None, start_date=None, end_date=None):
        if not start_date:
            start_date = '2019-01-01'

        if not end_date:
            end_date = pd.Timestamp.utcnow()

        start = API._timestamp(start_date)
        end = API._timestamp(end_date)

        start = int(start.timestamp()) * 1000
        end = int(end.timestamp()) * 1000

        parameters = f'incomeType=FUNDING_FEE'
        if symbol is not None:
            parameters += f'&symbol={symbol}'
        parameters += f'&startTime={start}&endTime={end}'
        parameters += f'&limit=1000'
        parameters += f'&recvWindow={self.recv_window}&timestamp={int(round(time.time()) * 1000)}'
        sig, req = self._sign(parameters)
        while True:
            r = requests.get(f"{self.api}/fapi/v1/income?{parameters}&signature={sig}", headers=req.headers)
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)

            data = r.json()
            if data == []:
                LOG.warning("%s: No data", self.ID)

            return data

    def money_flow(self, symbol=None, start_date=None, end_date=None):
        # deposits in and out of the account
        if not start_date:
            start_date = '2019-01-01'

        if not end_date:
            end_date = pd.Timestamp.utcnow()

        start = API._timestamp(start_date)
        end = API._timestamp(end_date)

        start = int(start.timestamp()) * 1000
        end = int(end.timestamp()) * 1000

        parameters = f'incomeType=TRANSFER'
        if symbol is not None:
            parameters += f'&symbol={symbol}'
        parameters += f'&startTime={start}&endTime={end}'
        parameters += f'&limit=1000'
        parameters += f'&recvWindow={self.recv_window}&timestamp={int(round(time.time()) * 1000)}'
        sig, req = self._sign(parameters)
        while True:
            r = requests.get(f"{self.api}/fapi/v1/income?{parameters}&signature={sig}", headers=req.headers)
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)

            data = r.json()
            if data == []:
                LOG.warning("%s: No data", self.ID)

            return data

    def fills(self, symbol=None):
        symbol_list = []
        data = []
        if symbol is None:
            while True:
                r = requests.get(f"{self.api}/fapi/v1/exchangeInfo")
                if r.status_code == 429:
                    sleep(RATE_LIMIT_SLEEP)
                    continue
                elif r.status_code == 500:
                    LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                    sleep(10)
                    continue
                elif r.status_code != 200:
                    self._handle_error(r, LOG)
                else:
                    sleep(RATE_LIMIT_SLEEP)
                result = r.json()
                break
            for symbol in result['symbols']:
                symbol_list.append(symbol['symbol'])
        else:
            symbol_list.append(symbol)

        for symbol in symbol_list:
            data += self._fills(symbol)

        return data

    def _fills(self, symbol):
        parameters = f'symbol={symbol}'
        parameters += f'&fromId={0}'
        parameters += f'&limit=1000'
        parameters += f'&recvWindow={self.recv_window}&timestamp={int(round(time.time()) * 1000)}'
        sig, req = self._sign(parameters)
        while True:
            r = requests.get(f"{self.api}/fapi/v1/userTrades?{parameters}&signature={sig}", headers=req.headers)
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)

            data = r.json()
            return data

    @staticmethod
    def _positions_normalization(pos):
        """
            {'symbol': 'BTCUSDT', 'positionAmt': '0.000', 'entryPrice': '0.00000',
             'markPrice': '9222.66966116', 'unRealizedProfit': '0.00000000', 'liquidationPrice': '0',
             'leverage': '20', 'maxNotionalValue': '5000000',
              'marginType': 'cross', 'isolatedMargin': '0.00000000', 'isAutoAddMargin': 'false',
              'positionSide': 'BOTH'}
             }
        """
        try:
            ret_val = []
            for p in pos:
                if float(p['positionAmt']) == 0.0:
                    continue
                ret_val.append({'symbol': p['symbol'],
                                'side': 'buy' if float(p['positionAmt']) >= 0 else 'sell',
                                'size': float(p['positionAmt']) if float(p['positionAmt']) >= 0
                                else float(p['positionAmt']) * -1,
                                'entryPrice': p['entryPrice']
                                })
            return ret_val
        except Exception as ex:
            print(' ')

    def positions(self):
        result = None
        parameters = f'recvWindow={self.recv_window}&timestamp={int(round(time.time()) * 1000)}'
        sig, req = self._sign(parameters)
        while True:
            r = requests.get(f"{self.api}/fapi/v2/positionRisk?{parameters}&signature={sig}", headers=req.headers)
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)
            result = r.json()
            break
        norm_result = self._positions_normalization(result)
        return norm_result

    def get_assets(self):
        result = None
        while True:
            r = requests.get(f"{self.api}/fapi/v1/exchangeInfo")
            if r.status_code == 429:
                sleep(RATE_LIMIT_SLEEP)
                continue
            elif r.status_code == 500:
                LOG.warning("%s: 500 for URL %s - %s", self.ID, r.url, r.text)
                sleep(10)
                continue
            elif r.status_code != 200:
                self._handle_error(r, LOG)
            else:
                sleep(RATE_LIMIT_SLEEP)
            result = r.json()
            break
        norm_result = []
        try:
            for asset in result['symbols']:
                norm_result.append({'name': asset['symbol'][0:-4],
                                    'min_trading_size': asset['filters'][2]['minQty'],
                                    'tick_size': asset['filters'][0]['tickSize'],
                                    'size_increment': asset['filters'][1]['stepSize']})
        except Exception as ex:
            print(' ')
        return norm_result

    def _sign(self, parameters):
        request = Request('GET')

        signature = hmac.new(self.key_secret.encode(), parameters.encode(), digestmod=hashlib.sha256).hexdigest()
        request.headers['Content-Type'] = "application/x-www-form-urlencoded"
        request.headers['X-MBX-APIKEY'] = self.key_id
        return signature, request


if __name__ == '__main__':
    e = Binance(None)
    b = e.fills()
    print(e.ID)
