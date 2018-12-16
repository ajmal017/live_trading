import unittest
import multiprocessing
from collections import OrderedDict

from live_trading.strategies.scannerbased.scannerbased import ScannerBased
from live_trading.strategies.scannerbased.signals.signals import Signals, Signals
from live_trading.strategies.scannerbased.signals.simplemovingaverage import SimpleMovingAverage
from live_trading.utils.exceptions_ import MaxTradesPerDayError


class ScannerBasedTestCase(unittest.TestCase):
    # queries

    # commands
    def test__init_trade_cnt_tradedInstrEmpty_cntTradesPerInstrPerDayEmptyDict(self):
        # arrange
        expected_strat_name = str('strat_name')
        expected_n_strats = int(1)
        expected_client_id = int(1)
        expected_universe = str('any NSDQ TotalView')
        expected_traded_instr = multiprocessing.Manager().list()
        expected_heartbeat_q = multiprocessing.Queue()
        expected_manager_ = multiprocessing.Manager().dict()
        expected_bar_size_secs = int(2)
        expected_order_type = str('MKT')
        expected_instr_select = object#InstrSelection
        expected_instr_select_args = (str('00:00:00'), str('00:00:01'), OrderedDict(), (OrderedDict(), OrderedDict()))
        expected_signals = SimpleMovingAverage
        expected_signal_args = (int(1), int(2))

        sb = ScannerBased(expected_strat_name,
                           expected_n_strats,
                           expected_client_id,
                           expected_universe,
                           expected_traded_instr,
                           expected_heartbeat_q,
                           expected_manager_,
                           expected_bar_size_secs,
                           expected_order_type,
                           expected_instr_select,
                           expected_instr_select_args,
                           expected_signals,
                           expected_signal_args)
        expected__traded_instr = []

        # TODO: DEV throws unittest error (only in debugger), ResourceWarning: unclosed <socket.socket fd=1536, never gets done

        # act
        sb._init_trade_cnt(expected__traded_instr)

        # assert
        self.assertEquals(len(sb.lt.cnt_trades_per_instr_per_day), 0)
    
    def test__check_if_done_maxTradesReached_RaiseSellAtEOBWarning(self):
        # arrange
        expected_strat_name = str('strat_name')
        expected_n_strats = int(1)
        expected_client_id = int(1)
        expected_universe = str('any NSDQ TotalView')
        expected_traded_instr = multiprocessing.Manager().list()
        expected_heartbeat_q = multiprocessing.Queue()
        expected_manager_ = multiprocessing.Manager().dict()
        expected_bar_size_secs = int(2)
        expected_order_type = str('MKT')
        expected_instr_select = object#InstrSelection
        expected_instr_select_args = (str('00:00:00'), str('00:00:01'), OrderedDict(), (OrderedDict(), OrderedDict()))
        expected_signals = SimpleMovingAverage
        expected_signal_args = (int(1), int(2))

        sb = ScannerBased(expected_strat_name,
                           expected_n_strats,
                           expected_client_id,
                           expected_universe,
                           expected_traded_instr,
                           expected_heartbeat_q,
                           expected_manager_,
                           expected_bar_size_secs,
                           expected_order_type,
                           expected_instr_select,
                           expected_instr_select_args,
                           expected_signals,
                           expected_signal_args)

        # TODO: DEV throws unittest error (only in debugger), ResourceWarning: unclosed <socket.socket fd=1536, never gets done

        EXPECTED_MAX_TRADES_PER_INSTR_PER_DAY = 1
        ScannerBased.MAX_TRADES_PER_INSTR_PER_DAY = EXPECTED_MAX_TRADES_PER_INSTR_PER_DAY
        expected_cnt_trades_per_instr_per_day = {'GOOG': 1}

        # act
        sb.lt.cnt_trades_per_instr_per_day = expected_cnt_trades_per_instr_per_day

        # assert
        with self.assertRaises(MaxTradesPerDayError): sb._check_if_done()

if __name__ == '__main__':
    unittest.main()
