import unittest
import multiprocessing
import time

from live_trading.utils.heartbeatmonitor import HeartbeatMonitor


class HeartbeatMonitorTestCase(unittest.TestCase):
    # queries
    def test_get_q_qEmpty_doesntRaise(self):
        # arrange
        expected_d_ = multiprocessing.Manager().dict()
        expected_q_ = multiprocessing.Queue()
        expected_tm2_run_in_parallel_secs = 2
        
        # act
        hbm = HeartbeatMonitor
        hbm.d_ = expected_d_
        hbm.q_ = expected_q_
        hbm.get_q(HeartbeatMonitor)
        procs = []
        p = multiprocessing.Process(target=hbm.get_q(HeartbeatMonitor))
        p.start()
        procs.append(p)
        p = multiprocessing.Process(target=self._timer, args=(expected_tm2_run_in_parallel_secs,))
        p.start()
        procs.append(p)
        status = None
        for _ in procs:
            while procs[0].is_alive() and procs[1].is_alive():
                continue
            else:
                if procs[0].is_alive():
                    procs[0].terminate()
                    status = True
                else:
                    status = False

        # assert
        self.assertTrue(status)

    # commands

    # helpers
    @staticmethod
    def _timer(sleeper):
        time.sleep(sleeper)
        return

if __name__ == '__main__':
    unittest.main()
