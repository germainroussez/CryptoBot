import plotly.graph_objs as go
from plotly.offline import plot

from Binance import Binance

class TradingModel:

	def __init__(self, symbol, timeframe:str='4h'):
		self.symbol = symbol
		self.timeframe = timeframe
		self.exchange = Binance()
		self.df = self.exchange.GetSymbolKlines(symbol, timeframe, 10000)
		self.last_price = self.df['close'][len(self.df['close'])-1]

#%%
	def plotData(self, buy_signals = False, sell_signals = False, plot_title:str="",
	indicators=[
		dict(col_name="fast_ema", color="indianred", name="FAST EMA"), 
		dict(col_name="50_ema", color="indianred", name="50 EMA"), 
		dict(col_name="200_ema", color="indianred", name="200 EMA")]):
		df = self.df

		# plot candlestick chart
		candle = go.Candlestick(
			x = df['time'],
			open = df['open'],
			close = df['close'],
			high = df['high'],
			low = df['low'],
			name = "Candlesticks")

		data = [candle]

		for item in indicators:
			if df.__contains__(item['col_name']):
				fsma = go.Scatter(
					x = df['time'],
					y = df[item['col_name']],
					name = item['name'],
					line = dict(color = (item['color'])))
				data.append(fsma)

		if df.__contains__('fast_sma'):
			fsma = go.Scatter(
				x = df['time'],
				y = df['fast_sma'],
				name = "Fast SMA",
				line = dict(color = ('rgba(102, 207, 255, 50)')))
			data.append(fsma)

		if df.__contains__('slow_sma'):
			ssma = go.Scatter(
				x = df['time'],
				y = df['slow_sma'],
				name = "Slow SMA",
				line = dict(color = ('rgba(255, 207, 102, 50)')))
			data.append(ssma)

		if df.__contains__('low_boll'):
			lowbb = go.Scatter(
				x = df['time'],
				y = df['low_boll'],
				name = "Lower Bollinger Band",
				line = dict(color = ('rgba(255, 102, 207, 50)')))
			data.append(lowbb)

		if df.__contains__('tenkansen'):
			trace = go.Scatter(
				x = df['time'],
				y = df['tenkansen'],
				name = "Tenkansen",
				line = dict(color = ('rgba(40, 40, 141, 100)')))
			data.append(trace)
		
		if df.__contains__('kijunsen'):
			trace = go.Scatter(
				x = df['time'],
				y = df['kijunsen'],
				name = "Kijunsen",
				line = dict(color = ('rgba(140, 40, 40, 100)')))
			data.append(trace)

		if df.__contains__('senkou_a'):
			trace = go.Scatter(
				x = df['time'],
				y = df['senkou_a'],
				name = "Senkou A",
				line = dict(color = ('rgba(160, 240, 160, 100)')))
			data.append(trace)

		if df.__contains__('senkou_b'):
			trace = go.Scatter(
				x = df['time'],
				y = df['senkou_b'],
				name = "Senkou B",
				fill = "tonexty",
				line = dict(color = ('rgba(240, 160, 160, 50)')))
			data.append(trace)

		if buy_signals:
			buys = go.Scatter(
					x = [item[0] for item in buy_signals],
					y = [item[1] for item in buy_signals],
					name = "Buy Signals",
					mode = "markers",
					marker_size = 20
				)
			data.append(buys)

		if sell_signals:
			sells = go.Scatter(
				x = [item[0] for item in sell_signals],
				y = [item[1] for item in sell_signals],
				name = "Sell Signals",
				mode = "markers",
				marker_size = 20
			)
			data.append(sells)

		layout = go.Layout(
			title=plot_title,
			xaxis = {
				"title" : self.symbol,
				"rangeslider" : {"visible": False},
				"type" : "date"
			},
			yaxis = {
				"fixedrange" : False,
			})
			
		fig = go.Figure(data = data, layout = layout)

		plot(fig, filename='graphs/'+plot_title+'.html')
