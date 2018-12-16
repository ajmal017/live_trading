import unittest
import datetime
import multiprocessing

from live_trading.live_trading import LiveTrading
from live_trading.utils.helpers import MethodManager_
from live_trading.strategies.strategies import DEBUGGING, RUNTIME_TM


class LiveTradingTestCase(unittest.TestCase):
    # queries
    def test_us_tz_op_dtObj_isNotDt(self):
        # arrange
        expected_strat_name = str('strat_name')
        expected_client_id = int(1)
        expected_runtime_tm = RUNTIME_TM
        expected_debugging = DEBUGGING
        expected_manager_ = multiprocessing.Manager().dict()
        expected_heartbeat_q = multiprocessing.Queue()
        expected_traded_instr = multiprocessing.Manager().list()

        lt = LiveTrading(expected_strat_name,
                         expected_client_id,
                         expected_runtime_tm,
                         expected_debugging,
                         expected_manager_,
                         expected_heartbeat_q,
                         expected_traded_instr)
        
        # act
        expected_dt_obj = str('hh.mm.ss')
        
        # assert
        with self.assertRaises(TypeError): lt.us_tz_op(expected_dt_obj)

    def test_us_tz_op_WrongTimeZone_Raise(self):
        # arrange
        expected_strat_name = str('strat_name')
        expected_client_id = int(1)
        expected_runtime_tm = RUNTIME_TM
        expected_debugging = DEBUGGING
        expected_manager_ = multiprocessing.Manager().dict()
        expected_heartbeat_q = multiprocessing.Queue()
        expected_traded_instr = multiprocessing.Manager().list()

        lt = LiveTrading(expected_strat_name,
                         expected_client_id,
                         expected_runtime_tm,
                         expected_debugging,
                         expected_manager_,
                         expected_heartbeat_q,
                         expected_traded_instr)

        # act
        # TODO: DEV arrange change of contemporary timezone instead

        # assert

    def test_us_tz_op_WrongTimeZone_Raise(self):
        # arrange

        # act

        # assert

    # commands


if __name__ == '__main__':
    unittest.main()
