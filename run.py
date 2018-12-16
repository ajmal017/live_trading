import datetime, time
from collections import OrderedDict
from multiprocessing import Process, Manager, Queue

from live_trading.strategies.scannerbased.scannerbased import ScannerBased
from live_trading.strategies.scannerbased.instrumentselection.scanners1 import Scanners_1
from live_trading.strategies.scannerbased.instrumentselection.scanners2 import  Scanners_2
from live_trading.strategies.scannerbased.signals.simplemovingaverage import SimpleMovingAverage
from live_trading.utils.heartbeatmonitor import HeartbeatMonitor
from live_trading.utils import helpers
from live_trading.logging_ import logging_

def main():
    universe = 'NSDQ TotalView'
    trade_rate = OrderedDict({'trade_rate': ['INSERT YOUR SCANNERS HERE', 'scanner']})
    perc_chg = OrderedDict({'chg': ['INSERT YOUR SCANNERS HERE', 'scanner']})
    overnight = OrderedDict({'chg_overnight': ['INSERT YOUR SCANNERS HERE', 'scanner']})
    mkt_cap = OrderedDict({'mkt_cap': ['100M', 'finRatiosMarketCap']})
    strats = {'market_open_trade_rate_sma_30_15':
                  [ScannerBased, Scanners_1, 10, 'MKT', ('09:30:15', '09:32:00', trade_rate, (overnight, mkt_cap)), SimpleMovingAverage, (30, 15)],
              'market_open_perc_chg_sma_12_8':
                  [ScannerBased, Scanners_1, 10,'MKT',('09:30:15', '09:32:00', perc_chg, (overnight, mkt_cap)), SimpleMovingAverage, (12, 8)]
              }

    traded_instr = Manager().list()
    heartbeat_q = Queue()
    manager_ = Manager().dict()
    procs = []
    p = Process(target=HeartbeatMonitor, args=(manager_, heartbeat_q, strats, traded_instr))
    p.start()
    procs.append(p)

    val_tup_ix = 1
    for client_id, k_v in enumerate(strats.items()):
        strat_name = k_v[0]
        # manager_ = Manager().dict()
        instr_select = k_v[val_tup_ix][1]
        bar_size_secs = k_v[val_tup_ix][2]
        order_type = k_v[val_tup_ix][3]
        # rule_set = tuple([k_v[val_tup_ix][i + 1] for i in range(len(k_v[val_tup_ix]) - 1)])
        instr_select_rules = k_v[val_tup_ix][4]
        signals = k_v[val_tup_ix][5]
        signal_rules = k_v[val_tup_ix][6]
        p = Process(target=k_v[val_tup_ix][0], args=(strat_name, len(strats), client_id, universe, traded_instr,
                                                     heartbeat_q, manager_, bar_size_secs, order_type, instr_select,
                                                     instr_select_rules, signals, signal_rules))
        p.start()
        procs.append(p)

    strat_proc_ix = 0
    monitor_proc_ix = 1
    for p in procs:
        if p.is_alive() and not procs[strat_proc_ix].is_alive():
            p.terminate()
            try:
                raise Exception('both processes terminated')
            except Exception as e:
                print(e)
                break
        if not procs[monitor_proc_ix].is_alive():
            print('monitor failed but continue anyways')
            pass
        else:
            p.join()

if __name__ == "__main__":
    # rk_logging.Logging().reader("1539042136") #run with debugger
    # rk_logging.Logging().export_csv("1536102988")
    # logging_.Logging(datetime.datetime.now(),datetime.datetime.now(),'').folder_concat_n_export_csv("1539042136")
    main()
    # conn_test()

