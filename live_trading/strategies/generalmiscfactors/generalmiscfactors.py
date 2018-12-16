from abc import ABCMeta, abstractmethod
from live_trading.utils.helpers import MethodManager_

class GeneralMiscFactors(MethodManager_):
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, live_trading):
        self.lt = live_trading

    black_list = ['QQQ', 'SQQQ', 'TQQQ', 'VXX', 'VIX', 'NVO']

    def _get_blac_list(self):
        return self.black_list
