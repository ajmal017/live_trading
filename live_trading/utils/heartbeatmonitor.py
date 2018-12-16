import time
import datetime
from collections import OrderedDict
import pandas as pd

from .consoledisplay import ConsoleDisplay

HEARTBEAT_SECS = 6
RUNTIME_TM_HEARTBEAT = datetime.datetime.now()

class Clear(object):
    def __repr__(self):
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        return ''

class HeartbeatMonitor:
    def __init__(self, d_, q_, strats, traded_instr):
        self.d_ = d_
        self.q_ = q_
        self.strats = strats
        self.traded_instr = traded_instr
        self.monitor_lines = ['curr_meth',
            '__winners',
            '__traded_instr',
            #'portfolio',
            'cnt_trades_per_instr_per_day',
            # 'portfolio_instr': self.strat.lt.portfolio_instr,
            # 'blank_line1': '',
            #'cap_usd',
            # 'budget_per_instr RiskManagement.get_budget': None,
            # 'blank_line2': '',
            'continuous_err_cnt',
            'n loops update_trade_flow',
            'n False buy_conditions' ,
            'n False sell_conditions']

        self.heartbeat_secs = HEARTBEAT_SECS
        self.cons_disp = ConsoleDisplay()
        self.clr = Clear()
        self.monitor_from_q()
        # self.monitor_f()

    def get_q(self):
        msgs = []
        while not self.q_.empty():
            # msgs.append(self.q_.get(True))
            msgs.append(self.q_.get(False))
        unique_msgs = []
        previous_val1 = ''
        previous_val2 = ''
        for i in msgs:
            if i[0] == previous_val1 and i[1] == previous_val2:
                continue
            previous_val1 = i[0]
            previous_val2 = i[1]
            unique_msgs.append(i)
        return unique_msgs

    def monitor_from_q(self):
        strat_ix = 0
        line_ix = 1
        val_ix = 2
        _cnt = 0
        df = None
        first_df = True
        while True:
            msgs = self.get_q()
            print('\n', 'heartbeat monitor ({} secs):'.format(self.heartbeat_secs))
            delta_ = datetime.datetime.now() - RUNTIME_TM_HEARTBEAT
            print('    ', 'total time elapsed', ':', delta_)
            for s_ix, strat in enumerate(self.strats):
                col = []
                for msg in msgs:
                    if msg[strat_ix] == strat:
                        for line in self.monitor_lines:
                            if msg[line_ix] == line:
                                col.append([msg[line_ix], str(msg[val_ix])])
                                if first_df:
                                    df = pd.DataFrame(col, columns=['line', '{}'.format(msg[strat_ix])])#.set_index(['line'])
                                    first_df = False
                                    col = []
                                    break
                                else:
                                    new_df = pd.DataFrame(col, columns=['line', '{}'.format(msg[strat_ix])])#.set_index(['line'])
                                    # df = df.join(new_df) #pd.join([df, new_df])
                                    df = df.merge(new_df, how='outer') #on='line',
                                    #  df = df.merge(new_df, on='line', how='o
                                    col = []
                                    break
                    #         else:
                    #             continue
                    # else:
                    #     continue
            print('    ', 'traded_instr', self.traded_instr)
            pd.set_option('display.width', self.cons_disp.pd_width)
            pd.set_option('display.column_space', self.cons_disp.pd_column_space)
            pd.set_option('display.max_rows', self.cons_disp.pd_max_rows)
            pd.set_option('display.max_columns', self.cons_disp.pd_max_columns)
            print('    ', 'strats detailed status', '\n', '   ', df)
            # pd.reset_option()
            first_df = True
            _cnt += 1
            time.sleep(self.heartbeat_secs)

    def monitor_f(self):
        _cnt = 0
        n_past_meths = 5
        while True:
            # if _cnt > 0:
            #     self.clr
            print('\n', 'heartbeat monitor ({} secs):'.format(self.heartbeat_secs))
            delta_ = datetime.datetime.now() - RUNTIME_TM_HEARTBEAT
            print('    ', 'total time elapsed', ':', delta_)
            for k in self.d_.keys():
                try:
                    if not isinstance(self.d_[k], time) and not isinstance(self.d_[k], datetime):
                        _datetime_time_check = True
                    else:
                        _datetime_time_check = False
                except:
                    _datetime_time_check = True

                _bl = 'blank_line'
                if k[0:len(_bl)] == _bl:
                    print('')

                elif k == 'curr_meth':
                    if len(self.d_[k]) > n_past_meths:
                        try:
                            # self.d_[k].pop()
                            self.d_[k] = self.d_[k][0:n_past_meths]
                        except:
                            pass
                    print('    ', k, self.d_[k])

                elif self.d_[k] is None:
                    print('    ', k, '')

                elif isinstance(self.d_[k], str) \
                        or isinstance(self.d_[k], int) \
                        or isinstance(self.d_[k], float) \
                        or _datetime_time_check:
                    print('    ', k, self.d_[k])

                elif len(self.d_[k]) > 1:
                    if isinstance(self.d_[k], dict) or isinstance(self.d_[k], OrderedDict):
                        _li = []
                        for j in self.d_[k]:
                            _li.append([j, self.d_[k][j]])
                    else:
                        _li = [j for j in self.d_[k]]
                    print('    ', k, _li)
                # else:
                #     print('    ', k, ':', self.d_[k])
            print('') # blank line for block end
            _cnt += 1
            time.sleep(self.heartbeat_secs)
