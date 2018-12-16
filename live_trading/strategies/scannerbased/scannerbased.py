import sys
import datetime
import pandas as pd

from live_trading.logging_ import logging_
from live_trading.utils import exceptions_, consoledisplay
from live_trading.utils import helpers
from live_trading.strategies.strategies import Strategies
from .riskmanagement.riskmanagement import RiskManagement

ITERATION_TIMEOUT_SECS = 20
CONTINUOUS_ERR_MAX_FOR_SLEEPING, SLEEP_TIME_IF_ERROR = 50, 2

COUNTRY = 'US'
MARKET_OPEN = '09:30:00'
EOB_HOUR, EOB_MIN = 15, 30

MKT_DATA_COST_USD = 25.0
MAX_PRICE_INSTR_USD = 500.0
MAX_TRADES_PER_INSTR_PER_DAY = 4  # min 2, even number because of sell EOD)
N_WILLINGNESS_TO_MOVE_UP_PRICE = 4

MA_PATIENCE_TO_TURN_MINS = 45


class ScannerBased(Strategies):
    def __init__(self, strat_name, n_strats, client_id, universe, traded_instr,
                 heartbeat_q, manager_, bar_size_secs, order_type, instr_select, instr_select_args, signals, signal_args):
        super(ScannerBased, self).__init__(strat_name, n_strats, client_id, universe, traded_instr,
                                           heartbeat_q, manager_, bar_size_secs, order_type, instr_select,
                                           instr_select_args, signals, signal_args)
        self.bar_size_secs = bar_size_secs
        self.max_trades_per_instr_per_day = MAX_TRADES_PER_INSTR_PER_DAY
        self.max_price_instr_usd = MAX_PRICE_INSTR_USD
        self.iteration_timeout_secs = ITERATION_TIMEOUT_SECS

        self.strat_name = strat_name
        self.universe = universe
        self.instr_select = instr_select
        self.order_type = order_type
        self.instr_select_args = instr_select_args
        self.signal_args = signal_args
        self.signals = signals(self, *self.signal_args)

        # self.DummyLogic.__init__(self)
        # self.lt = manager_
        self.rm = RiskManagement(self)
        self.exc = exceptions_.ExceptionHandling(self.runtime_tm, CONTINUOUS_ERR_MAX_FOR_SLEEPING, SLEEP_TIME_IF_ERROR)
        self.cons_disp = consoledisplay.ConsoleDisplay()

        self.eob_hour, self.eob_min = EOB_HOUR, EOB_MIN

        self._ma_collection_df = pd.DataFrame(columns=['symbol','unix_ts','short_ma','long_ma'])
        self.n_willingness_to_move_up_price = N_WILLINGNESS_TO_MOVE_UP_PRICE #times, alter deducted by 1
        self.ma_counter = 0
        # self.__traded_instr = None
        # self.__winners = None
        self.starting_cap_usd = self.lt.cash.available_funds(self.lt.report.pnl(), self.lt.account_curr)
        if self.debugging.get_meths:
            self.print_meths(str(self.__class__.__name__), dir(self))
        self.run_()

    def run_(self):
        self.lt.check_network_requirements()
        while True:
            try:
                while not self._start_routine_check():
                    self.lt.ib.sleep(5)
                    continue

                # if self.hedge():
                #     break
                self.instr_select(self.bar_size_secs, self.order_type, self.instr_select_args, self, self.signals)

            except Exception as e:
                self.exc.handle_(e, self.debugging.raise_errors)
                self.add_to_manager(self.strat_name, 'continuous_err_cnt', self.exc.continuous_err_cnt)
                self.lt.heartbeat_q.put([self.strat_name, 'continuous_err_cnt', self.exc.continuous_err_cnt])
                if self.exc.continuous_err_exceeded():
                    self.lt.ib.sleep(self.exc.sleep_time_if_error)

    def hedge(self):
        # self.sma1 = SimpleMovingAverage(self, MAS1_LONG_PERIODS, MAS1_SHORT_PERIODS)
        # Scanners_1(self, self.sma1)
        # self.sma1 = SimpleMovingAverage(self, MAS1_LONG_PERIODS, MAS1_SHORT_PERIODS)
        #
        # procs = []
        # # manager_ = Manager().dict()
        # self.lt.add_to_monitor('market_open', self)
        # p = Process(target=Scanners_1, args=(self, self.lt.monitor, self.sma1))
        # p.start()
        # procs.append(p)
        # for p in procs:
        #     p.join()
        done = True
        return done

    def _start_routine_check(self):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.add_to_manager(self.strat_name, *log.monitor())
        if self.debugging.dummy_time:
            _now = self.lt._manipulated_time(datetime.datetime.now())
        else:
            _now = datetime.datetime.now()
        current = self.lt.us_tz_op(_now).time()
        op = datetime.datetime.strptime(MARKET_OPEN, '%H:%M:%S').time()
        if current < op:
            status = False
        else:
            status = True
        log.log(status)
        return status

    def _init_trade_cnt(self, _traded_instr):
        self.cons_disp.print_warning('this might be conflicting')
        # print('this might be conflicting')
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.add_to_manager(self.strat_name, *log.monitor())
        if len(_traded_instr) == 0:
            self.lt.cnt_trades_per_instr_per_day = {}
        else:
            for w_ix, wnr in enumerate(_traded_instr):
                if w_ix == 0:
                    self.lt.cnt_trades_per_instr_per_day = {wnr: 0}
                else:
                    self.lt.cnt_trades_per_instr_per_day[wnr] = 0
        self.add_to_manager(self.strat_name, 'cnt_trades_per_instr_per_day',
                       self.lt.cnt_trades_per_instr_per_day)
        self.lt.heartbeat_q.put([self.strat_name, 'cnt_trades_per_instr_per_day', self.lt.cnt_trades_per_instr_per_day])
        log.log()

    def _check_if_done(self):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.add_to_manager(self.strat_name, *log.monitor())
        d_is_empty = lambda x: not bool(x) #empty dict check, turn around
        status = True
        if d_is_empty(self.lt.cnt_trades_per_instr_per_day):
            status = False
        for i in self.lt.cnt_trades_per_instr_per_day.keys():
            if self.lt.cnt_trades_per_instr_per_day[i] < MAX_TRADES_PER_INSTR_PER_DAY:
                status = False
        if status:
            raise exceptions_.MaxTradesPerDayError

        if self.signals.sell_at_eob_f():
            raise exceptions_.SellAtEOBWarning

        log.log(status)

    def conclude_results(self):
        self.lt.report.result_trading_day(self.starting_cap_usd, self.lt.account_curr, self.lt.tax_rate_account_country, MKT_DATA_COST_USD)
