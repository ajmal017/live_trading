from abc import ABCMeta, abstractmethod

class Signals(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self):
        pass

    # def __init__(self, strategy):
    #     self.strategy = strategy

    def __buy_conditions(self, ticker):
        pass

    def __sell_conditions(self, ticker):
        pass

    def sell_at_eob_f(self):
        pass
