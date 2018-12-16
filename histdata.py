import datetime

from live_trading.utils.gatherdata import GatherData
from live_trading.utils.analyzedata import AnalyzeData
from live_trading.utils.scheduleadgent.scheduleagent import ScheduleAgent

ON_THIS_TZ = datetime.time(15, 31, 0)
OFF_THIS_TZ = datetime.time(15, 41, 0)

"""
SELECT TOP 1000 [unix_ts] 
      ,[dt_ts]
      ,[scanner_name]
      ,[symbol]
      ,[symbol_rank]
      ,[bar_szie]
	  select distinct symbol
  FROM [AlgoTrading].[dbo].[hist_scanner]
  --order by [dt_ts] desc

SELECT *
  FROM [AlgoTrading].[dbo].hist_ohlcv
  order by dt_ts desc

    select distinct symbol
  FROM [AlgoTrading].[dbo].hist_ohlcv
  where unix_ts = 1541169600  
"""

def main():
    gt = GatherData()
    # sc_ag = ScheduleAgent() sc_ag.scanner_1st_hist_data_2nd,
    gt.run_scanner(ON_THIS_TZ, OFF_THIS_TZ, 'db')
    # gt.run_scanner(ON_THIS_TZ, OFF_THIS_TZ, 'db')
    # ad = AnalyzeData()
    # ad.run_()

if __name__ == "__main__":
    main()
