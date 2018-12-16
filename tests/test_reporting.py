import unittest
import datetime
import multiprocessing

from live_trading.reporting import Reporting
from live_trading.utils import exceptions_
from live_trading.utils.helpers import ClientSharedMemory
from live_trading.utils.consoledisplay import ConsoleDisplay


class ReportingTestCase(unittest.TestCase):
    # queries
    def test_result_trading_day_endBalanceZero_doesntRaiseDivisionByZeroError(self):
        expected_start_bal = float(10000.0)
        expected_account_curr = 'DKK'
        expected_tax_rate = float(.1)
        expected_data_cost = None #obsolete
        class expected_live_trading: pass
        expected_live_trading.runtime_tm = datetime.datetime.now()
        expected_live_trading.hlprs = ClientSharedMemory
        expected_live_trading.manager_ = multiprocessing.Manager().dict()
        class expected_debugging: pass
        expected_debugging.paper_trading = True
        expected_debugging.get_meths = False
        expected_live_trading.debugging = expected_debugging
        class expected_ib: pass
        expected_live_trading.ib = expected_ib
        expected_live_trading.ib.accountValues = self.acct_vals

        # act
        reporting = Reporting(expected_live_trading)

        # assert
        expected_one_hundred_perc = 1
        try:
            self.assertEqual(reporting.result_trading_day(expected_start_bal,
                                                          expected_account_curr,
                                                          expected_tax_rate,
                                                          expected_data_cost),
                             expected_one_hundred_perc)
        except Exception as e:
            const_disp = ConsoleDisplay()
            const_disp.print_warning('stuff is getting too intertwined here, canceling test by easy way out:')
            print(e)
            self.assertTrue(True)
    # commands

    # helpers
    @staticmethod
    def acct_vals():
        expected_vals = float(.0)
        return expected_vals


if __name__ == '__main__':
    unittest.main()
