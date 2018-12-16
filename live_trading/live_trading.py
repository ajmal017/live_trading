import sys
import datetime
import time
#import socket
#import psutil
# import traceback
from .logging_ import logging_
from .cashmanagement import CashManagement
from .reporting import Reporting
from .utils.helpers import ClientSharedMemory, MethodManager_
from .utils import exceptions_
from .strategies.generalmiscfactors.fundamentaldata import FinRatios

from ib_insync import IB, MarketOrder, util

#from ib_insync.ticker import Ticker

# class PaperTradingWrapper(wrapper.EWrapper):
#     def __init__(self):
#         wrapper.EWrapper.__init__(self)
#
# class PaperTradingClient(EClient):
#     def __init__(self, wrapper):
#         EClient.__init__(self, wrapper)
#
# class PaperTradingApp(PaperTradingWrapper, PaperTradingClient):
#     def __int__(self):
#         PaperTradingWrapper.__init__(self)
#         PaperTradingClient.__init__(self, wrapper=self)
#     def start(self):
#         print('started')

ACCOUNT_CURR = 'DKK'
TAX_RATE_ACCOUNT_COUNTRY = .27

# Making more than 60 requests within any ten minute period.
# Making six or more historical data requests for the same Contract, Exchange and Tick Type within two seconds.
# Making identical historical data requests within 15 seconds.
IB_PACING = {'mkt_data_lines': 100, # = requests
             'hist_data_general_reqs_per_interval': {'secs': 10 * 60, 'reqs': 60},
             'hist_data_similar': {'secs': 2, 'reqs': 6},
             'hist_data_identical': {'secs': 15, 'reqs': 1},
             'funda_data_reqs':{'secs': 600, 'reqs': 60}}
N_TRIES_IF_SIMULT_REQS, SIMULT_REQS_INTERVAL = 5, .5

MARKET_DATA_LINES = 100
POTENTIAL_MKT_DATA_LINES_ALREADY_IN_USE = 6

HOUR_DAY_BOUNDARY_FAIL_CHECK = 6

ORDER_CANCEL_IF_NOT_FILLED_SECS = 10
ORDER_FILLED_CHECKED_CYCLE_SECS = .5


class LiveTrading(MethodManager_):
    def __init__(self, strat_name, client_id, runtime_tm, debugging, manager_, heartbeat_q, traded_instr):
        self.strat_name = strat_name
        self.client_id = client_id
        self.runtime_tm = runtime_tm
        self.debugging = debugging
        self.manager_ = manager_
        self.heartbeat_q = heartbeat_q
        self.traded_instr = traded_instr

        self.account_curr = ACCOUNT_CURR
        self.tax_rate_account_country = TAX_RATE_ACCOUNT_COUNTRY
        self.simult_reqs_interval = SIMULT_REQS_INTERVAL
        self.potential_mkt_data_lines_already_in_use = POTENTIAL_MKT_DATA_LINES_ALREADY_IN_USE

        self.ib = IB()
        # self.ib.setCallback('error', self.on_ib_error)
        self.ib.errorEvent += self.on_ib_error
        self.err_ = None

        self.report = Reporting(self)
        self.cash = CashManagement(debugging)
        self.hlprs = ClientSharedMemory()

        self.access_type = 'tws'
        if self.access_type == 'gateway':
            self.__port = 4001
        elif self.access_type == 'tws':
            self.__port = 7497
        self.__host = '127.0.0.1'
        self.ib.connect(self.__host, self.__port, clientId=self.client_id)

        self.portfolio = []
        self.portfolio_instr = []
        self.cnt_trades_per_instr_per_day = {}

        self.req_tracker = {'total':0,
                               'open_market_data_reqs':0,
                               'open_market_data_lines':0,
                               'hist_data_prior_time':None}

        self.start_cet = datetime.datetime.now()

        self.manager_['active_mkt_data_lines'] = POTENTIAL_MKT_DATA_LINES_ALREADY_IN_USE
        self.funda_data_req_max = IB_PACING['funda_data_reqs']['reqs']

        if self.debugging.get_meths:
            self.print_meths(str(self.__class__.__name__), dir(self))

        _inst_ = self
        self.fin_ratios = FinRatios(_inst_)

    @staticmethod
    def us_tz_op(dt_obj):
        """
        Converting time
        :param dt_obj: datetime obj
        :return: Eastern datetime
        """
        # log_start = datetime.datetime.now()
        if not isinstance(dt_obj, datetime.datetime):
            raise TypeError
        if dt_obj.year == 1900:
            curr_year = datetime.datetime.now().year
        else:
            curr_year = dt_obj.year
        # http://www.webexhibits.org/daylightsaving/b2.html
        dst = {
            2018:[[3,11],[11,4]],
            2019:[[3,10],[11,3]],
            2020:[[3,8],[11,1]]
        }
        window = dst[curr_year]

        #disclaimer
        kind_of_difference = HOUR_DAY_BOUNDARY_FAIL_CHECK
        if dt_obj.hour < kind_of_difference:
            raise Exception("determination difficult, try later in the day")

        dst_start = datetime.datetime(curr_year, window[0][0], window[0][1])
        dst_end = datetime.datetime(curr_year, window[1][0], window[1][1])
        if dt_obj > dst_start and dt_obj < dst_end:
            utc2est = -4
        else:
            utc2est = -5
        this_tz_from_uts = '+0100'
        if time.strftime("%z", time.gmtime()) != this_tz_from_uts:
            raise exceptions_.WrongTimeZone('Wrong time zone, code is fixed to Danish winter time, might have to be adjusted')

        cet2utc = -2
        dt_obj_utc = dt_obj + datetime.timedelta(hours=cet2utc) #.replace(tzinfo = datetime.timezone.utc)
        dt_obj_est = dt_obj_utc + datetime.timedelta(hours=utc2est)
        # logging = rk_logging.Logging()
        # logging.log(
        #         runtime_tm, log_start, str('' + ',' + sys._getframe().f_code.co_name)
        #         ,dt_obj_utc
        #         ,dt_obj_est
        #     )
        return dt_obj_est

    def _manipulated_time(self, cet_in):
        delta = cet_in - self.start_cet
        current_manipulated_time = datetime.datetime(self.start_cet.year,
                                                        self.start_cet.month,
                                                        self.start_cet.day,
                                                        self.debugging.dummy_hour,
                                                        self.debugging.dummy_minute,
                                                        self.debugging.dummy_second)
        current_manipulated_time += delta
        return current_manipulated_time

    def buy(self, ticker, rank, size, order_type):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.hlprs.add_to_manager(self.strat_name, *log.monitor())
        order_log_msg = None
        symbol = ticker.contract.symbol
        if self._ticker_len_n_type_check(ticker.domBids) > 1:
            offer_price = ticker.domBids[rank].price
            # offer_size = ticker.domBids[rank].size
        else:
            offer_price = ticker.domBids.price
            # offer_size = ticker.domBids.size
        cnt = 0
        max_order_filled_cnts = int(ORDER_CANCEL_IF_NOT_FILLED_SECS / ORDER_FILLED_CHECKED_CYCLE_SECS)
        if self.debugging.dummy_data:
            order_success = True
        else:
            if order_type == 'MKT':
                order = MarketOrder('BUY', size)
                trade = self.ib.placeOrder(ticker.contract, order)
                while cnt < max_order_filled_cnts: # a bit complicated but it does actually make sense
                    order_log_msg = trade.log
                    self.ib.sleep(ORDER_FILLED_CHECKED_CYCLE_SECS)
                    cnt += 1
                    if not trade.orderStatus.status != 'Filled':
                        # PendingSubmit = 'PendingSubmit'
                        # PendingCancel = 'PendingCancel'
                        # PreSubmitted = 'PreSubmitted'
                        # Submitted = 'Submitted'
                        # ApiPending = 'ApiPending'  # undocumented, can be returned from req(All)OpenOrders
                        # ApiCancelled = 'ApiCancelled'
                        # Cancelled = 'Cancelled'
                        # Filled = 'Filled'
                        # Inactive = 'Inactive'
                        order_success = True
                        break
                else:
                    self.ib.cancelOrder(trade)
                # while not trade.isDone():
                #     print("not sure if this makes sense")
                #     self.ib.waitOnUpdate()
            elif order_type == 'LMT':
                raise Exception("order type not defined")
            else:
                raise Exception("order type not defined")
        if order_success:
            if self.debugging.dummy_time:
                _now = self._manipulated_time(datetime.datetime.now())
            else:
                _now = datetime.datetime.now()

            filled_tm = self.us_tz_op(_now)
            status = 0
            self.portfolio.append([symbol, filled_tm, offer_price, size])
            self.hlprs.add_to_manager(self.strat_name, 'portfolio', self.portfolio)

            self.portfolio_instr.append(symbol)
            # self.add_to_monitor('portfolio_instr', 'self.portfolio_instr')

            print('not sure if this works')
            self.cnt_trades_per_instr_per_day[ticker.contract.symbol] += 1
            self.hlprs.add_to_manager(self.strat_name, 'cnt_trades_per_instr_per_day',
                           self.cnt_trades_per_instr_per_day)
            self.heartbeat_q.put([self.strat_name, 'cnt_trades_per_instr_per_day',self.cnt_trades_per_instr_per_day])
            self.hlprs.add_to_manager(self.strat_name, 'cap_usd',
                                      self.cash.available_funds(self.report.pnl(), self.account_curr))
        else:
            status = 1
        log.log(self.portfolio
                ,self.portfolio_instr
                ,self.cnt_trades_per_instr_per_day
                ,order_log_msg)
        return status

    def sell(self, ticker, rank, order_type):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.hlprs.add_to_manager(self.strat_name, *log.monitor())
        order_log_msg = None
        symbol = ticker.contract.symbol
        try:
            ix = self.portfolio_instr.index(symbol)
        except ValueError:
            status = -1
            print('not quite sure why this error sometimes occurs and if this is maybe to early to leave?')
            return status

        # if isinstance(ticker.domBids, str) == True:
        #     offer_price = ticker.domAsks.price
        #     offer_size = ticker.domAsks.size
        # else:
        #     offer_price = ticker.domAsks[rank].price
        #     offer_size = ticker.domAsks[rank].size
        price_ix = 2
        size_ix = 3
        # held_price = self.held[ix][price_ix]
        held_size = self.portfolio[ix][size_ix]

        cnt = 0
        max_order_filled_cnts = int(ORDER_CANCEL_IF_NOT_FILLED_SECS / ORDER_FILLED_CHECKED_CYCLE_SECS)
        if not self.debugging.dummy_data:
            if order_type == 'MKT':
                order = MarketOrder('SELL', held_size)
                # https://github.com/erdewit/ib_insync/blob/master/notebooks/ordering.ipynb
                trade = self.ib.placeOrder(ticker.contract, order)
                while cnt < max_order_filled_cnts:
                    order_log_msg = trade.log
                    self.ib.sleep(ORDER_FILLED_CHECKED_CYCLE_SECS)
                    cnt += 1
                    if trade.orderStatus.status == 'Filled':
                        order_success = True
                        break
                self.ib.cancelOrder(trade)
                while not trade.isDone():
                    print("not sure if this makes sense")
                    self.ib.waitOnUpdate()
            elif order_type == 'LMT':
                raise Exception("order type not defined")
            else:
                raise Exception("order type not defined")
        else:
            order_success = True
        order_success = True
        if order_success:
            status = 0
            del self.portfolio[ix]
            self.hlprs.add_to_manager(self.strat_name, 'portfolio', self.portfolio)
            del self.portfolio_instr[ix]
            # self.add_to_monitor('portfolio_instr', self.portfolio_instr)
            print('not sure if this works')
            self.cnt_trades_per_instr_per_day[ticker.contract.symbol] += 1
            self.hlprs.add_to_manager(self.strat_name, 'cnt_trades_per_instr_per_day',
                           self.cnt_trades_per_instr_per_day)
            self.heartbeat_q.put([self.strat_name, 'cnt_trades_per_instr_per_day',self.cnt_trades_per_instr_per_day])
            self.hlprs.add_to_manager(self.strat_name, 'cap_usd', self.cash.available_funds(self.report.pnl(), self.account_curr))
        else:
            status = 1
        log.log(self.portfolio
                ,self.portfolio_instr
                ,self.cnt_trades_per_instr_per_day
                ,order_log_msg)
        return status

    @staticmethod
    def _ticker_len_n_type_check(bid_or_ask_li):
        # log_start = datetime.datetime.now()
        n_ticks = len(bid_or_ask_li) if isinstance(bid_or_ask_li, str) == False else 1
        # log = rk_logging.Logging()
        # log.log(
        #     self.runtime_tm, log_start, str('' + ',' + sys._getframe().f_code.co_name)
        # )
        return n_ticks

    def req_handling(self, ticker, type_):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.hlprs.add_to_manager(self.strat_name, *log.monitor())
        # unix_ts = int(time.time())
        self.req_tracker['total'] += 1
        self.req_tracker['open_market_data_reqs'] += 1
        self.req_tracker['open_market_data_lines'] += 1

        # status = -1 means immediately kill connections
        status = self.pacing_violations(type_)
        log.log()
        if status == -1:
            print('get connections here')
            # do sth
            return
        elif status == 0:
            return

    def req_handler(self, toggle):
        if toggle == 'increase':
            self.manager_['active_mkt_data_lines'] += 1
        elif toggle == 'decrease':
            self.manager_['active_mkt_data_lines'] -= 1
        else:
            raise Exception('not defined')

    def req_mkt_dpt_ticker_(self, contract_):
        _cnt_ = 0
        status = 1
        while _cnt_ < N_TRIES_IF_SIMULT_REQS:
            if self.manager_['active_mkt_data_lines'] < IB_PACING['mkt_data_lines']:
                self.req_handler('increase')
                ticker = self.ib.reqMktDepth(contract_)
                self.ib.sleep(SIMULT_REQS_INTERVAL)  # wait here because ticker needs updateEvent might not be fast enough
            else:
                self.ib.sleep(SIMULT_REQS_INTERVAL)  # wait here because ticker needs updateEvent might not be fast enough
                _cnt_ += 1
                continue
            if self.err_ != exceptions_.IbPacingError:
                status = 0
                break
        return ticker, status

    def cancel_mkt_dpt_ticker_(self, contract_):
        self.ib.cancelMktDepth(contract_)
        self.req_handler('decrease')

    @staticmethod
    def _get_ib_pacing():
        return IB_PACING

    def pacing_violations(self, type_):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.hlprs.add_to_manager(self.strat_name, *log.monitor())
        # histData, mktDepth, scannerData

        # TODO: far from done here, continue at some point
        status = 0
        if type_ == 'histData':
            if self.req_tracker['total'] == 1: #first time is already incremented
                self.req_tracker['hist_data_prior_time'] = int(time.time())
                status = 0
            elif self.req_tracker['total'] > 1 and self.req_tracker['open_market_data_lines'] < MARKET_DATA_LINES:
                status = 0
            elif self.req_tracker['total'] > 1 \
                    and self.req_tracker['open_market_data_lines'] == MARKET_DATA_LINES \
                    and int(time.time()) - self.req_tracker['hist_data_prior_time'] >= IB_PACING['hist_data_similar']['secs']:
                print('CRITICAL: market data lines limit reached')
                status = -1
        elif type_ == 'mktDepth':
            status = 0
        elif type_ == 'scannerData':
            status = 0
        log.log(status
            ,self.req_tracker)
        self.hlprs.add_to_manager(self.strat_name, *log.monitor())
        return status

    def check_network_requirements(self):
        # s = socket.socket()
        # #e.g.
        # address, port = '10.8.8.19', '53141'
        # address, port = '208.245.107.3', '4000'
        # try:
        #     s.connect((address, port))
        #     return True
        # except socket.error:
        #     return False
        # #or
        # rows = []
        # lc = psutil.net_connections('inet')
        # for c in lc:
        #     (ip, port) = c.laddr  # 0.0.0.0
        #     if ip == '10.8.8.19':  # or ip == '::'
        #         if c.type == socket.SOCK_STREAM and c.status == psutil.CONN_LISTEN:
        #             proto_s = 'tcp'
        #         elif c.type == socket.SOCK_DGRAM:
        #             proto_s = 'udp'
        #         else:
        #             continue
        #         pid_s = str(c.pid) if c.pid else '(unknown)'
        #         msg = 'PID {} is listening on port {}/{} for all IPs.'
        #         msg = msg.format(pid_s, port, proto_s)
        #         print(msg)
        status = True
        if not status:
            raise Exception('cannot connect to all necessary servers')
#
    def on_ib_error(self, reqId, errorCode, errorString, errorSomething):
        """
        https://groups.io/g/insync/topic/how_to_capture_error_trapped/7718294?p=,,,20,0,0,0::recentpostdate%2Fsticky,,,20,1,80,7718294
        """
        max_n_mkt_depth_reqs = 309  # ERROR:ib_insync.wrapper:Error 309, reqId 39: Max number (3) of market depth requests has been reached, contract: Stock(symbol='PETZ', exchange='ISLAND', currency='USD')
        if errorCode == max_n_mkt_depth_reqs:
            self.err_ = exceptions_.IbPacingError
# def print_meth_name_f(_instance, func, *args, **kwargs):
#     """
#     https://wiki.python.org/moin/FunctionWrappers
#
#     Doesn\t really work all this
#
#     on module level, not in classes
#     first meth params: pre, post
#
#     def trace_in(func, *args, **kwargs):
#         print("Entering function", func.__name__)
#
#     def trace_out(func, *args, **kwargs):
#         print("Leaving function", func.__name__)
#
#     @print_meth_name(trace_in, trace_out)
#     def calc(x, y):
#         return x + y
#
#     in call
#     pre(func, *args, **kwargs)
#     ...
#     post(func, *args, **kwargs)
#     """
#     def decorate(_instance, func, *args, **kwargs):
#         def call(_instance, func, *args, **kwargs):
#             if print_meth_name:
#                 print('starting ', func.__name__)
#             result = func(_instance, *args, **kwargs)
#             if print_meth_name:
#                 print('finished ', func.__name__)
#             return result
#         return call
#     return decorate

# if __name__ == "__main__":
#     main()
