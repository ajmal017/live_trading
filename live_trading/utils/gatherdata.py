import time
import datetime
import numpy as np
import pandas as pd
import os

# from live_trading.live_trading import LiveTrading
from ib_insync import IB, ScannerSubscription, Stock
from .helpers import Database
from .analyzedata import AnalyzeData

BAR_SIZE = 15
SCANNER_SCOPE = ['TOP_TRADE_RATE', 'TOP_OPEN_PERC_GAIN', 'HIGH_OPEN_GAP']


class GatherData:
    def __init__(self):
        self.analyze = AnalyzeData()
        access_type = 'tws'
        client_id = 0
        if access_type == 'gateway':
            __port = 4001
        elif access_type == 'tws':
            __port = 7497
        __host = '127.0.0.1'
        self.ib = IB()
        self.ib.connect(__host, __port, clientId=client_id)
        self.db = Database()
        self.conn = self.db.connect_()

        self.limit = 50

    def load_scanner(self, scanner):
        ss = ScannerSubscription()
        ss.instrument = "STK"  # STOCK.EU
        ss.locationCode = "STK.NASDAQ"  # US.MAJOR
        ss.scanCode = scanner
        scan = self.ib.reqScannerData(ss)
        # ss.cancelScannerSubscription(ss)
        # self.ib.cancelScannerSubscription(ss)
        # arr = np.array(scan)
        return scan

    @classmethod
    def fields_scanner(cls, unix_ts, dt_ts, scanner, data_):
        fields = []
        for line in data_:
            _symbol = line.contractDetails.contract.symbol
            _rank = line.rank
            fields.append([unix_ts, dt_ts, scanner, _symbol, _rank, BAR_SIZE])
        return fields

    @classmethod
    def insert_scanner(cls, unix_ts, dt_ts, scanner, data_, cursor):
        # if isinstance(data_, np.ndarray) or isinstance(data_, np.ndarray):
        if not isinstance(data_, Exception):
            insert_data = cls.fields_scanner(unix_ts, dt_ts, scanner, data_)
            query = "insert into hist_scanner values(?,?,?,?,?,?);".format(insert_data)
            cursor.executemany(query, insert_data)
        else:
            cursor.execute( "insert into hist_scanner values({},{},{},{},{},{});".format(unix_ts,
                                                                                 dt_ts,
                                                                                 scanner,
                                                                                 np.nan,
                                                                                 np.nan,
                                                                                 BAR_SIZE) )

    @classmethod
    def save_scanner(cls, unix_ts, dt_ts, scanner, data_):
        path_ = str(os.path.dirname(os.path.realpath(__file__))) + '\\hist_files\\scanners\\'
        saving_data = cls.fields_scanner(unix_ts, dt_ts, scanner, data_)
        df = pd.DataFrame(saving_data)
        df.to_csv(path_ + str(unix_ts) + '_' + scanner + '.csv', ',', index=False)

    def load_hist_data(self, dt_ts_str, symbol, duration_secs):
        contract = Stock(symbol, 'SMART', 'USD')
        data_ = self.ib.reqHistoricalData(contract,
                                          endDateTime=''.format(dt_ts_str),
                                          durationStr='{} S'.format(duration_secs),
                                          barSizeSetting='{} secs'.format(BAR_SIZE),
                                          whatToShow='ADJUSTED_LAST',
                                          useRTH=True,
                                          formatDate=1)
        # ss.cancelScannerSubscription(ss)
        # self.ib.cancelScannerSubscription(ss)
        # arr = np.array(scan)
        return data_

    @classmethod
    def fields_hist_data(cls, data_, symbol):
        fields = []
        for i in data_:
            unix_ts = time.mktime(i.date.timetuple())
            fields.append([int(unix_ts), i.date, symbol, float(i.open), float(i.high), float(i.low), float(i.close), float(i.volume)])
        return fields

    @classmethod
    def insert_hist_data(cls, data_, symbol, cursor):
        insert_data = cls.fields_hist_data(data_, symbol)
        query = "insert into hist_ohlcv values(?,?,?,?,?,?,?,?);".format(insert_data)
        cursor.executemany(query, insert_data)


    def run_scanner(self, on_this_tz, off_this_tz, save_mode='db'):
        done = False
        while True:
            now = datetime.datetime.now().time()
            while now > on_this_tz and now < off_this_tz:
                # while schedule_agent(on_this_tz, off_this_tz):
                previous_unix_ts = int(time.time())
                previous_dt_ts = datetime.datetime.now()
                with self.conn.cursor() as cursor:
                    try:
                        # if isinstance(self.conn, self.db.Connection):
                        for scanner in SCANNER_SCOPE:
                            data_ = self.load_scanner(scanner)
                            if save_mode == 'db':
                                self.insert_scanner(previous_unix_ts, previous_dt_ts, scanner, data_, cursor)
                                print('requested and inserted {} scanners, bar size is {}'.format(str(len(SCANNER_SCOPE)),
                                                                                                  str(BAR_SIZE)))
                            elif save_mode == 'files':
                                self.save_scanner(previous_unix_ts, previous_dt_ts, scanner, data_)
                                print('requested and saved {} scanners, bar size is {}'.format(str(len(SCANNER_SCOPE)),
                                                                                                  str(BAR_SIZE)))
                    except Exception as e:
                        print('error occured and inserted:', e)
                        self.insert_scanner(previous_unix_ts, previous_dt_ts, np.nan, e, cursor)
                current_unix_ts = int(time.time())
                print('waiting for next bar:', BAR_SIZE)
                while current_unix_ts - previous_unix_ts < BAR_SIZE:
                    current_unix_ts = int(time.time())
                done = True
                now = datetime.datetime.now().time()
            else:
                time.sleep(1)
            if done:
                dt_ts_str, scanners = self.analyze.get_todays_insertions(self.conn)
                matches = self.analyze.query_matches(dt_ts_str, scanners, self.limit, self.conn)
                insertion_li = []

                # dt_ts_str = '20181026 09:40:00'

                for match in matches:
                    try:
                        hist_data = self.load_hist_data(dt_ts_str, match, 10 * 60)
                        insertion_li.append(hist_data)
                        with self.conn.cursor() as cursor:
                            self.insert_hist_data(hist_data, match, cursor)
                    except IndexError:
                        print('stop')
                done = False
