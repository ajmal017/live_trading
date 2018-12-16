import unittest
import multiprocessing
from collections import OrderedDict

from live_trading.strategies.strategies import Strategies
from live_trading.strategies.scannerbased.instrumentselection.instrumentselection import InstrSelection
from live_trading.strategies.scannerbased.signals.simplemovingaverage import SimpleMovingAverage
from live_trading.utils import helpers

class StrategiesTestCase(unittest.TestCase):
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
    expected_signals = object #SimpleMovingAverage
    expected_signal_args = (int(1), int(2))

    strat = Strategies(expected_strat_name,
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

    # queries
    # commands
    def test_updateTradeFlow_ticker_returnsFilledLines(self):
        expected_contract = 'GOOG'
        expected_lines = [helpers.Lines_(price=float(0.1), size=int(1)),
                          helpers.Lines_(price=float(0.2), size=int(2))]
        expected_ticker = helpers.Tick_(contract=expected_contract, domBids=expected_lines, domAsks=expected_lines)
        expecteed_order = 'BUY'
        # self.assertNotEquals(len(expected_lines),0)
        self.assertGreaterEqual(len(expected_lines), 1)

if __name__ == '__main__':
    unittest.main()
