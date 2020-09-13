# Class used to compute indicators on a dataframe. We're creating it in order to separate it from the rest of the code that is not related.
# Here, we import indicators from external libraries, but also write our own functions for computing indicators

from pyti.smoothed_moving_average import smoothed_moving_average as sma
from pyti.exponential_moving_average import exponential_moving_average as ema
from pyti.bollinger_bands import lower_bollinger_band as lbb
from pyti.bollinger_bands import upper_bollinger_band as ubb

#%%
def ComputeIchimokuCloud(df):
	""" Taken from the python for finance blog """

	# Tenkan-sen (Conversion Line): (9-period hign + 9-period low)/2
	nine_period_high = df['high'].rolling(window=9).max()
	nine_period_low = df['low'].rolling(window=9).min()
	df['tenkansen'] = (nine_period_high + nine_period_low)/2

	# Kijun-sen (Base Line): (26-period high + 26-period low)/2
	period26_high = df['high'].rolling(window=26).max()
	period26_low = df['low'].rolling(window=26).min()
	df['kijunsen'] = (period26_high + period26_low)/2

	# Senkou Span A (Leading Span A): (Conversion Line + Base Line)/2
	df['senkou_a'] = ((df['tenkansen'] + df['kijunsen']) / 2 ).shift(26)

	# Senkou Span B
	period52_high = df['high'].rolling(window=52).max()
	period52_low = df['low'].rolling(window=52).min()
	df['senkou_b'] = ((period52_high + period52_low) / 2).shift(52)

	# Chikou Span: Most recent closing price, plotted 26 periods behind (optional)
	df['chikouspan'] = df['close'].shift(-26)

	return df

#%%
class Indicators:

	# Here, we're putting all indicators that we have access to (we can add any
	# number of indicators here); The purpose of this dict will become apparent

	INDICATORS_DICT = {
		"sma": sma,
		"ema": ema,
		"lbb": lbb,
		"ubb": ubb,
		"ichimoku": ComputeIchimokuCloud,
	}

#%%
	@staticmethod
	def AddIndicator(df, indicator_name, col_name, args):
		""" df is the dataframe to which we will add the indicator
		indicator_name is the name of the indicator as found in the dict above
		col_name is the name that the indicator will appear under in the dataframe
		args are arguments that might be used when calling the indicator function"""
		try:
			if indicator_name == "ichimoku": 
				# this is a special case, because it will create more columns in the df
				df = ComputeIchimokuCloud(df)
			else:
				df[col_name] = Indicators.INDICATORS_DICT[indicator_name](df['close'].tolist(), args)
		except Exception as e:
			print("\nException raised when trying to compute "+indicator_name)
			print(e)