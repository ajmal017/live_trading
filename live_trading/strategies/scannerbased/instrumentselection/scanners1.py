from collections import OrderedDict
import datetime
import time
import sys
from ib_insync import ScannerSubscription, Stock
import random
import pandas as pd
import copy

from live_trading.logging_ import logging_
from live_trading.utils import exceptions_, helpers, consoledisplay
from live_trading.strategies.generalmiscfactors.generalmiscfactors import GeneralMiscFactors
from live_trading.strategies.generalmiscfactors.fundamentaldata import FinRatios

from .instrumentselection import InstrSelection

class FACTORS:
    __slots__ = ['bar_size_secs', 'order_type', 'analysis_logic_start_time', 'trading_logic_start_time', 'positive_factors', 'negative_factors', 'black_list']
    def __init__(self, bar_size_secs, order_type, analysis_logic_start_time, trading_logic_start_time, positive_factors, negative_factors):
        self.bar_size_secs = bar_size_secs
        self.order_type = order_type
        self.analysis_logic_start_time = analysis_logic_start_time
        self.trading_logic_start_time = trading_logic_start_time
        self.positive_factors = positive_factors
        self.negative_factors = negative_factors
        self.black_list = GeneralMiscFactors.black_list
        # self.black_list_empty_throw = lambda black_list: raise TypeError if self.black_list is None else pass
        if self.black_list is None:
            raise TypeError

class Scanners_1(FACTORS, InstrSelection):
    def __init__(self, bar_size_secs, order_type, instr_select_args, strat, signals): #market_open, manager_, signals
        # super(Scanners_1, self).__init__(instr_select_args)
        # helpers.MethodManager_.__init__(self)
        self.strat = strat
        self.signals = signals
        FACTORS.__init__(self, bar_size_secs, order_type, *instr_select_args)
        InstrSelection.__init__(self, self.strat.debugging)

        self.__traded_instr = None
        self.__hist_data_winners_df = pd.DataFrame(columns=['symbol','unix_ts','side','rank','price','size'])
        self.ss = ScannerSubscription()
        self.ss.instrument = "STK"  # STOCK.EU
        self.ss.locationCode = "STK.NASDAQ"  # US.MAJOR
        self.cons_disp = consoledisplay.ConsoleDisplay()
        if self.strat.debugging.get_meths:
            self.print_meths(str(self.__class__.__name__), dir(self))
        self.run_()

    def run_(self):
        if self.strat.debugging.dummy_time:
            _now = self.strat.lt._manipulated_time(datetime.datetime.now())
        else:
            _now = datetime.datetime.now()
        while self.strat.lt.us_tz_op(_now).time() < datetime.datetime.strptime(self.analysis_logic_start_time, '%H:%M:%S').time():
            if self.strat.debugging.dummy_time:
                _now = self.strat.lt._manipulated_time(datetime.datetime.now())
            else:
                _now = datetime.datetime.now()
            self.strat.lt.ib.sleep(5)

        _analysis_logic = datetime.datetime.strptime(self.analysis_logic_start_time, '%H:%M:%S')  # .time()
        _trading_logic = datetime.datetime.strptime(self.trading_logic_start_time, '%H:%M:%S')  # .time()
        _n_iters = int((_trading_logic - _analysis_logic).seconds / 60)
        _tries = 0
        while _tries < _n_iters:
            # if self.market_open.debugging:
            if self.strat.debugging.dummy_data:
                self.__winners = self.strat.debugging.dummy_instr
                break
            else:
                try:
                    self.__winners = self.find_winners(self.strat.parallel_traded_instr_per_strat)
                    self.strat.add_to_manager(self.strat.strat_name, '__winners', self.__winners)
                    break
                except Exception as e:
                    self.cons_disp.print_warning('waiting 60 secs because no winner could be determined in this iteration')
                    self.strat.lt.ib.sleep(60)
                    _tries += 1
        else:
            raise Exception('couldnt determine winners')
        _par = self.strat.parallel_traded_instr_per_strat
        _until = _par if _par < len(self.__winners) else len(self.__winners)
        pre_select = self.__winners[0:_until]
        self._iter_ = 0
        traded_instr_this_strat = self._check_tradeability_of_instr(pre_select)
        while True:
            # for customReqId, symbol in enumerate(self.strat.lt.traded_instr):
            for customReqId, symbol in enumerate(traded_instr_this_strat):
                contract = Stock(symbol, 'ISLAND', 'USD')
                # if self.market_open.debugging:
                status = None
                if self.strat.debugging.dummy_data:
                    if customReqId < len(self.strat.lt.traded_instr):
                        self.last_price = {}
                        self.last_price[symbol] = 236.39
                    # simulate down turn after n minutes
                    mins_down_turn = 4
                    delta_mins = (datetime.datetime.now() - self.strat.lt.start_cet).seconds * 60
                    if delta_mins < mins_down_turn:
                        # _sign = random.choice(['+','-'])
                        _sign = '+'
                    else:
                        _sign = '-'
                    _price = self.last_price[symbol] * float(eval('1.0' + _sign + str(random.uniform(0.001, 0.05))))
                    _size = random.randint(20, 8000)
                    ticker = helpers.Tick_(contract=contract,
                                           domBids=[helpers.Lines_(price=_price + 0.3, size=_size * (1 - 0.15)),
                                                    helpers.Lines_(price=_price + 0.2, size=_size * (1 - 0.10)),
                                                    helpers.Lines_(price=_price + 0.1, size=_size * (1 - 0.05)),
                                                    helpers.Lines_(price=_price, size=_size)],
                                           domAsks=[helpers.Lines_(price=_price - 0.3, size=_size * (1 - 0.05)),
                                                    helpers.Lines_(price=_price - 0.4, size=_size * (1 - 0.10)),
                                                    helpers.Lines_(price=_price - 0.5, size=_size * (1 - 0.15)),
                                                    helpers.Lines_(price=_price - 0.6, size=_size * (1 - 0.20)),
                                                    helpers.Lines_(price=_price - 0.7, size=_size * (1 - 0.25))])
                else:
                    ticker, status = self.strat.lt.req_mkt_dpt_ticker_(contract)
                # self.market_open.lt.req_handling(ticker, 'mktDepth')
                if customReqId == 0:
                    self.last_iteration = datetime.datetime.now()
                    unix_ts = int(time.time())
                if status != 1:
                    status = self.collect_hist_ticks(ticker, unix_ts)
                if status == 1:
                    self.strat.lt.cancel_mkt_dpt_ticker_(contract)
                    next_in_line = self.__winners.pop(0)
                    self.reshuffle_winners(self.strat.parallel_traded_instr_per_strat, next_in_line, remove=symbol)
                    traded_instr_this_strat = self._check_tradeability_of_instr(traded_instr_this_strat)
                    # _trix_ = traded_instr_this_strat.index(symbol)
                    # del traded_instr_this_strat[_trix_]
                    break

                if self._iter_ == 0:
                    # self.scanner_based._init_trade_cnt(self.__traded_instr)
                    self.strat._init_trade_cnt(self.strat.lt.traded_instr)

                self.strat.update_trade_flow(ticker)
                self.strat.lt.cancel_mkt_dpt_ticker_(contract)
                self._iter_ += 1

            while (datetime.datetime.now() - self.last_iteration).seconds < self.strat.bar_size_secs:
                # print('looping through bar seconds gate', '(datetime.datetime.now() - self.last_iteration).seconds < BAR_SIZE_SECS: ',
                #       (datetime.datetime.now() - self.last_iteration).seconds < BAR_SIZE_SECS)
                # self.market_open.lt.ib.sleep(1)
                continue
            try:
                self.strat._check_if_done()
                continue
            except Exception as e:
                self.strat.exc.handle_(e, self.strat.debugging.raise_errors)
            self.strat.conclude_results()
            break

    def find_winners(self, parallel_traded_instr_per_strat):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        hist_data_df = None
        # matches = None
        _analysis_logic = datetime.datetime.strptime(self.analysis_logic_start_time, '%H:%M:%S')
        _trading_logic = datetime.datetime.strptime(self.trading_logic_start_time, '%H:%M:%S')
        _n_iters = int((_trading_logic - _analysis_logic).seconds / 60)
        if self.strat.debugging.dummy_time:
            _now = self.strat.lt._manipulated_time(datetime.datetime.now())
        else:
            _now = datetime.datetime.now()

        _time_gates = [self.strat.lt.us_tz_op(_now) + datetime.timedelta(minutes=ix) for ix, _ in
                       enumerate(range(_n_iters))]  # minutes=ix works fairly well

        _inst_ = self
        del _inst_

        negative_scan_instr, negative_misc_factors = [], []
        _factor_val_ix, _factor_type_ix = 0, 1
        for nf in self.negative_factors:
            v_ = list(nf.values())
            if v_[0][_factor_type_ix] == 'scanner':
                negative_scan_instr.append(v_)
            else:
                negative_misc_factors.append(v_)

        longer_scan_list = len(self.positive_factors) \
            if len(self.positive_factors) >= len(negative_scan_instr) \
            else len(self.negative_factors)
        reduce_from_longer_scan_list = self.positive_factors \
            if len(self.positive_factors) >= len(negative_scan_instr) \
            else self.negative_factors

        for ix, turn in enumerate(range(_n_iters)):
            if ix == 0:
                while True:
                    # first iter, check lenghts and availabilities
                    # this might be too complicated for the small number of factors
                    positive_instr, negative_scan_instr = self.initial_scan_to_sort(longer_scan_list)

                    matches = self.match_f(positive_instr, negative_scan_instr, _n_iters, _first_iter=True)

                    negative_misc_instr = []
                    for nmi_ in negative_misc_factors:
                        if nmi_[0][_factor_type_ix] == 'finRatiosMarketCap':
                            for match in matches[0:int(self.strat.lt.funda_data_req_max / self.strat.n_strats)]:
                                try:
                                    if not self.strat.lt.fin_ratios.mkt_cap(match, nmi_[0][_factor_val_ix]):
                                        negative_misc_instr.append(match)
                                except Exception as e:
                                    print('stop')

                    negative_misc_instr = negative_misc_instr + self.black_list
                    matches = self._remove_misc_negative_instr(negative_misc_instr, matches, self.strat.runtime_tm)

                    if len(matches) < parallel_traded_instr_per_strat and not len(matches) == 0:
                        if self.strat.rm.fraction_sorting_out_negative_list > .0:
                            self._reduce_fraction_sorting_out_negative_list()
                            continue

                        if len(self.negative_factors) > 0:
                            # _key_ = list(self.negative_factors.keys())[0]
                            _key_ = list(self.negative_factors)
                            del self.negative_factors[_key_]
                            continue

                        self.cons_disp.print_warning('not sure if this can be deleted or needs to stay')
                        # if len(self.positive_factors) == 2:
                        #     break

                        # _key_ = list(reduce_from_longer_scan_list.keys())[longer_scan_list - 1]
                        _key_ = list(reduce_from_longer_scan_list.keys())[longer_scan_list - 1]
                        del reduce_from_longer_scan_list[_key_]
                        longer_list = len(self.positive_factors) \
                            if len(self.positive_factors) >= len(self.negative_factors) \
                            else len(self.negative_factors)
                        reduce_from_longer_scan_list = self.positive_factors \
                            if len(self.positive_factors) >= len(self.negative_factors) \
                            else self.negative_factors
                    elif len(matches) == 0:
                        raise exceptions_.TooFewContractsWhileDeterminingError
                    else:
                        break
            else:
                self._time_gates_f(_time_gates, ix)

                _pos_instr, _neg_instr = self.scan_(longer_scan_list)
                for _fctr_ix in range(len(positive_instr)):
                    _key_ = list(positive_instr.keys())[_fctr_ix]
                    positive_instr[_key_] = positive_instr[_key_] + _pos_instr[_key_]
                for _fctr_ix in range(len(negative_scan_instr)):
                    _key_ = list(negative_scan_instr.keys())[_fctr_ix]
                    negative_scan_instr[_key_] = negative_scan_instr[_key_] + _neg_instr[_key_]

        matches = self.match_f(positive_instr, negative_scan_instr, _n_iters)
        # matches = self._remove_misc_negative_instr(self.black_list, matches, self.strat.runtime_tm)

        if self.strat.debugging.dummy_data:
            matches = self.strat.debugging.dummy_instr
        log.log(hist_data_df, matches)
        return matches

    # @classmethod
    def _time_gates_f(self, _time_gates, ix):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        gate = _time_gates[ix].time()
        if self.strat.debugging.dummy_time:
            _now = self.strat.lt._manipulated_time(datetime.datetime.now())
        else:
            _now = datetime.datetime.now()
        _now = self.strat.lt.us_tz_op(_now).time()
        while _now < gate:  # _time_gates
            if self.strat.debugging.dummy_time:
                _now = self.strat.lt._manipulated_time(datetime.datetime.now())
            else:
                _now = datetime.datetime.now()
            _now = self.strat.lt.us_tz_op(_now).time()
            self.strat.lt.ib.sleep(1)
            # _visible_counter += 1
            # if _visible_counter % 5 == 0:
            #     print('_visible_counter seconds {} ({} - {})'.format(str(_visible_counter),_now.strftime('%H:%M:%S'),gate.strftime('%H:%M:%S')))
            continue
        log.log()

    @classmethod
    def _relevance_discarding(cls, factors, _n_iters, runtime_tm, _first_iter=False):
        log_start = datetime.datetime.now()
        log = logging_.Logging(runtime_tm, log_start,
                               str(cls.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        selection_dict = OrderedDict()
        for ix, i in enumerate(factors.values()):
            flat = [j for k in i for j in k]
            n = []
            for f in flat:
                n.append([f, flat.count(f)])
            if not _first_iter:
                for cix, c in enumerate(n):
                    if c[1] < _n_iters:
                        del n[cix]
            fittest = [r[0] for r in n]
            selection_dict[ix] = fittest
        log.log()
        return selection_dict

    def _check_tradeability_of_instr(self, traded_instr_this_strat):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        removables = []
        # for wnr_ in self.__winners:
        instrs = copy.copy(traded_instr_this_strat)
        for wnr_ in traded_instr_this_strat:
            if self.is_used_by_another_parallel_strat(wnr_):
                removables.append(wnr_)
        if len(removables) > 0:
            for rem_ in removables:
                next_in_line = self.__winners.pop(0)
                instrs.append(next_in_line)
                self.reshuffle_winners(self.strat.parallel_traded_instr_per_strat, next_in_line, remove=rem_)
                _ix = instrs.index(rem_)
                del instrs[_ix]
        log.log(removables)
        return instrs

    def reshuffle_winners(self, parallel_traded_instr_per_strat, next_in_line, remove=None):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())

        if remove is None:
            # self.__traded_instr = []
            for i in range(parallel_traded_instr_per_strat):
                # if len(self.__winners) == 0 and len(self.__traded_instr) > 0:
                if len(self.__winners) == 0 and len(self.strat.lt.traded_instr) > 0:
                    return
                # elif len(self.__winners) == 0 and len(self.__traded_instr) == 0:
                elif len(self.__winners) == 0 and len(self.strat.lt.traded_instr) == 0:
                    raise exceptions_.NoMoreWinnersInLineError

                # self.__traded_instr.append(next_in_line)
                self.strat.lt.traded_instr.append(next_in_line)
                self.strat.add_to_manager(self.strat.strat_name, 'traded_instr', self.strat.lt.traded_instr)
                self.strat.add_to_manager(self.strat.strat_name, '__winners', self.__winners)
                self.strat.lt.heartbeat_q.put([self.strat.strat_name, '__winners', self.__winners])
        else:
            # ix = self.__traded_instr.index(remove)
            try:
                ix = self.strat.lt.traded_instr.index(remove)
                del self.strat.lt.traded_instr[ix]
                # self.strat.add_to_manager(self.strat.strat_name, 'traded_instr', self.strat.lt.traded_instr)
            except ValueError:
                pass
            if len(self.__winners) == 0 and len(self.strat.lt.traded_instr) > 0:
            # if len(self.__winners) == 0 and len(self.__traded_instr) > 0:
                return
            elif len(self.__winners) == 0 and len(self.strat.lt.traded_instr) == 0:
            # elif len(self.__winners) == 0 and len(self.__traded_instr) == 0:
                raise exceptions_.NoMoreWinnersInLineError
            self.strat.lt.traded_instr.append(next_in_line)
            # self.__traded_instr.append(next_in_line)
            # self.strat.add_to_manager(self.strat.strat_name, 'traded_instr', self.strat.lt.traded_instr)
            # self.strat.add_to_manager(self.strat.strat_name, '__winners', self.__winners)
            self.strat.lt.heartbeat_q.put([self.strat.strat_name, '__winners', self.__winners])

    def match_f(self, positive_instr, negative_instr, _n_iters, _first_iter=False):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        positive_list = self._relevance_discarding(positive_instr, _n_iters, self.strat.runtime_tm, _first_iter)
        # must_appear_at_least = len2 if _first_iter else 2 * _n_iters
        must_appear_at_least = len(self.positive_factors) if _first_iter else len(self.positive_factors) * _n_iters
        self.cons_disp.print_warning('not sure if must_appear_at_least is correct')
        concat_ = []
        for i_ix, i in enumerate(positive_instr.keys()):
            concat_.append(positive_list[i_ix])
        counts_ = []
        flat = [j for k in concat_ for j in k]
        for f in flat:
            counts_.append([f, flat.count(f)])
        positive_matches = []
        for c_ix, c in enumerate(list(counts_)):
            if c[1] >= must_appear_at_least:
                positive_matches.append(c[0])
        positive_matches = list(set(positive_matches))
        if len(negative_instr) > 0:
            negative_list = self._relevance_discarding(negative_instr, _n_iters, self.strat.runtime_tm, _first_iter)
            # sort out a certain number of overnight stars
            matches = []
            negative_list_flat = [j for i in negative_list.values() for j in i]
            _cnt_remove = 0
            _step_through = int(1 / (1 - self.strat.rm.fraction_sorting_out_negative_list))
            for j, i in enumerate(list(positive_matches)):
                if i in negative_list_flat:
                    if _cnt_remove < _step_through:
                        _cnt_remove += 1
                    else:
                        _cnt_remove = 0
                        continue
                matches.append(i)
        else:
            matches = positive_matches
        log.log(matches)
        return matches

    def _reduce_fraction_sorting_out_negative_list(self):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start,
                               str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        self.strat.rm.fraction_sorting_out_negative_list -= .1
        if self.strat.rm.fraction_sorting_out_negative_list < .0:
            self.strat.rm.fraction_sorting_out_negative_list = .0
        log.log(self.strat.rm.fraction_sorting_out_negative_list)

    @classmethod
    def _remove_misc_negative_instr(cls, black_list, matches, runtime_tm):
        log_start = datetime.datetime.now()
        log = logging_.Logging(runtime_tm, log_start,
                               str(cls.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        selected_matches = []
        for i in matches:
            if i in black_list:
                continue
            selected_matches.append(i)
        log.log()
        return selected_matches

    def __make_trade_decision(self, ticker, order):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        buy_try, sell_try, status = None, None, None
        if order == 'BUY':
            side = 1  # bid
        elif order == 'SELL':
            side = 0  # ask
        else:
            raise Exception('must be either BUY or SELL')

        # if DEBUGGING:
        if self.strat.debugging.dummy_data:
            # available_bids, available_asks = 5, 6
            available_bids = self.strat.lt._ticker_len_n_type_check(ticker.domBids)
            available_asks = self.strat.lt._ticker_len_n_type_check(ticker.domAsks)
        else:
            available_bids = self.strat.lt._ticker_len_n_type_check(ticker.domBids)
            available_asks = self.strat.lt._ticker_len_n_type_check(ticker.domAsks)

        buy_conditions = self.signals.__buy_conditions(ticker)
        if order == 'BUY' and not buy_conditions:
            status = -1
        elif order == 'BUY' and buy_conditions:
            buy_try = 0
            while True:
                price, offer_size = self.signals.price_size_select(ticker, buy_try, side)
                if price > self.strat.max_price_instr_usd:
                    status = 1
                    break
                price, offer_size = self.signals.price_size_select(ticker, buy_try, side)
                cap_ = ''
                _cap_cnt = 0
                _max_cap_cnt = 10
                while _cap_cnt < _max_cap_cnt:
                    cap_ = self.strat.lt.cash.available_funds(self.strat.lt.report.pnl(), self.strat.lt.account_curr)
                    if cap_ != 'value cannot be determined':
                        break
                    self.strat.lt.ib.sleep(0.5)
                    _cap_cnt += 1
                    if _cap_cnt == _max_cap_cnt:
                        raise exceptions_.ReportExtractionError
                self.strat.add_to_manager(self.strat.strat_name, 'cap_usd', cap_)
                # budget = self.scanner_based.rm.get_budget(len(self.__traded_instr), cap_, self.scanner_based.runtime_tm)
                budget = self.strat.rm.get_budget(len(self.strat.lt.traded_instr), cap_, self.strat.runtime_tm)
                # self.lt.add_to_monitor('budget_per_instr RiskManagement.get_budget', budget)
                offer = price * offer_size
                size = int(budget / price)
                # if budget < price:
                #     buy_try += 1
                # else:
                #     buy_order_filled_status = self.lt.buy(ticker, buy_try, size, ORDER_TYPE)
                #     if buy_order_filled_status == 0:
                #         status = 0
                #         break
                #     else:
                #         status = -1
                buy_order_filled_status = self.strat.lt.buy(ticker, buy_try, size, self.order_type)
                if buy_order_filled_status == 0:
                    status = 0
                    break
                else:
                    status = -1
                if buy_try == self.strat.n_willingness_to_move_up_price - 1 or buy_try == available_bids:
                    status = -1
                    break
        elif order == 'SELL' and not self.signals.__sell_conditions(ticker):
            status = -1
        elif order == 'SELL' \
                and (self.signals.__sell_conditions(ticker) or self.signals.stop_loss_f(ticker)):
            sell_try = 0
            size_ix = 3
            symbol_ix = 0
            while True:
                price, offer_size = self.signals.price_size_select(ticker, sell_try, side)
                # offer = price * size
                # held_position = self.lt.held_instruments[str(reqId)]['size'] * price
                row_num = [i[symbol_ix] for i in self.strat.lt.portfolio].index(ticker.contract.symbol)
                held_size =  self.strat.lt.portfolio[row_num][size_ix]
                if offer_size < held_size:
                    sell_try += 1
                else:
                    status = 0
                    self.strat.lt.sell(ticker, sell_try, self.order_type)
                    break
                if sell_try == self.strat.n_willingness_to_move_up_price - 1 or sell_try == available_asks:
                    status = -1
                    break
        # statuses:
        # -1 = next try/price up
        # 0 = ok = buy/sell
        # 1 = other conditions not met = abandon
        log.log(buy_try
                ,sell_try
                ,status)

    def collect_hist_ticks(self, ticker, unix_ts):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
        cnt = 0
        log_msg1 = ""
        while cnt < self.strat.iteration_timeout_secs:
            # if DEBUGGING:
            if self.strat.debugging.dummy_data:
                # available_bids, available_asks = 5, 6
                available_bids = self.strat.lt._ticker_len_n_type_check(ticker.domBids)
                available_asks = self.strat.lt._ticker_len_n_type_check(ticker.domAsks)
            else:
                available_bids = self.strat.lt._ticker_len_n_type_check(ticker.domBids)
                available_asks = self.strat.lt._ticker_len_n_type_check(ticker.domAsks)
            if available_asks > 0 and available_bids > 0:
                break
            else:
                log_msg1 = 'no bids or asks available for contract, iterating through {}/ITERATION_TIMEOUT_SECS = {}'\
                    .format(str(cnt), str(self.strat.iteration_timeout_secs))
                log.log(log_msg1)
                self.strat.add_to_manager(self.strat.strat_name, *log.monitor())
            self.strat.lt.ib.sleep(1)
            cnt += 1
        else:
            log_msg1 = 'ending iteration - no bids or asks available for contract'
            self.cons_disp.print_warning(log_msg1)
            status = 1
            log.log(log_msg1)
            return status

        for interm_side in ['ask', 'bid']:
            symbol = ticker.contract.symbol
            if interm_side == 'ask':
                side = 0
                items = ticker.domAsks
            else:
                side = 1
                items = ticker.domBids
            _n_ranks = self.strat.n_willingness_to_move_up_price \
                if self.strat.n_willingness_to_move_up_price >= len(items) \
                else len(items)
            for rank in range(_n_ranks):
                if self.strat.debugging.dummy_data:
                    # price, size = float(random.randint(10,100)), random.randint(100,10000)
                    price, size = items[rank].price, items[rank].size
                else:
                    try:
                        price, size = items[rank].price, items[rank].size
                    except IndexError:
                        try:
                            price, size = items.price, items.size
                        except AttributeError:
                            continue
                df = pd.DataFrame([[symbol, unix_ts, side, rank, price, size]],
                                  columns=['symbol', 'unix_ts', 'side', 'rank', 'price', 'size'])
                self.__hist_data_winners_df = pd.concat([self.__hist_data_winners_df, df])
                _row_major = 0
                # self.lt.add_to_monitor('n __hist_data_winners_df', self.__hist_data_winners_df.shape[_row_major])
                # print(self.hist_data_winners_df)
        status = 0
        log.log(log_msg1
            ,price
            ,size
            ,side)
        return status

    def receive_(self, _type_):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        scan_data = []
        self.ss.scanCode = _type_
        scan = self.strat.lt.ib.reqScannerData(self.ss)
        if len(scan) == 0:
            print('scanner did not return anything')
            raise exceptions_.ScannerReturnsNothingError
        rank = 0
        while True:
            try:
                scan_data.append([scan[rank].contractDetails.contract.symbol])
                rank += 1
            except IndexError:
                break
        log.log(_type_)
        return scan_data

    def initial_scan_to_sort(self, _longer_list):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        positive_instr = OrderedDict()
        negative_instr = OrderedDict()
        _scan_param_ix = 0
        for factor_ix in range(_longer_list):
            try:
                _key_ = list(self.positive_factors.keys())[factor_ix]
                positive_instr[_key_] = self.receive_(self.positive_factors[_key_][_scan_param_ix])
            except IndexError:
                pass
            except exceptions_.ScannerReturnsNothingError:
                del self.positive_factors[factor_ix]
            try:
                _factor_val_ix, _factor_type_ix = 0, 1
                if isinstance(self.negative_factors, tuple):
                    for _nf in self.negative_factors:
                        if list(_nf.values())[0][_factor_type_ix] == 'scanner':
                            _neg_fact = _nf
                            break
                else:
                    _neg_fact = self.negative_factors[0]
                _key_ = list(_neg_fact.keys())[factor_ix]
                negative_instr[_key_] = self.receive_(_neg_fact[_key_][_scan_param_ix])
            except IndexError:
                pass
            except exceptions_.ScannerReturnsNothingError:
                del self.negative_factors[factor_ix]
        log.log(_longer_list)
        return positive_instr, negative_instr

    def scan_(self, _longer_list):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.strat.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        positive_instr = OrderedDict()
        negative_instr = OrderedDict()
        _scan_param_ix = 0
        for factor_ix in range(_longer_list):
            try:
                _key_ = list(self.positive_factors.keys())[factor_ix]
                positive_instr[_key_] = self.receive_(self.positive_factors[_key_][_scan_param_ix])
            except IndexError:
                pass
            except exceptions_.ScannerReturnsNothingError:
                negative_instr[_key_] = []
            try:
                _key_ = list(self.negative_factors.keys())[factor_ix]
                negative_instr[_key_] = self.receive_(self.negative_factors[_key_][_scan_param_ix])
            except IndexError:
                pass
            except exceptions_.ScannerReturnsNothingError:
                negative_instr[_key_] = []
        log.log(_longer_list)
        return positive_instr, negative_instr
