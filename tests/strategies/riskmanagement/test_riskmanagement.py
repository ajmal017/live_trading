import unittest
import datetime

from live_trading.strategies.scannerbased.riskmanagement.riskmanagement import RiskManagement
from live_trading.strategies.strategies import Strategies
from live_trading.utils import exceptions_

class RiskManagementTestCase(unittest.TestCase):
    # queries
    def test_get_budget_nWinnersZero_returnsTrue(self):
        # arrange
        expected__n_winners = int(0)
        expected_cap_ = float(10000.0)
        expected_runtime_tm = datetime.datetime.now()

        # act
        rm = RiskManagement(Strategies)

        # assert
        with self.assertRaises(exceptions_.WinnersZero): rm.get_budget(expected__n_winners, expected_cap_, expected_runtime_tm)
        
    # commands

if __name__ == '__main__':
    unittest.main()
