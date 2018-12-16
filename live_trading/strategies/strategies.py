import datetime
import sys

from live_trading.live_trading import LiveTrading
from live_trading.logging_ import logging_
from live_trading.utils import exceptions_
from live_trading.utils.helpers import ClientSharedMemory, MethodManager_

class DUMMIES:
    __slots__ = ['dummy_data', 'dummy_instr', 'dummy_time', 'dummy_hour', 'dummy_minute', 'dummy_second',
                 'raise_errors', 'paper_trading', 'get_meths']

    def __init__(self):
        self.dummy_data = False
        self.dummy_instr = ['FB', 'AMZN', 'GOOG', 'TSLA']
        self.dummy_time = True
        self.dummy_hour, self.dummy_minute, self.dummy_second = 15, 30, 0
        self.raise_errors = True
        self.paper_trading = True
        self.get_meths = False

PARALLEL_TRADED_INSTR_PER_STRAT = 2
MAX_N_STRATS_PER_EXECUTION = 3
DEBUGGING, RUNTIME_TM = DUMMIES(), datetime.datetime.now()

class Strategies(ClientSharedMemory, MethodManager_):
    def __init__(self, strat_name, n_strats, client_id, universe, traded_instr, heartbeat_q, manager_,
                 bar_size_secs, order_type, instr_select, instr_select_args, signals, signal_args):
        super(Strategies, self).__init__()
        self.debugging = DEBUGGING
        # self.DummyLogic = DummyLogic
        self.runtime_tm = RUNTIME_TM
        self.parallel_traded_instr_per_strat = PARALLEL_TRADED_INSTR_PER_STRAT \
            if n_strats <= MAX_N_STRATS_PER_EXECUTION \
            else int(MAX_N_STRATS_PER_EXECUTION / n_strats * PARALLEL_TRADED_INSTR_PER_STRAT)
        self.strat_name = strat_name
        self.n_strats = n_strats
        self.client_id = client_id
        self.bar_size_secs = bar_size_secs

        # self.parallel_traded_instr_per_strat = PARALLEL_TRADED_INSTR_PER_STRAT

        self.lt = LiveTrading(self.strat_name, self.client_id, self.runtime_tm, self.debugging, manager_, heartbeat_q, traded_instr)

        if n_strats > MAX_N_STRATS_PER_EXECUTION:
            raise exceptions_.TooManyStratsError
        if not self.pacing_pre_check(self.lt._get_ib_pacing(), n_strats, self.parallel_traded_instr_per_strat,
                                     bar_size_secs, self.lt.potential_mkt_data_lines_already_in_use):
            raise exceptions_.TooMuchMktDptStreaming
        # if self.debugging.get_meths:
        #     self.print_meths(str(self.__class__.__name__), dir(self))

    def run_(self):
        pass

    def update_trade_flow(self, ticker):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        # self.lt.add_to_monitor(*log.monitor())
        price, offer_size, size, status = None, None, None, None
        try:
            curr_n_trades = self.lt.cnt_trades_per_instr_per_day[ticker.contract.symbol]
        except KeyError:
            curr_n_trades = 0
        if ticker.contract.symbol not in self.lt.portfolio_instr and curr_n_trades < self.max_trades_per_instr_per_day:
            self.__make_trade_decision(ticker, 'BUY')
        elif ticker.contract.symbol in self.lt.portfolio_instr:
            self.__make_trade_decision(ticker, 'SELL')
        log.log(price
            ,offer_size
            ,size
            ,status)
        self.add_to_manager(self.strat_name, 'n loops update_trade_flow', 'increment_1')
        # self.lt.heartbeat_q.put([self.strat_name, 'n loops update_trade_flow', 'increment_1'])

    def __make_trade_decision(self, ticker, order):
        pass

    def pacing_pre_check(self, ib_pacing, n_strats, parallel_traded_instr_per_strat, bar_size_secs_, potential_mkt_data_lines_already_in_use):
        mkt_data_lines = ib_pacing['mkt_data_lines'] < (n_strats * parallel_traded_instr_per_strat) + potential_mkt_data_lines_already_in_use
        if mkt_data_lines:
            return False
        # hist data check with bar size
        return True
