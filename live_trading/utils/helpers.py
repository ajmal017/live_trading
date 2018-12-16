from collections import OrderedDict

class Helpers: pass

class ClientSharedMemory:
    def init_manager(self, *args, **kwargs):
        # cap_usd = None
        for k, v in kwargs.items():
            if k == 'strats':
                strats = v
        d_ = OrderedDict({ 'n strategies': len(strats),
               'curr_meth': OrderedDict({}),
               '__winners': OrderedDict({}),
               '__traded_instr': OrderedDict({}),
               'portfolio': [], #self.strat.lt.portfolio
               'cnt_trades_per_instr_per_day': OrderedDict({}),#self.strat.lt.cnt_trades_per_instr_per_day
               #'portfolio_instr': self.strat.lt.portfolio_instr,
               # 'blank_line1': '',
               'cap_usd': 0.0,
               #'budget_per_instr RiskManagement.get_budget': None,
               # 'blank_line2': '',
               'continuous_err_cnt': OrderedDict({k: 0 for k in strats}),
               'n loops update_trade_flow': OrderedDict({k: 0 for k in strats}),
               'n False buy_conditions': OrderedDict({k: 0 for k in strats}),
               'n False sell_conditions': OrderedDict({k: 0 for k in strats}),
               'active_mkt_data_lines': 0 })#,
               # 'n __hist_data_winners_df': 0,
               #'blank_line3': '')
        return d_

    def add_to_manager(self, strat_name, key_, val_, first_time=False):
        return
        # (
        # if val_ == 'increment_1':
        #     try:
        #         self.lt.manager_[key_][strat_name] = self.lt.manager_[key_][strat_name] + 1
        #     except Exception as e:
        #         print('')
        #         # if len(self.lt.manager_[key_]) == 0:
        #         #     self.lt.manager_[key_] = OrderedDict({strat_name: [val_]})
        #         # else:
        #         #     raise Exception('add_to_manager: something strange')
        # elif key_ == 'curr_meth':
        #     try:
        #         self.lt.manager_[key_][strat_name] = [val_] + self.lt.manager_[key_][strat_name]
        #     # except KeyError:
        #     except Exception as e:
        #         if len(self.lt.manager_[key_]) == 0:
        #             self.lt.manager_[key_] = OrderedDict({strat_name: [val_]})
        #         elif len(self.lt.manager_[key_]) > 0:
        #             self.lt.manager_[key_][strat_name] = [val_]
        #         else:
        #             raise Exception('add_to_manager: something strange')
        # else:
        #     try:
        #         x = self.lt.manager_[key_]
        #         x[strat_name] = val_
        #         self.lt.manager_[key_] = x
        #         self.lt.manager_[key_][strat_name] = val_
        #         print('')
        #         print('')
        #     # except KeyError:
        #     except Exception as e:
        #         if len(self.lt.manager_[key_]) == 0:
        #             self.lt.manager_[key_] = OrderedDict({strat_name: [val_]})
        #             x = self.lt.manager_[key_]
        #         else:
        #             raise Exception('add_to_manager: something strange')
        # )

class MethodManager_:
    def print_meths(self, cls_, obj_dir):
        own_vars = []
        for i in obj_dir:
            if i[0:2] != '__':
                own_vars.append(i)
        meths = []
        for i in own_vars:
            try:
                _ = eval('self.{}.__name__'.format(i))
                meths.append(i)
            except AttributeError as e:
                continue
        print(cls_)
        for i in meths:
            print(' ', i)

class Database:
    def __init__(self):
        import pyodbc
        self.pyodbc = pyodbc
        self.dbsys = 'mssql2012'

    def connect_(self):
        if self.dbsys == 'mssql2012':
            driver = '{SQL Server Native Client 11.0}'
            host = ''
            database = 'AlgoTrading'
            trusted_connection = 'yes'
            conn_string = r'DRIVER={0};SERVER={1};DATABASE={2};Trusted_Connection={3}'.format(driver,
                                                                                              host,
                                                                                              database,
                                                                                              trusted_connection)
            conn = self.pyodbc.connect(conn_string)
            return conn

class Tick_:
    # __slots__ = ['contract','domBids','domAsks']
    def __init__(self, contract, domBids, domAsks):
        self.contract = contract
        self.domBids = domBids
        self.domAsks = domAsks

class Lines_:
    # __slots__ = ['price','size']
    def __init__(self, price, size):
        self.price = price
        self.size= size
