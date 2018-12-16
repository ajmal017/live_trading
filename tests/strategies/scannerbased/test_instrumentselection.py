import unittest

from live_trading.strategies.scannerbased.instrumentselection.instrumentselection import InstrSelection
from live_trading.strategies.strategies import Strategies
from live_trading.live_trading import LiveTrading

class InstrSelectionTestCase(unittest.TestCase):
    # queries
    def test_is_used_by_another_parallel_strat_instrIsInTradedInstr_returnsTrue(self):
        # arrange
        expected_symbol_ = 'GOOG'
        expected_traded_instr = ['GOOG', 'AAPL']

        # act
        InstrSelection.strat = Strategies
        InstrSelection.strat.lt = LiveTrading
        InstrSelection.strat.lt.traded_instr = expected_traded_instr

        # assert
        self.assertTrue(InstrSelection.is_used_by_another_parallel_strat(InstrSelection, expected_symbol_))

    # commands

if __name__ == '__main__':
    unittest.main()
