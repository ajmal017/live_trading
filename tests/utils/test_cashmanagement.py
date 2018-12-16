import unittest

from live_trading.cashmanagement import CashManagement
from live_trading.utils import exceptions_


class CashManagementTestCase(unittest.TestCase):
    # queries
    def test_available_funds_pnlEmpty_raisesKeyError(self):
        # arrange
        class expected_pnl:
            def __iter__(self):
                return self
        # expected_pnl.member = object()
        expected_account_currency = 'USD'
        class expected_debugging: pass
        expected_debugging.paper_trading = True
        expected_debugging.get_meths = False

        # act
        cm = CashManagement(expected_debugging)

        # assert
        with self.assertRaises(KeyError): cm.available_funds(expected_pnl, expected_account_currency)

    def test_dummy_curr_conversion_currNotInExchRateDict_raises(self):
        # arrange
        expected_account_currency = 'TRY'
        expected_cap_account_curr = float(10000.0)
        class expected_debugging: pass
        expected_debugging.paper_trading = True
        expected_debugging.get_meths = False

        # act
        cm = CashManagement(expected_debugging)

        # assert
        with self.assertRaises(exceptions_.CurrNotInExchRateDict): cm.dummy_curr_conversion(expected_account_currency, expected_cap_account_curr)

    # commands


if __name__ == '__main__':
    unittest.main()
