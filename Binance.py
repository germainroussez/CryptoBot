import requests
import json
import decimal
import hmac
import time
import pandas as pd
import hashlib
from decimal import Decimal

class Binance:
	# Order Status
	ORDER_STATUS_NEW = 'NEW'
	ORDER_STATUS_PARTIALLY_FILLED = 'PARTIALLY_FILLED'
	ORDER_STATUS_FILLED = 'FILLED'
	ORDER_STATUS_CANCELED = 'CANCELED'
	ORDER_STATUS_PENDING_CANCEL = 'PENDING_CANCEL'
	ORDER_STATUS_REJECTED = 'REJECTED'
	ORDER_STATUS_EXPIRED = 'EXPIRED'

	# Order Side
	SIDE_BUY = 'BUY'
	SIDE_SELL = 'SELL'

	# Order Type
	ORDER_TYPE_LIMIT = 'LIMIT'
	ORDER_TYPE_MARKET = 'MARKET'
	ORDER_TYPE_STOP_LOSS = 'STOP_LOSS'
	ORDER_TYPE_STOP_LOSS_LIMIT = 'STOP_LOSS_LIMIT'
	ORDER_TYPE_TAKE_PROFIT = 'TAKE_PROFIT'
	ORDER_TYPE_TAKE_PROFIT_LIMIT = 'TAKE_PROFIT_LIMIT'
	ORDER_TYPE_LIMIT_MAKER = 'LIMIT_MAKER'

	# Intervals of data
	KLINE_INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']

	def __init__(self, credentials='credentials.txt'):
		self.base = 'https://api.binance.com'   # Base of any API request with Binance

		self.endpoints = {
			"order": '/api/v3/order',   # Send in a new order.
			"testOrder": '/api/v3/order/test',   # Test new order creation and signature/recvWindow long. Creates and validates a new order but does not send it into the matching engine.
			"allOrders": '/api/v3/allOrders',   # Get all account orders; active, canceled, or filled.
			"klines": '/api/v3/klines',   # Kline/candlestick bars for a symbol. Klines are uniquely identified by their open time.
			"exchangeInfo": '/api/v3/exchangeInfo',   # Current exchange trading rules and symbol information
			"24hrTicker" : '/api/v3/ticker/24hr',   # 24 hour rolling window price change statistics. Careful when accessing this with no symbol.
			"averagePrice" : '/api/v3/avgPrice',   # Current average price for a symbol.
			"orderBook" : '/api/v3/depth',   # Get current Orderbook data.
			"account" : '/api/v3/account'   # Get current account information.
		}   # API requests endpoints used

		f = open(credentials, "r")   # Read the creditential file (anonymous)
		contents = f.read().split('\n')   # Split information red in the creditential file
		self.binance_keys = dict(api_key = contents[0], secret_key=contents[1])   # Attribute creditential informations from creditential file 

		self.headers = {"X-MBX-APIKEY": self.binance_keys['api_key']}

#%%
	def _get(self, url, params=None, headers=None) -> dict:
		""" Makes a Get Request """
		try: 
			response = requests.get(url, params=params, headers=headers)
			data = json.loads(response.text)
			data['url'] = url
		except Exception as e:
			print("Exception occured when trying to access "+url)
			print(e)
			data = {'code': '-1', 'url':url, 'msg': e}

		return data

#%%
	def _post(self, url, params=None, headers=None) -> dict:
		""" Makes a Post Request """
		try: 
			response = requests.post(url, params=params, headers=headers)
			data = json.loads(response.text)
			data['url'] = url
		except Exception as e:
			print("Exception occured when trying to access "+url)
			print(e)
			data = {'code': '-1', 'url':url, 'msg': e}

		return data

#%%
	def GetSymbolDataOfSymbols(self, symbols:list=None):
		""" Gets All symbols which are tradable (currently) """
		url = self.base + self.endpoints["exchangeInfo"]   # Define the url request
		data = self._get(url)   # Call the _get function with the url to get data
		if data.__contains__('code'):
			return []

		symbols_list = []
		for pair in data['symbols']:
			if pair['status'] == 'TRADING':   # There are pairs available but not 'tradable'
				if symbols != None and pair['symbol'] in symbols:
					symbols_list.append(pair)

		return symbols_list   # return pairs with the quoteAsset we are looking for

#%%
	def GetAccountData(self) -> dict:
		""" Gets Balances & Account Data """
		url = self.base + self.endpoints["account"]   # Define the url request
		params = {
		'timestamp': int(round(time.time()*1000)),   # timestamp (millisecond) is the time when the request was created and sent
		'recvWindow': 60000   # recvWindow specify the number of milliseconds after timestamp the request is valid for (60000 max)
		}
		self.signRequest(params)   # Request needs to be signed by creditential info to be valid

		return self._get(url, params, self.headers)

#%%
	def Get24hrTicker(self, symbol:str):
		url = self.base + self.endpoints['24hrTicker'] + "?symbol="+symbol   # Define the url request

		return self._get(url)   # Return a bunch of informations about the 24h ticker on the requested symbol

#%%
	def GetSymbolKlinesExtra(self, symbol:str, interval:str, limit:int=1000, end_time=False):
		# Basicaly, we are calling the GetSymbolKlines as many times as needed
		# in order to get all the historical data required (based on the limit parameter)
		# and finally, results get merged into one long dataframe.
		repeat_rounds = 0
		if limit > 1000:   # We can get only 1000 candles per request
			repeat_rounds = int(limit/1000)   # So we have to define the number of requests needed to get all the historical data required

		initial_limit = limit % 1000   # Residual
		if initial_limit == 0:   # To avoid launching an empty request
			initial_limit = 1000

		# First, we get the last initial_limit candles, starting FROM end_time and going
		# backwards (or starting in the present moment, if end_time is False)
		df = self.GetSymbolKlines(symbol, interval, limit=initial_limit, end_time=end_time)
		while repeat_rounds > 0:
			# Then, for every other 1000 candles, we get them, but starting at the beginning
			# of the previously received candles.
			df2 = self.GetSymbolKlines(symbol, interval, limit=1000, end_time=df['time'][0])
			df = df2.append(df, ignore_index = True)
			repeat_rounds -= 1

		return df

#%%
	def GetSymbolKlines(self, symbol:str, interval:str, limit:int=1000, end_time=False):
		"""	Gets trading data for one symbol 
		
		Parameters
		--
			symbol str:        The symbol for which to get the trading data

			interval str:      The interval on which to get the trading data
				minutes      '1m' '3m' '5m' '15m' '30m'
				hours        '1h' '2h' '4h' '6h' '8h' '12h'
				days         '1d' '3d'
				weeks        '1w'
				months       '1M' """

		if limit > 1000:   # We can get only 1000 candles per request
			return self.GetSymbolKlinesExtra(symbol, interval, limit, end_time)   # So we use a function that decimate our request in smaller ones

		params = '?&symbol='+symbol+'&interval='+interval+'&limit='+str(limit)   # Define the quote necessary for the request
		if end_time:
			params = params + '&endTime=' + str(int(end_time))   # Update the quote if we have a special end_time

		url = self.base + self.endpoints['klines'] + params   # Define the url request (with the param/quote)

		data = requests.get(url)   # download data
		df = pd.DataFrame.from_dict(json.loads(data.text))   # Convert data to pd dataframe using the json dictionnary
		df = df.drop(range(6, 12), axis=1)   # Clean-up the dataframe by removing data we're not interested in
		df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']   # rename columns
		for col in df.columns:
			df[col] = df[col].astype(float)   # transform values from strings to floats
		df['date'] = pd.to_datetime(df['time'] * 1000000, infer_datetime_format=True)   # convert the time data to a date data

		return df

#%%
	def PlaceOrderFromDict(self, params, test:bool=False):
		""" Places order from params dict """
		params['timestamp'] = int(round(time.time()*1000))   # timestamp (millisecond) is the time when the request was created and sent
		params['recvWindow'] = 60000   # recvWindow specify the number of milliseconds after timestamp the request is valid for (60000 max)
		self.signRequest(params)   # Request needs to be signed by creditential info to be valid

		if test: 
			url = self.base + self.endpoints['testOrder']   # testOrder url
		else:
			url = self.base + self.endpoints['order']   # Order url

		return self._post(url, params, self.headers)

#%%
	def PlaceOrder(self, symbol:str, side:str, orderType:str, quantity:float=0, price:float=0, test:bool=True):
		"""Places an order on Binance
		Parameters
		--
			symbol str:        The symbol for which to get the trading data
			side str:          The side of the order 'BUY' or 'SELL'
			type str:          The type, 'LIMIT', 'MARKET', 'STOP_LOSS'
			quantity float:    ..... """
		params = {
			'symbol': symbol,
			'side': side,   # BUY or SELL
			'type': orderType,   # MARKET, LIMIT, STOP LOSS etc
			'quantity': quantity,
			'timestamp': int(round(time.time()*1000)),   # timestamp (millisecond) is the time when the request was created and sent
			'recvWindow': 60000   # recvWindow specify the number of milliseconds after timestamp the request is valid for (60000 max)
		}
		if orderType != 'MARKET':
			params['timeInForce'] = 'GTC'   # GTC (GoodTillCancelled) : An order will be on the book unless the order is canceled
			params['price'] = Binance.floatToString(price)
		self.signRequest(params)   # Request needs to be signed by creditential info to be valid

		if test: 
			url = self.base + self.endpoints['testOrder']   # url to test new order creation and signature/recvWindow long. Creates and validates a new order but does not send it into the matching engine.
		else:
			url = self.base + self.endpoints['order']   # url to send in a new order.

		return self._post(url, params=params, headers=self.headers)   # Posting the order (even if it's a test)

#%%
	def CancelOrder(self, symbol:str, orderId:str):
		"""	Cancels the order on a symbol based on orderId """
		params = {
			'symbol': symbol,
			'orderId' : orderId,   # Necessary to know which order to cancel
			'timestamp': int(round(time.time()*1000)),   # timestamp (millisecond) is the time when the request was created and sent
			'recvWindow': 60000   # recvWindow specify the number of milliseconds after timestamp the request is valid for (60000 max)
		}
		self.signRequest(params)   # Request needs to be signed by creditential info to be valid
		url = self.base + self.endpoints['order']   # url to send in a new order.
		try: 
			response = requests.delete(url, params=params, headers=self.headers)   # Sending the request to cancel an order
			data = response.text   # converting the response into a dictionnary
		except Exception as e:   # an exception generally occure when the order is already filled
			print("Exception occured when trying to cancel order on "+url)
			print(e)
			data = {'code': '-1', 'msg':e}

		return json.loads(data)   # returns -in all cases- the response

#%%
	def GetOrderInfo(self, symbol:str, orderId:str):
		""" Gets info about an order on a symbol based on orderId """
		params = {
			'symbol': symbol,
			'origClientOrderId' : orderId,   # Necessary to know which order we want information from
			'timestamp': int(round(time.time()*1000)),   # timestamp (millisecond) is the time when the request was created and sent
			'recvWindow': 60000   # recvWindow specify the number of milliseconds after timestamp the request is valid for (60000 max)q
		}
		self.signRequest(params)   # Request needs to be signed by creditential info to be valid
		url = self.base + self.endpoints['order']   # url to send in a new order.

		return self._get(url, params=params, headers=self.headers)   # Getting the orderInfo

#%%
	def signRequest(self, params:dict):
		""" Signs the request to the Binance API """
		query_string = '&'.join(["{}={}".format(d, params[d]) for d in params])
		signature = hmac.new(self.binance_keys['secret_key'].encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256)
		params['signature'] = signature.hexdigest()

#%%
	@classmethod
	def floatToString(cls, f:float):
		""" Converts the given float to a string, without resorting to the scientific notation """
		ctx = decimal.Context()
		ctx.prec = 12
		d1 = ctx.create_decimal(repr(f))

		return format(d1, 'f')

#%%
	@classmethod
	def get10Factor(cls, num):
		""" Returns the number of 0s before the first non-0 digit of a number 
		(if |num| is < than 1) or negative the number of digits between the first 
		integer digit and the last, (if |num| >= 1) 
		   |get10Factor(0.00000164763) = 6
		   |get10Factor(1600623.3) = -6	"""
		p = 0
		for i in range(-20, 20):
			if num == num % 10**i:
				p = -(i - 1)
				break

		return p

#%%
	@classmethod
	def RoundToValidPrice(cls, symbol_data, desired_price, round_up:bool=False) -> Decimal:
		""" Returns the price of a symbol we can buy, closest to desiredPrice """
		
		pr_filter = {}
		
		for fil in symbol_data["filters"]:
			if fil["filterType"] == "PRICE_FILTER":
				pr_filter = fil
				break
		
		if not pr_filter.keys().__contains__("tickSize"):
			raise Exception("Couldn't find tickSize or PRICE_FILTER in symbol_data.")
			return

		round_off_number = int(cls.get10Factor((float(pr_filter["tickSize"]))))

		number = round(Decimal(desired_price), round_off_number)
		if round_up:
			number = number + Decimal(pr_filter["tickSize"])

		return number

#%%
	@classmethod
	def RoundToValidQuantity(cls, symbol_data, desired_quantity, round_up:bool=False) -> Decimal:
		""" Returns the minimum quantity of a symbol we can buy,
		closest to desiredPrice """
		
		lot_filter = {}
		
		for fil in symbol_data["filters"]:
			if fil["filterType"] == "LOT_SIZE":
				lot_filter = fil
				break
		
		if not lot_filter.keys().__contains__("stepSize"):
			raise Exception("Couldn't find stepSize or PRICE_FILTER in symbol_data.")
			return

		round_off_number = int(cls.get10Factor((float(lot_filter["stepSize"]))))

		number = round(Decimal(desired_quantity), round_off_number)
		if round_up:
			number = number + Decimal(lot_filter["stepSize"])

		return number

#%%
def Main():

	symbol = 'ETHUSDT'
	exchange = Binance('credentials.txt')

	GetAccountData = exchange.GetAccountData()
	Get24hrTicker = exchange.Get24hrTicker(symbol=symbol)
	GetSymbolKlines = exchange.GetSymbolKlines(symbol=symbol, interval='5m', limit=10000)
	GetSymbolDataOfSymbols = exchange.GetSymbolDataOfSymbols(symbols=symbol)
	PlaceOrder = exchange.PlaceOrder(symbol=symbol, side="BUY", orderType="LIMIT", quantity=20, price=360, test=True)

	return GetAccountData, Get24hrTicker, GetSymbolKlines, GetSymbolDataOfSymbols, PlaceOrder

#%%
if __name__ == '__main__':
	GetAccountData, Get24hrTicker, GetSymbolKlines, GetSymbolDataOfSymbols, PlaceOrder = Main()
