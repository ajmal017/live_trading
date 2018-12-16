import datetime
import sys

from live_trading.logging_ import logging_
from live_trading.utils import helpers, exceptions_

CAP_RETENTION_IF_TOO_FEW_INSTR = .5
TOO_FEW_INSTR_TRADED = 1

class RiskManagement:
    def __init__(self, strategy):
        self.strategy = strategy
        self.fraction_sorting_out_negative_list = .2

    @staticmethod
    def get_budget(_n_winners, cap_ , runtime_tm):
        log_start = datetime.datetime.now()
        log = logging_.Logging(runtime_tm, log_start, str(' '+ ',' + sys._getframe().f_code.co_name))
        if _n_winners > TOO_FEW_INSTR_TRADED:
            budget = cap_ / _n_winners
        else:
            try:
                budget = (cap_ / _n_winners) * (1 - CAP_RETENTION_IF_TOO_FEW_INSTR)
            except Exception as e:
                if _n_winners == 0:
                    raise exceptions_.WinnersZero()
                else:
                    raise e
        log.log(budget, _n_winners)
        return budget
