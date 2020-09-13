import time
from requests import exceptions 

from uuid import uuid1
from decimal import Decimal, getcontext
from yaspin import yaspin
from yaspin.spinners import Spinners
from Binance import Binance

from multiprocessing.pool import ThreadPool as Pool
from functools import partial
from Database import BotDatabase

from TradingModel import TradingModel

from Strategies import *

# BotRunner.py allows us to run all the startegies in parallel
# Each bot has access to an exchange and a database.
#%%
class BotRunner:

	def __init__(self, sp, exchange, database):
		self.sp = sp
		self.exchange = exchange
		self.database = database
		self.update_balance = True
		self.ask_permission = False
		getcontext().prec = 33

#%%
	def EntryOrder(self, bot_params, strategy_function, pairs, symbol_data):
		sp = self.sp
		exchange = self.exchange
		database = self.database

		# get dataframe & check for signal
		symbol = symbol_data['symbol']
		df = exchange.GetSymbolKlines(symbol, bot_params['interval'])
		buy = strategy_function(df, len(df['close'])-1)

		sp.text = "Checking signals on "+symbol
		# if signal, place buy order
		if buy is not False:   # if buy side is True
			i = len(df) - 1   # len of the data available on this symbol
			order_id = str(uuid1())   # making a unique id for the order
			# buy at 0.4% lower than current price
			q_qty = Decimal(bot_params['trade_allocation'])   # Defining the available qtity tradable

			buy_price = exchange.RoundToValidPrice(   # Returns the price of a symbol we can buy, closest to desiredPrice
				symbol_data = symbol_data, 
				desired_price = Decimal(df['close'][i]) * Decimal(0.99))

			quantity = exchange.RoundToValidQuantity(   # Returns the minimum quantity of a symbol we can buy, closest to desiredPrice
				symbol_data = symbol_data, 
				desired_quantity = q_qty / buy_price)

			order_params = dict(
				symbol = symbol,
				side = "BUY",   # BUY or SELL
				type = "LIMIT",   # MARKET, LIMIT, STOP LOSS etc
				timeInForce = "GTC",   # GTC (GoodTillCancelled) : An order will be on the book unless the order is canceled
				price = format(buy_price, 'f'),
				quantity = format(quantity, 'f'),
				newClientOrderId = order_id)   # Giving to the order an ID

			if self.ask_permission:   # Every time the bot finds a signal, it needs our permission to buy

				model = TradingModel(symbol, bot_params['interval'])   # make a trading model
				model.df = df
				model.plotData(buy_signals=[(df['time'][i], buy)], plot_title=symbol)   # model that we plot to give a vision of the signal

				sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
				print(order_params)   # give the params for de permission
				permission = input("Signal found on "+ symbol +", place order (y / n)?")   # need an answer (y or n)
				sp.start()   # Spinning animation confirming that the bot is running
				if permission != 'y':
					return

			# buy from exchange
			order_result = self.PlaceOrder(order_params, bot_params['test_run'])   # Places order on Pair based on params. Returns False if unsuccesful, or the order_info received from the exchange if succesful

			if order_result is not False:   # Order is a success

				self.update_balance = True   # setting update_balance to True so that the Balance is refreshed

				# Save order
				db_order = self.OrderResultToDatabase(order_result, symbol_data, bot_params, True)   # Building the frame to save the order into the DB
				database.SaveOrder(db_order)   # saving the order into the DB

				pairs[symbol]['is_active'] = False   # setting the symbol on sell side (we can only have one trade per symbol at the time)
				pairs[symbol]['current_order_id'] = order_id   # giving to the symbol the current order ID

				# Change pair state to inactive
				database.UpdatePair(
					bot=bot_params, 
					symbol=symbol, 
					pair=pairs[symbol]
				)

#%%
	def ExitOrder(self, bot_params, pairs, order:dict):
		# Check order has been filled, if it has, update order in database and then
		# place a new order at target price, OCO-type if we also have stop loss enabled
		sp = self.sp
		exchange = self.exchange
		database = self.database

		if order['is_closed']:   # if we don't have any orders
			return   # end

		symbol = order['symbol']   # setting the symbols with orders
		exchange_order_info = exchange.GetOrderInfo(symbol, order['id'])   # getting info on the orders

		if not self.CheckRequestValue(exchange_order_info):   # if something went wrong
			return 

		pair = pairs[symbol]   # listing all symbols orders

		sp.text = "Looking for an Exit on "+symbol
		# update old order in database
		order['status'] = exchange_order_info['status']   # listing the status of every orders
		order['executed_quantity'] = Decimal(exchange_order_info['executedQty'])   # listing the executed qtity of every orders
		if exchange_order_info['status'] == exchange.ORDER_STATUS_FILLED:   # if the order status is filled
			if order['is_entry_order']:   # and if the order is an entry order (on buy side)
				# place the exit order
				order_id = str(uuid1())   # making a unique id for the order

				sell_price = exchange.RoundToValidPrice(   # Returns the price of a symbol we can sell, closest to desiredPrice
					symbol_data = self.all_symbol_datas[symbol], 
					desired_price = Decimal(order['take_profit_price']))

				quantity = exchange.RoundToValidQuantity(   # Returns the minimum quantity of a symbol we can sell, closest to desiredPrice
					symbol_data = self.all_symbol_datas[symbol], 
					desired_quantity = Decimal(order['executed_quantity']))

				order_params = dict(
					symbol = symbol,
					side = "SELL",   # BUY or SELL
					type = "LIMIT",   # MARKET, LIMIT, STOP LOSS etc
					timeInForce = "GTC",   # GTC (GoodTillCancelled) : An order will be on the book unless the order is canceled
					price = format(sell_price, 'f'),
					quantity = format(quantity, 'f'),
					newClientOrderId = order_id)   # Giving to the order an ID

				if self.ask_permission:   # Every time the bot finds a signal, it needs our permission to sell
					sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
					print("Exit found on "+ symbol)

					print("Entry Order")
					print(exchange_order_info, "\n")   # give the info of entry orders for permission
					print("Potential Exit Order")
					print(order_params, "\n")   # give the params of potential exit order for the permission

					permission = input("Place exit order (y / n)?")   # need an answer (y or n)
					if permission != 'y':	
						return

				# buy from exchange
				order_result = self.PlaceOrder(order_params, bot_params['test_run'])   # Places order on Pair based on params. Returns False if unsuccesful, or the order_info received from the exchange if succesful

				if order_result is not False:   # Order is a success

					self.update_balance = True   # setting update_balance to True so that the Balance is refreshed
					
					# Save order
					db_order = self.OrderResultToDatabase(order_result, None, bot_params, False, False, order['id'])   # Building the frame to save the order into the DB
					database.SaveOrder(db_order)   # saving the order into the DB

					order['is_closed'] = True   # setting the symbol on buy side (we can only have one trade per symbol at the time)
					order['closing_order_id'] = order_id   # giving to the symbol the current order ID
					# Change pair state to inactive
					pair['is_active'] = False   # setting the symbol on buy side (we can only have one trade per symbol at the time)
					pair['current_order_id'] = order_id   # giving to the symbol the current order ID
			else:
				self.update_balance = True   # setting update_balance to True so that the Balance is refreshed
				sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
				print("Succesfully exited order on "+ symbol +"!")
				print(order)
				print(exchange_order_info)
				sp.start()   # Spinning animation confirming that the bot is running
				order['is_closed'] = True   # setting the symbol on buy side (we can only have one trade per symbol at the time)
				pair['is_active'] = True   # setting the symbol on buy side (we can only have one trade per symbol at the time)
				pair['current_order_id'] = None   # giving to the symbol the current order ID

			pairs[symbol] = pair   # listing all symbols orders

			# Change pair state to active
			database.UpdatePair(
				bot=bot_params,
				symbol=symbol,
				pair=pair
			)

		database.UpdateOrder(order)   # Update the DB

#%%
	def PlaceOrder(self, params, test):
		''' Places order on Pair based on params. Returns False if unsuccesful, 
		or the order_info received from the exchange if succesful '''
		sp = self.sp
		exchange = self.exchange

		order_info = exchange.PlaceOrderFromDict(params, test=test)
		# IF ORDER PLACING UNSUCCESFUL, CLOSE THIS POSITION
		sp.stop()
		if "code" in order_info:
			print("ERROR placing order !!!! ")
			print(params)
			print(order_info)
			print()
			sp.start()
			return False
		# IF ORDER SUCCESFUL, SET PAIR TO ACTIVE
		else:
			print("SUCCESS placing ORDER !!!!")
			print(params)
			print(order_info)
			print()
			sp.start()
			return order_info

#%%
	def CheckRequestValue(self, response, text='Error getting request from exchange!', print_response=True):
		""" Checks return value of request """
		sp = self.sp

		if "code" in response:   # If 'code' in response, mean that there is an Error
			sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
			print(text)   # Printing the Error message
			if print_response:
				print(response, '\n')   # printing the response comming from the exchange
			sp.start()   # Spinning animation confirming that the bot is running
			return False
		else:
			return True

#%%
	def OrderResultToDatabase(self, order_result, symbol_data, bot_params, is_entry_order=False, is_closed=False, closing_order_id=False):
		
		sp = self.sp
		exchange = self.exchange

		order = dict()
		if symbol_data == None:
			symbol_data = exchange.GetSymbolDataOfSymbols([order_result['symbol']])
		order['id'] = order_result['clientOrderId']
		order['bot_id'] = bot_params['id']
		order['symbol'] = order_result['symbol']
		order['time'] = order_result['transactTime']
		order['price'] = order_result['price']
		order['take_profit_price'] = exchange.RoundToValidPrice(
			symbol_data = symbol_data,
			desired_price = Decimal(order_result['price']) * Decimal(bot_params['profit_target']), 
			round_up=True)
		order['original_quantity'] =  Decimal(order_result['origQty'])
		order['executed_quantity'] =  Decimal(order_result['executedQty'])
		order['status'] = order_result['status']
		order['side'] = order_result['side']
		order['is_entry_order'] = is_entry_order
		order['is_closed'] = is_closed
		order['closing_order_id'] = closing_order_id

		sp.stop()
		print("In db, order will be saved as ")
		print(order)
		sp.start()

		return order

#%%
	def CreateBot(self,
		name = 'Nin9_Bot',   # Name of the bot
		strategy_name = 'ma_crossover',   # Name of the strategy
		interval = '3m',   # Interval of trading process
		trade_allocation = 0.1,   # Allocation allowed for this bot (%)
		profit_target = 1.012,
		test = True,   # we can run the bot in test mode
		symbols = []):   # This function creates a bot based on some settings ans saves it to the DB

		exchange = self.exchange
		database = self.database

		assert interval in exchange.KLINE_INTERVALS, interval+" is not a valid interval."   # Making sure interval set exists
		assert trade_allocation > 0 and trade_allocation <= 1, "Trade allocation should be in (0, 1]"   # Making sure trade allocation set is reasonable
		assert profit_target > 0, "Profit target should be above 0"   # Making sure profit target set is abose 0

		bot_id = str(uuid1())   # making a unique id for the bot
		bot_params = dict(
			id = bot_id,
			name = name,
			strategy_name = strategy_name,
			interval = interval,
			trade_allocation = Decimal(trade_allocation), 
			profit_target = Decimal(profit_target),
			test_run = test
		)
		database.SaveBot(bot_params)   # saving the bot parameters into the DB

		symbol_datas = exchange.GetSymbolDataOfSymbols(symbols)   # Getting information about symbols set (Tradable or not, ...)
		symbol_datas_dict = dict()
		for sd in symbol_datas:
			symbol_datas_dict[sd['symbol']] = sd   # converting symbol_datas list to a dictionnary symbol_datas_dict with symbols as items

		pairs = []
		for symbol_data in symbol_datas:
			pair_id = str(uuid1())
			pair_params = dict(
				id = pair_id,
				bot_id = bot_id,
				symbol = symbol_data['symbol'],
				is_active = True,
				current_order_id = None,
				profit_loss = Decimal(1)
			)
			database.SavePair(pair_params)   # saving the pairs parameters into the DB
			pairs.append(pair_params)   # adding these params to pairs list

		bot_params['pairs'] = pairs   # adding pairs list to the bot_params list

		return bot_params, symbol_datas_dict

#%%
	def GetAllBotsFromDb(self):
		""" Returns all Bots from the DB """

		exchange = self.exchange
		database = self.database

		bot_sds = []
		bots = database.GetAllBots()   # Gets all Bots details from Database
		for bot in bots:
			pairs = database.GetAllPairsOfBot(bot)   #  Gets all the pairs from each bot (list)

			symbols = []
			for pair in pairs:
				symbols.append(pair['symbol'])   # from each pair extract the symbol and put it in a list

			symbol_datas = exchange.GetSymbolDataOfSymbols(symbols)   # Getting information about symbols set (Tradable or not, ...)
			symbol_datas_dict = dict()
			for sd in symbol_datas:
				symbol_datas_dict[sd['symbol']] = sd   # converting symbol_datas list to a dictionnary symbol_datas_dict with symbols as items

			bot_sds.append((bot, symbol_datas_dict))   # adding the bot and his trading symbols to a list

		return bot_sds   # returning this list

#%%
	def GetBalances(self, bots):
		""" Get Balances of all Assets From Exchange """

		exchange = self.exchange
		account_data = exchange.GetAccountData()   # Gets Balances & Account Data

		requested_times = 0
		while not self.CheckRequestValue(account_data, text="\nError getting account balance, retrying..."):
			requested_times = requested_times + 1   # Adding one to the total try times to request balance and account data
			time.sleep(10)   # Put the bot to sleep during 10 sec 
			account_data = exchange.GetAccountData()   # Gets Balances & Account Data
			if requested_times > 15:   # If we have already requested the exchange 15 times
				self.sp.stop()   # We stop the spinning animation (bot stops)
				print("\nCan't get balance from exchange, tried more than 15 times.\n", "Stopping.\n")   # we print a final error message
				return False, False, False   # we return all results False

		balances_text = "**** BALANCES ****\n"
		buy_on_bot = dict()
		quote_assets = []
		for bot, symbol_datas_dict in bots:   # getting each bot
			for sd in symbol_datas_dict.values():   # getting each symbol data of each bot
				if sd['quoteAsset'] not in quote_assets:   # if the quote asset of the data provided isn't in the local variable
					quote_assets.append(sd['quoteAsset'])   # We add it

			for bal in account_data['balances']:   # looking to the balances of the exchange account
				if bal['asset'] in quote_assets:   # if the asset of the exchange account balance is in our quoteAsset
					balances_text = balances_text + " | " + bal['asset'] + ": " + str(round(Decimal(bal['free']), 5))
					if Decimal(bal['free']) > Decimal(bot['trade_allocation']):
						buy_on_bot[bal['asset']] = dict(buy = True, balance = Decimal(bal['free']))   # giving the bot free asset to trade
					else:
						buy_on_bot[bal['asset']] = dict(buy = False, balance = Decimal(bal['free']))   # not giving the bot free asset to trade

		return account_data, balances_text+"\n", buy_on_bot

#%%
	def StartExecution(self, bots):
		""" This is the main execution loop. It has two parts : 
			ONE - it checks all pairs for symbols, and places orders if symbolsmatch.
			TWO - it checks all unfilled orders that were placed on the bot to see if
			they were filled, and places subsequent orders/closes trades based on that."""

		database = self.database

		if len(bots) == 0:   # if there is no bots setting
			self.sp.text = "No bots available, exiting..."
			return

		self.sp.text = "Getting balances of all bots..."
		account_data, balances_text, buy_on_bot = self.GetBalances(bots)   # Get Balances of all Assets From Exchange

		self.all_symbol_datas = dict()

		for bot, sd in bots:
			pairs = database.GetAllPairsOfBot(bot)   # Gets All symbols which are tradable (currently)
			for pair in pairs:
				self.all_symbol_datas[pair['symbol']] = sd[pair['symbol']]   # from each pair extract the symbol and put it in a list

		while True:
			with yaspin(Spinners.growHorizontal) as sp:
				self.sp = sp   # Spinning animation confirming that the bot is running
				try:
					# Get All Pairs
					aps = [] 
					for bot, sd in bots:
						aps.extend(database.GetAllPairsOfBot(bot))   # add all symbol_data from all bots to this list aps (allPairsSymbols)
					all_pairs = dict()
					for pair in aps:
						all_pairs[pair['symbol']] = pair   # add all pairs from all symbols_data from all bots to this list all_pairs

					# Only request balances if order was placed recently
					if self.update_balance:
						account_data, balances_text, buy_on_bot = self.GetBalances(bots)   # Get Balances of all Assets From Exchange
						if account_data is False:   # if getting balance hasn't worked
							return
						sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
						print(balances_text)   # print the error message + the reason
						sp.start()   # Spinning animation start meaning that the bot is running
						self.update_balance = False   # setting update_balance to False to not run it infinitely

					# Find Signals on Bots
					for bot, symbol_datas_dict in bots:

						# Get Active Pairs per Bot
						ap_symbol_datas = []
						aps = database.GetActivePairsOfBot(bot)   # Gets all the active pairs from a bot
						pairs = dict()
						for pair in aps:
							if symbol_datas_dict.get(pair['symbol'], None) == None:
								sp.text = "Couldn't find " + pair['symbol'] + " looking for it later..."   # There is no active pairs
							else:
								ap_symbol_datas.append(symbol_datas_dict[pair['symbol']])   # add each symbol_data of active pairs to the list ap_symbol_datas
								pairs[pair['symbol']] = pair   # add each symbol of active pairs to the list pairs

						# If Enough Balance on bot, try finding signals
						try:
							self.Run(bot, strategies_dict[bot['strategy_name']], pairs, ap_symbol_datas)   # wrapper around the EntryOrder function
						except exceptions.SSLError:
							sp.text = "SSL Error caught!"
						except exceptions.ConnectionError:
							sp.text = "Having trouble connecting... retry"

						open_orders = database.GetOpenOrdersOfBot(bot)   # Getting all the open orders and copy to open_order list

						# If we have open orders saved in the DB, see if they exited
						if len(open_orders) > 0:   # If we have an open order
							sp.text = (str(len(open_orders)) + " orders open on " + bot['name'] + ", looking to close.")   # Spinning animation writting text
							try:
								self.Exit(bot, all_pairs, open_orders)   # wrapper around the ExitOrder function
							except exceptions.SSLError:
								sp.text = "SSL Error caught!"
							except exceptions.ConnectionError:
								sp.text = "Having trouble connecting... retry"
						else:
							sp.text = "No orders open on "+ bot['name']

				except KeyboardInterrupt:   # Stopping the bot by [ctrl+c]
					sp.stop()   # Spinning animation stop meaning that the bot isn't running anymore
					print("\nExiting...\n")
					return

#%%
	def Run(self, bot_params, strategy_function, pairs, symbol_datas):
		"""This is a wrapper around the EntryOrder function which allows
		us to check for signals and for filled orders in parallel
		(because we have to check signals on hundreds of pairs, potentially)"""
		pool = Pool(4)
		func1 = partial(self.EntryOrder, bot_params, strategy_function, pairs)
		pool.map(func1, symbol_datas)
		pool.close()
		pool.join()

#%%
	def Exit(self, bot_params, pairs, orders):
		"""This is a wrapper around the ExitOrder function which allows
		us to check for signals and for filled orders in parallel
		(because we have to check signals on hundreds of pairs, potentially)"""
		pool = Pool(4)
		func1 = partial(self.ExitOrder, bot_params, pairs)
		pool.map(func1, orders)
		pool.close()
		pool.join()

#%%
def Main():

	sp = yaspin(Spinners.growHorizontal)   # horizontal growing bar during botRunning
	exchange = Binance(credentials = 'credentials.txt')   # access to the exchange (adapted for Binance only)
	database = BotDatabase("database.db")   # access to the local database
	prog = BotRunner(sp, exchange, database)   # initializing the tradingBot

	i = input("Execute or Quit? (e or q)\n")   # Execute the tradingBot ?
	while i not in ['q']:
		if i == 'e':
			i = input("Create a new bot? (y or n)\n")   # We can create a new bot or recover the last one
			if i == 'y':   # Creating a brand new bot (usualy with new parameters)
				bot_symbol_datas = []   # Defining a list about to receive all data from symbols, strategy and allocation
				symbols = ['BTCUSDT', 'LTCUSDT', 'BNBUSDT', 'QTUMUSDT', \
				'ADAUSDT', 'XRPUSDT', 'EOSUSDT', 'XLMUSDT', 'ONTUSDT', \
				'TRXUSDT', 'VETUSDT', 'LINKUSDT', 'ETHUSDT', 'BATUSDT', \
				'XMRUSDT', 'ATOMUSDT', 'ALGOUSDT']   # List of symbols we want to trade

				bot, symbol_datas_dict = prog.CreateBot(   # Creating a new bot
					name = 'TestingBot',   # Name of the bot
					strategy_name = 'ma_crossover',   # Name of the strategy
					interval = '1m',   # Interval of trading process
					trade_allocation = 0.1,   # Allocation allowed for this bot (%)
					profit_target = 1.012,
					test = True,   # we can run the bot in test mode
					symbols = symbols)   # This function creates a bot based on some settings ans saves it to the DB
				bot_symbol_datas.append((bot, symbol_datas_dict))   # adding this new bot to a variable used here in the script
			else:
				bot_symbol_datas = prog.GetAllBotsFromDb()   # adding this saved bot to a variable used here in the script

			prog.StartExecution(bot_symbol_datas)   # Starting the bot with parameters given

		i = input("Execute or Quit? (e or q)")

#%%
if __name__ == "__main__":
	bot_symbol_datas = Main()
