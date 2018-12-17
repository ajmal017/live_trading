# live_trading

## Introduction
The live_trading python library is an algo trading interface for broker APIs and was developed with the intention to cater for trading with market-depth (level II) data granularity. The project started with a minimum viable product (MVP) design and neglects therefore currently major mandatory compenents of a regular trading interface. It focuses on alpha, i.e. instrument selection. In its nature, the interface is developed with the Interactive Brokers (IB) API, where the Trader Works Station (TWS) locally acts as the server and the API as the client. The development took place in a Danish account trading on US markets and is thus developed in DKK currency with USD conversion. The market data provier is NASDAQ TotalView. The library is not fully functional and has issues with resilience (hence, a project Resilience was opened). Apart from that, most notably, it lacks proper sell functions at EOD and for stop loss functionality. In additio, it is not fully reactive, i.e. the IBAPI is asynronous in its nature, its python API is not completely reactive and the package on top of the API acts pseudo-synchronously (ib_insync, using asyncio).

## Installation
The package can only run with a IB running as a service (e.g. IB TWS or Gateway) with a deposited account. Read more: https://interactivebrokers.github.io/tws-api/initial_setup.html

## Dependencies/versions
* IB TWS: Build 972
* IBAPI: 9.744
* Python: 3.6
* ib_insync: v0.9
* Pandas: 0.23.4
* MSSQL: 2012

## Versioning
Public beta 0.1

## License
TBD

## Disclaimer/Warning
live_trading does not give investmnet advice. For safety reasons due to the beta version, use paper trading.
