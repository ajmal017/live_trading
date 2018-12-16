import datetime
import time
import traceback
import sys
import os

from ..logging_ import logging_

class NoMoreWinnersInLineError(Exception):
    pass

class TooFewContractsWhileDeterminingError(Exception):
    pass

class ScannerReturnsNothingError(Exception):
    pass

class MaxTradesPerDayError(Exception):
    pass

class SellAtEOBWarning(Exception):
    pass

class ReportExtractionError(Exception):
    pass

class TooManyStratsError(Exception):
    pass

class IbPacingError(Exception):
    pass

class TooMuchMktDptStreaming(Exception):
    pass

class WrongTimeZone(Exception):
    pass

class WinnersZero(Exception):
    pass

class CurrNotInExchRateDict(Exception):
    pass

class ExceptionHandling:
    def __init__(self, runtime_tm, continuous_err_max_for_sleeping, sleep_time_if_error):
        self.runtime_tm = runtime_tm
        self.continuous_err_max_for_sleeping = continuous_err_max_for_sleeping
        self.sleep_time_if_error = sleep_time_if_error
        self.path = str(os.path.dirname(os.path.realpath(__file__))) + '\\..\\errorlog\\'
        self.continuous_err_cnt = 0

    def handle_(self, e, raise_error=False):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))
        # self.lt.add_to_monitor(*log.monitor())
        documentation = []
        documentation_str = ''
        file_name = int(time.mktime(self.runtime_tm.timetuple()))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        documentation.append(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        documentation_str += repr(traceback.format_exception(exc_type, exc_value, exc_traceback)) + '\n\n\n'

        with open(self.path + str(file_name), 'a') as f:
            # f.write(str(documentation))#.encode('utf-8')
            f.write(str(documentation_str))#.encode('utf-8'))

        if isinstance(e, TooFewContractsWhileDeterminingError):
            print('too few contracts to trade, exit')
            raise e
        elif isinstance(e, MaxTradesPerDayError):
            print('max trades per day reached, done')
        elif isinstance(e, SellAtEOBWarning):
            print('get rid of all positions at EOB')
        elif isinstance(e, NoMoreWinnersInLineError):
            print('no more candidates for trading')
            raise e
        elif isinstance(e, TooManyStratsError):
            print('too many strategies per day/execution')
            raise e
        else:
            if raise_error:
                raise e
        print('error logged: ', str(e))
        log.log(str(e))
        #self.lt.add_to_monitor(*log.monitor())
        self.continuous_err_cnt += 1

    def continuous_err_exceeded(self):
        if self.continuous_err_cnt > self.continuous_err_max_for_sleeping:
            print('sleeping {}'.format(str(self.sleep_time_if_error)))
            return  True
        else:
            return  False

    @staticmethod
    def on_ib_error(reqId, errorCode, errorString, errorSomething):
        """
        https://groups.io/g/insync/topic/how_to_capture_error_trapped/7718294?p=,,,20,0,0,0::recentpostdate%2Fsticky,,,20,1,80,7718294
        """
        max_n_mkt_depth_reqs = 309  # ERROR:ib_insync.wrapper:Error 309, reqId 39: Max number (3) of market depth requests has been reached, contract: Stock(symbol='PETZ', exchange='ISLAND', currency='USD')
        if errorCode == max_n_mkt_depth_reqs:
            return IbPacingError
        else:
            return None

    # def on_ib_error(self, reqId, errorCode, errorString):
    #     """
    #     https://groups.io/g/insync/topic/how_to_capture_error_trapped/7718294?p=,,,20,0,0,0::recentpostdate%2Fsticky,,,20,1,80,7718294
    #     """
    #     if len(ib_) > 0:
    #         err = ib_.errorEvent
    #         print('str')
    #     max_n_mkt_depth_reqs = 309 # ERROR:ib_insync.wrapper:Error 309, reqId 39: Max number (3) of market depth requests has been reached, contract: Stock(symbol='PETZ', exchange='ISLAND', currency='USD')
    #     if errorCode == max_n_mkt_depth_reqs:
    #         raise IbPacingError
    #     else:
    #         pass



# print("*** print_tb:")
# traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
# print("*** print_exception:")
# # exc_type below is ignored on 3.5 and later
# traceback.print_exception(exc_type, exc_value, exc_traceback,
#                           limit=2, file=sys.stdout)
# print("*** print_exc:")
# traceback.print_exc(limit=2, file=sys.stdout)
# print("*** format_exc, first and last line:")
# formatted_lines = traceback.format_exc().splitlines()
# print(formatted_lines[0])
# print(formatted_lines[-1])
# print("*** format_exception:")
# # exc_type below is ignored on 3.5 and later
# print(repr(traceback.format_exception(exc_type, exc_value,
#                                       exc_traceback)))
# print("*** extract_tb:")
# print(repr(traceback.extract_tb(exc_traceback)))
# print("*** format_tb:")
# print(repr(traceback.format_tb(exc_traceback)))
# print("*** tb_lineno:", exc_traceback.tb_lineno)
