from live_trading.utils.helpers import MethodManager_
from live_trading.utils import exceptions_

class CashManagement(MethodManager_):
    def __init__(self, debugging):
        self.debugging = debugging
        if self.debugging.get_meths:
            self.print_meths(str(self.__class__.__name__), dir(self))

    def available_funds(self, pnl, account_curr):
        cap_ = ''
        curr = 'BASE' if self.debugging.paper_trading else account_curr
        # curr = account_curr
        def for_tests_fn(pnl):
            # _li = [i if '__' not in i[0:2] for i in pnl]
            _li = []
            for i in pnl.__dict__:
                if '__' not in str(i)[0:2]:
                    _li.append(i)
            if len(_li) == 0:
                raise KeyError
        # try:
        #     for_tests_fn(pnl)
        # except Exception as e:
        #     raise e
        for_tests_fn(pnl)
        for i in pnl:
            if i.tag == 'NetLiquidationByCurrency' and i.currency == curr:
                cap_account_curr = float(i.value)
                cap_ = self.dummy_curr_conversion(account_curr, cap_account_curr)
                break
        if isinstance(cap_, str):
            cap_ = 'value cannot be determined'
        if self.debugging.paper_trading:
            cap_ /= 100
        return cap_

    @classmethod
    def dummy_curr_conversion(cls, account_curr, cap_account_curr):
        exch_rate_ = {'DKK': 0.16}  # google 5 sep. 2018
        try:
            cap_ = cap_account_curr * exch_rate_[account_curr]
        except KeyError as e:
            raise exceptions_.CurrNotInExchRateDict
        return cap_
