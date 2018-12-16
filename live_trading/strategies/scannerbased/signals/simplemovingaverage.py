import datetime
import sys
import pandas as pd

from live_trading.logging_ import logging_

from .signals import Signals

STOP_LOSS = .2
MINS_SELL_BEFORE_EOB =  15

class SimpleMovingAverage(Signals):
    def __init__(self, strategy, long_periods, short_periods):
        super(SimpleMovingAverage, self).__init__()
        self.strategy = strategy
        self.long_periods = long_periods
        self.short_periods = short_periods

    # @classmethod
    def __buy_conditions(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        # try:
        #     short_ma_greater_than_long = self.__moving_averages(ticker)
        # except:
        #     short_ma_greater_than_long = True
        return_minimal = True
        status = True
        while status:
            # if not short_ma_greater_than_long:
            #     return False
            if not return_minimal:
                status = False
            break
        if not status:
            self.strategy.add_to_manager(self.strategy.strat_name, 'n False buy_conditions', 'increment_1')
        log.log(return_minimal)
        return status

    def __sell_conditions(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        price_higher_than_bought = self.__price_higher_than_bought(ticker)
        sell_at_eob = self.__sell_at_eob_f()
        try:
            short_ma_greater_than_long = self.__moving_averages(ticker)
        except Exception as e:
            short_ma_greater_than_long = True
            print('this may be problematic')
        status = True
        while status:
            if not price_higher_than_bought:
                status = False
            if not sell_at_eob:
                status = False
            if short_ma_greater_than_long:
                status = False
            break
        if not status:
            self.strategy.add_to_manager(self.strategy.strat_name, 'n False sell_conditions', 'increment_1')
        log.log(price_higher_than_bought
                ,short_ma_greater_than_long
                ,sell_at_eob)
        return status

    # @print_meth_name
    def price_size_select(self, ticker, ix, side):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        if side == 1:
            items = ticker.domBids
        else:
            items = ticker.domAsks
        _len = self.strategy.lt._ticker_len_n_type_check(items)
        if _len > 1:
            # if self.market_open.debugging:
            if self.strategy.debugging.dummy_data:
                # price, size = float(random.randint(10, 100)), random.randint(100, 10000)
                price, size = items[ix].price, items[ix].size
            else:
                price, size = items[ix].price, items[ix].size
        else:
            # if self.market_open.debugging:
            if self.strategy.debugging.dummy_data:
                # price, size = float(random.randint(10, 100)), random.randint(100, 10000)
                price, size = items.price, items.size
            else:
                price, size = items.price, items.size
        log.log(price
                ,size)
        return price, size

    def sell_at_eob_f(self):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        if self.strategy.debugging.dummy_time:
            _now = self.strategy.lt._manipulated_time(datetime.datetime.now())
        else:
            _now = datetime.datetime.now()

        if self.strategy.eob_min >= MINS_SELL_BEFORE_EOB:
            eob_dt = datetime.datetime.strptime("{}:{}:00".format(self.strategy.eob_hour,
                                                                  str(30 - MINS_SELL_BEFORE_EOB)), '%H:%M:%S')
        else:
            hour = self.strategy.eob_hour - 1
            minute = 60 + self.strategy.eob_min - MINS_SELL_BEFORE_EOB
            eob_dt = datetime.datetime.strptime("{}:{}:00".format(str(hour), str(minute)),'%H:%M:%S')
        sell_at_eob = self.strategy.lt.us_tz_op(_now).time() > eob_dt.time()
        log.log(sell_at_eob)
        return sell_at_eob

    def __price_higher_than_bought(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        symbol =  ticker.contract.symbol
        held_ix = self.strategy.lt.portfolio_instr.index(symbol)
        held_price_ix = 2
        held_price = self.strategy.lt.portfolio[held_ix][held_price_ix]
        rank = 0
        if self.strategy.lt._ticker_len_n_type_check(ticker.domBids) > 1:
            curr_price = ticker.domAsks[rank].price
        else:
            curr_price = ticker.domAsks.price
        log.log(self.strategy.lt.portfolio
                ,curr_price)
        if held_price < curr_price:
            return True
        else:
            return False

    def stop_loss_f(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        if self.strategy.lt._ticker_len_n_type_check(ticker.domAsks) > 1:
            current_ask_price = ticker.domAsks[0].price
        else:
            current_ask_price = ticker.domAsks.price
        change = (current_ask_price - self.strategy.lt.portfolio[ticker.contract.symbol]) / current_ask_price
        log.log(current_ask_price
                ,change)
        if change < -STOP_LOSS:
            return True
        else:
            return False

    # @classmethod
    def __moving_averages(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        # ma procedure
        long_ma, short_ma = self.__ma_calc('collected', ticker)
        if long_ma == np.nan and short_ma == np.nan:
            raise Exception('not defined')
        elif long_ma > short_ma:
            short_ma_greater_than_long = False
        else:
            short_ma_greater_than_long = True
        log.log(long_ma
                ,short_ma)
        return short_ma_greater_than_long

    def __ma_calc(self, by, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strategy.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strategy.add_to_manager(self.strategy.strat_name, *log.monitor())
        long_ma, short_ma = None, None
        if by == 'collected':
            rank = 0
            # side
            # bid = 1
            # ask = 0
            side = 1
            self.filtered_df = self.strategy.__hist_data_winners_df[(self.strategy.__hist_data_winners_df['symbol'] == ticker.contract.symbol) &
                                                                    (self.strategy.__hist_data_winners_df['side'] == side) &
                                                                    (self.strategy.__hist_data_winners_df['rank'] == rank)]
            _length = self.filtered_df.shape[0]
            if _length < self.long_periods:
                long_ma, short_ma = np.nan, np.nan
            else:
                long_ma = self.filtered_df.sort_values('unix_ts', ascending=False)[0:self.long_periods]['price'].mean()
                short_ma = self.filtered_df.sort_values('unix_ts', ascending=False)[0:self.short_periods]['price'].mean()
                # print(long_ma, short_ma)
                _unix_ts = self.filtered_df['unix_ts'].sort_values(ascending=False).iloc[0]
                if self.strategy.ma_counter == 0:
                    self._ma_collection_df = pd.DataFrame([[ticker.contract.symbol, _unix_ts, short_ma, long_ma]])

                else:
                    add_df = pd.DataFrame([[ticker.contract.symbol,
                               _unix_ts,
                               short_ma,
                               long_ma]])
                    self._ma_collection_df = pd.concat([self._ma_collection_df, add_df])

        log.log(long_ma
                ,short_ma)
        return long_ma, short_ma
