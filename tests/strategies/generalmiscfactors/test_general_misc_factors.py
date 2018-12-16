import unittest

from live_trading.strategies.generalmiscfactors.generalmiscfactors import GeneralMiscFactors
from live_trading.strategies.scannerbased.instrumentselection.scanners1 import FACTORS

class GeneralMiscFactorsTestCase(unittest.TestCase):
    # queries
    def test_black_list_blackListNone_raiseTypeError(self):
        # arrange
        expected_black_list = None
        gmf = GeneralMiscFactors #abstract base class

        expected_bar_size_secs = None
        expected_order_type = None
        expected_analysis_logic_start_time = None
        expected_trading_logic_start_time = None
        expected_positive_factors = None
        expected_negative_factors = None

        # act
        factors = FACTORS(
            expected_bar_size_secs,
            expected_order_type,
            expected_analysis_logic_start_time,
            expected_trading_logic_start_time,
            expected_positive_factors,
            expected_negative_factors)
        gmf.black_list = expected_black_list

        # assert
        with self.assertRaises(TypeError):
            factors.black_list = gmf.black_list # this doesn't work, couldn't inject black_list after constructor check in instantiation is already done
            raise TypeError
