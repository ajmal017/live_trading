import datetime
import sys
from ib_insync import Stock
import xmltodict

from live_trading.logging_ import logging_
from live_trading.utils import helpers
from live_trading.reporting import Reporting
from .generalmiscfactors import GeneralMiscFactors

CAP_RETENTION_IF_TOO_FEW_INSTR = .5
TOO_FEW_INSTR_TRADED = 1

class FundamentalData(GeneralMiscFactors, Reporting):
    def __init__(self, *args):
        super(FundamentalData, self).__init__(*args)

class FinRatios(FundamentalData):
    def __init__(self, *args):
        super(FinRatios, self).__init__(*args)

    def mkt_cap(self, symbol_, threshold_):
        log_start = datetime.datetime.now()
        log = logging_.Logging(self.lt.runtime_tm, log_start, str(self.__class__.__name__ + ',' + sys._getframe().f_code.co_name))

        if isinstance(threshold_, int) or isinstance(threshold_, float):
            raise Exception('invalid value, must be a letter at end')
        if threshold_[-1] == 'M':
            mult_ = 1000000
        elif threshold_[-1] == 'B':
            mult_ = 1000000000
        else:
            mult_ = 1
        threshold_ = int(threshold_[:-1]) * mult_
        self.lt.hlprs.add_to_manager(self.lt.manager_, *log.monitor())

        contract_ = Stock(symbol_, 'ISLAND', 'USD')
        snapshot_xml = self.lt.ib.reqFundamentalData(contract_, 'ReportSnapshot')
        if len(snapshot_xml) > 0:
            snapshot = xmltodict.parse(snapshot_xml)
            fin_stat_xml = self.lt.ib.reqFundamentalData(contract_, 'ReportsFinStatements')
            fin_stat = xmltodict.parse(fin_stat_xml)
            px_ = float(snapshot \
                ['ReportSnapshot']\
                ['Ratios']\
                ['Group']\
                [0]\
                ['Ratio']\
                [0]\
                ['#text'])
            coa_ = fin_stat \
                ['ReportFinancialStatements']\
                ['FinancialStatements']\
                ['COAMap']\
                ['mapItem']
            # periods = fin_stat \
            #     ['ReportFinancialStatements']\
            #     ['FinancialStatements']\
            #     ['AnnualPeriods']\
            #     ['FiscalPeriod']
            line_items_ = fin_stat \
                ['ReportFinancialStatements']\
                ['FinancialStatements']\
                ['AnnualPeriods']\
                ['FiscalPeriod']\
                [0]\
                ['Statement']\
                [1]\
                ['lineItem']
            # [len(periods)-1]\
            for ix_, acc_grp in enumerate(coa_):
                if acc_grp['#text'] == 'Total Common Shares Outstanding':
                    where = coa_[ix_]['@coaItem']
                    precision_ = int(acc_grp['@precision'])
                    if precision_ == 1:
                        zeros = 1000.0
                    elif precision_ == 2:
                        zeros = 1000000.0
                    else:
                        zeros = 1.0
                    for ix2, line_ in enumerate(line_items_):
                        if line_['@coaCode'] == where:
                            shares_outstanding_ = float(line_items_[ix2]['#text']) * zeros
                            break
            mkt_cap = px_ * shares_outstanding_
        else:
            mkt_cap = 0.0
        log.log()
        if mkt_cap  > threshold_:
            return True
        else:
            return False
