from abc import ABCMeta, abstractmethod
from live_trading.utils.helpers import MethodManager_

class InstrSelection(MethodManager_):
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, debugging):
        MethodManager_.__init__(self)

    def is_used_by_another_parallel_strat(self, symbol_):
        if symbol_ in self.strat.lt.traded_instr:
            return True
