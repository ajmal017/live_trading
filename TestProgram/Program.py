"""
Copyright (C) 2018 Interactive Brokers LLC. All rights reserved. This code is subject to the terms
and conditions of the IB API Non-Commercial License or the IB API Commercial License, as applicable.
"""

import sys
import argparse
import datetime
import collections
import inspect

import logging
import time
import os.path

import random
import sys
import pandas as pd
import numpy as np
import queue
import pickle

from ibapi import wrapper
from ibapi.client import EClient
from ibapi.utils import iswrapper

# types
from ibapi.common import *
from ibapi.order_condition import *
from ibapi.contract import *
from ibapi.order import *
from ibapi.order_state import *
from ibapi.execution import Execution
from ibapi.execution import ExecutionFilter
from ibapi.commission_report import CommissionReport
from ibapi.scanner import ScannerSubscription
from ibapi.ticktype import *

from ibapi.account_summary_tags import *

from ContractSamples import ContractSamples
from OrderSamples import OrderSamples
from AvailableAlgoParams import AvailableAlgoParams
from ScannerSubscriptionSamples import ScannerSubscriptionSamples
from FaAllocationSamples import FaAllocationSamples

from Analysis import Analysis


def SetupLogger():
    if not os.path.exists("log"):
        os.makedirs("log")

    time.strftime("pyibapi.%Y%m%d_%H%M%S.log")

    recfmt = '(%(threadName)s) %(asctime)s.%(msecs)03d %(levelname)s %(filename)s:%(lineno)d %(message)s'

    timefmt = '%y%m%d_%H:%M:%S'

    # logging.basicConfig( level=logging.DEBUG,
    #                    format=recfmt, datefmt=timefmt)
    logging.basicConfig(filename=time.strftime("log/pyibapi.%y%m%d_%H%M%S.log"),
                        filemode="w",
                        level=logging.INFO,
                        format=recfmt, datefmt=timefmt)
    logger = logging.getLogger()
    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    logger.addHandler(console)


def printWhenExecuting(fn):
    def fn2(self):
        print("   doing", fn.__name__)
        fn(self)
        print("   done w/", fn.__name__)

    return fn2

def printinstance(inst:Object):
    attrs = vars(inst)
    print(', '.join("%s: %s" % item for item in attrs.items()))

class Activity(Object):
    def __init__(self, reqMsgId, ansMsgId, ansEndMsgId, reqId):
        self.reqMsdId = reqMsgId
        self.ansMsgId = ansMsgId
        self.ansEndMsgId = ansEndMsgId
        self.reqId = reqId


class RequestMgr(Object):
    def __init__(self):
        # I will keep this simple even if slower for now: only one list of
        # requests finding will be done by linear search
        self.requests = []

    def addReq(self, req):
        self.requests.append(req)

    def receivedMsg(self, msg):
        pass


# ! [socket_declare]
class KumaroPaperClient(EClient):
    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)
        # ! [socket_declare]

        # how many times a method is called to see test coverage
        self.clntMeth2callCount = collections.defaultdict(int)
        self.clntMeth2reqIdIdx = collections.defaultdict(lambda: -1)
        self.reqId2nReq = collections.defaultdict(int)
        self.setupDetectReqId()

        self.current_symbol = ''

    def countReqId(self, methName, fn):
        def countReqId_(*args, **kwargs):
            self.clntMeth2callCount[methName] += 1
            idx = self.clntMeth2reqIdIdx[methName]
            if idx >= 0:
                sign = -1 if 'cancel' in methName else 1
                self.reqId2nReq[sign * args[idx]] += 1
            return fn(*args, **kwargs)

        return countReqId_

    def setupDetectReqId(self):

        methods = inspect.getmembers(EClient, inspect.isfunction)
        for (methName, meth) in methods:
            if methName != "send_msg":
                # don't screw up the nice automated logging in the send_msg()
                self.clntMeth2callCount[methName] = 0
                # logging.debug("meth %s", name)
                sig = inspect.signature(meth)
                for (idx, pnameNparam) in enumerate(sig.parameters.items()):
                    (paramName, param) = pnameNparam
                    if paramName == "reqId":
                        self.clntMeth2reqIdIdx[methName] = idx

                setattr(KumaroPaperClient, methName, self.countReqId(methName, meth))

                # print("KumaroPaperClient.clntMeth2reqIdIdx", self.clntMeth2reqIdIdx)


# ! [ewrapperimpl]
class KumaroPaperWrapper(wrapper.EWrapper):
    # ! [ewrapperimpl]
    def __init__(self):
        wrapper.EWrapper.__init__(self)

        self.wrapMeth2callCount = collections.defaultdict(int)
        self.wrapMeth2reqIdIdx = collections.defaultdict(lambda: -1)
        self.reqId2nAns = collections.defaultdict(int)
        self.setupDetectWrapperReqId()

    # TODO: see how to factor this out !!

    def countWrapReqId(self, methName, fn):
        def countWrapReqId_(*args, **kwargs):
            self.wrapMeth2callCount[methName] += 1
            idx = self.wrapMeth2reqIdIdx[methName]
            if idx >= 0:
                self.reqId2nAns[args[idx]] += 1
            return fn(*args, **kwargs)

        return countWrapReqId_

    def setupDetectWrapperReqId(self):

        methods = inspect.getmembers(wrapper.EWrapper, inspect.isfunction)
        for (methName, meth) in methods:
            self.wrapMeth2callCount[methName] = 0
            # logging.debug("meth %s", name)
            sig = inspect.signature(meth)
            for (idx, pnameNparam) in enumerate(sig.parameters.items()):
                (paramName, param) = pnameNparam
                # we want to count the errors as 'error' not 'answer'
                if 'error' not in methName and paramName == "reqId":
                    self.wrapMeth2reqIdIdx[methName] = idx

            setattr(KumaroPaperWrapper, methName, self.countWrapReqId(methName, meth))

            # print("KumaroPaperClient.wrapMeth2reqIdIdx", self.wrapMeth2reqIdIdx)


# this is here for documentation generation
"""
#! [ereader]
        # You don't need to run this in your code!
        self.reader = reader.EReader(self.conn, self.msg_queue)
        self.reader.start()   # start thread
#! [ereader]
"""

# ! [socket_init]
class KumaroPaperApp(KumaroPaperWrapper, KumaroPaperClient):
    def __init__(self):
        KumaroPaperWrapper.__init__(self)
        KumaroPaperClient.__init__(self, wrapper=self)
        # ! [socket_init]
        self.nKeybInt = 0
        self.started = False
        self.nextValidOrderId = None
        self.permId2ord = {}
        self.reqId2nErr = collections.defaultdict(int)
        self.globalCancelOnly = False
        self.simplePlaceOid = None

    def dumpTestCoverageSituation(self):
        for clntMeth in sorted(self.clntMeth2callCount.keys()):
            logging.debug("ClntMeth: %-30s %6d" % (clntMeth,
                                                   self.clntMeth2callCount[clntMeth]))

        for wrapMeth in sorted(self.wrapMeth2callCount.keys()):
            logging.debug("WrapMeth: %-30s %6d" % (wrapMeth,
                                                   self.wrapMeth2callCount[wrapMeth]))

    def dumpReqAnsErrSituation(self):
        logging.debug("%s\t%s\t%s\t%s" % ("ReqId", "#Req", "#Ans", "#Err"))
        for reqId in sorted(self.reqId2nReq.keys()):
            nReq = self.reqId2nReq.get(reqId, 0)
            nAns = self.reqId2nAns.get(reqId, 0)
            nErr = self.reqId2nErr.get(reqId, 0)
            logging.debug("%d\t%d\t%s\t%d" % (reqId, nReq, nAns, nErr))

    @iswrapper
    # ! [connectack]
    def connectAck(self):
        if self.async:
            self.startApi()

    # ! [connectack]

    @iswrapper
    # ! [nextvalidid]
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)

        logging.debug("setting nextValidOrderId: %d", orderId)
        self.nextValidOrderId = orderId
        # ! [nextvalidid]

        # we can start now
        self.start()
        # self.rec_todays_data()

    def start(self):
        if self.started:
            return

        self.started = True

        if self.globalCancelOnly:
            print("Executing GlobalCancel only")
            self.reqGlobalCancel()
        else:
            print("Executing requests")
            self.marketDepthOperations_req()
            #self.reqGlobalCancel()
            #self.marketDataType_req()
            #self.accountOperations_req()
            # self.tickDataOperations_req()
            # self.marketDepthOperations_req()
            #self.realTimeBars_req()
            #self.historicalDataRequests_req()
            #self.optionsOperations_req()
            # self.marketScanners_req()
            # self.contractOperations_req()
            #self.reutersFundamentals_req()

            # self.reqScannerParameters()

            #self.bulletins_req()
            #self.contractOperations_req()
            #self.contractNewsFeed_req()
            #self.miscelaneous_req()
            #self.linkingOperations()
            #self.financialAdvisorOperations()
            #self.orderOperations_req()
            #self.marketRuleOperations()
            #self.pnlOperations()
            #self.historicalTicksRequests_req()
            #self.tickByTickOperations()
            # self.whatIfOrder_req()

            # self.four_trades_of_high_vol()

            print("Executing requests ... finished")

    # @printWhenExecuting
    # @iswrapper
    @printWhenExecuting
    def four_trades_of_high_vol(self):
        self.hist_data_q = queue.Queue()
        self.market_data_lines = 100
        island = ['PIH', 'TURN', 'FLWS', 'FCCY', 'SRCE', 'VNET', 'TWOU', 'JOBS', 'CAFD', 'EGHT', 'AVHI', 'SHLM', 'AAON',
                  'ABAX',
                  'ABEO', 'ABEOW', 'ABIL', 'ABMD', 'AXAS', 'ACIU', 'ACIA', 'ACTG', 'ACHC', 'ACAD', 'ACST', 'AXDX',
                  'XLRN', 'ANCX',
                  'ARAY', 'ACRX', 'ACET', 'AKAO', 'ACHN', 'ACIW', 'ACRS', 'ACNB', 'ACOR', 'SQZZ', 'ATVI', 'ACTA',
                  'ACXM', 'ADMS',
                  'ADMP', 'ADAP', 'ADUS', 'AEY', 'IOTS', 'ADMA', 'ADBE', 'ADOM', 'ADTN', 'ADRO', 'AAAP', 'ADES', 'AEIS',
                  'AMD',
                  'ADXS', 'ADXSW', 'ADVM', 'AEGN', 'AGLE', 'AEHR', 'AMTX', 'AERI', 'AVAV', 'AEZS', 'AEMD', 'GNMX',
                  'AFMD', 'AGEN',
                  'AGRX', 'AGYS', 'AGIO', 'AGNC', 'AGNCB', 'AGNCP', 'AGFS', 'AGFSW', 'ALRN', 'AIMT', 'AIRT', 'ATSG',
                  'AIRG', 'AMCN',
                  'AKAM', 'AKTX', 'AKCA', 'AKBA', 'AKER', 'AKRX', 'AKTS', 'ALRM', 'ALSK', 'AMRI', 'ALBO', 'ABDC',
                  'ADHD', 'ALDR',
                  'ALDX', 'ALXN', 'ALCO', 'ALGN', 'ALIM', 'ALJJ', 'ALKS', 'ABTX', 'ALGT', 'AIQ', 'AHGP', 'AMMA', 'ARLP',
                  'AHPI',
                  'AMOT', 'ALQA', 'ALLT', 'MDRX', 'AFAM', 'ALNY', 'AOSL', 'GOOG', 'GOOGL', 'SMCP', 'ATEC', 'SWIN',
                  'AABA', 'ALT',
                  'ASPS', 'AIMC', 'AMAG', 'AMRN', 'AMRK', 'AYA', 'AMZN', 'AMBC', 'AMBCW', 'AMBA', 'AMCX', 'DOX', 'AMDA',
                  'AMED',
                  'UHAL', 'ATAX', 'AMOV', 'AAL', 'ACSF', 'AETI', 'AMNB', 'ANAT', 'AOBC', 'APEI', 'ARII', 'AMRB',
                  'AMSWA', 'AMSC',
                  'AMWD', 'CRMT', 'ABCB', 'AMSF', 'ASRV', 'ASRVP', 'ATLO', 'AMGN', 'FOLD', 'AMKR', 'AMPH', 'IBUY',
                  'ASYS', 'AFSI',
                  'AMRS', 'ADI', 'ALOG', 'ANAB', 'AVXL', 'ANCB', 'ANDA', 'ANDAR', 'ANDAU', 'ANDAW', 'ANGI', 'ANGO',
                  'ANIP',
                  'ANIK', 'ANSS', 'ATRS', 'ANTH', 'ABAC', 'APOG', 'APEN', 'AINV', 'APPF', 'APPN', 'AAPL', 'ARCI',
                  'APDN',
                  'APDNW', 'AGTC', 'AMAT', 'AAOI', 'AREX', 'APTI', 'APRI', 'APVO', 'APTO', 'AQMS', 'AQB', 'AQXP',
                  'ARDM',
                  'ARLZ', 'PETX', 'ABUS', 'ARCW', 'ABIO', 'RKDA', 'ARCB', 'ACGL', 'ACGLP', 'APLP', 'ARDX', 'ARNA',
                  'ARCC',
                  'ARGX', 'AGII', 'AGIIL', 'ARGS', 'ARIS', 'ARKR', 'ARTX', 'ARQL', 'ARRY', 'ARRS', 'DWAT', 'AROW',
                  'ARWR',
                  'ARTNA', 'ARTW', 'ASBB', 'ASNA', 'ASND', 'ASCMA', 'APWC', 'ASML', 'AZPN', 'ASMB', 'ASFI', 'ASTE',
                  'ATRO',
                  'ALOT', 'ASTC', 'ASUR', 'ASV', 'ATAI', 'ATRA', 'ATHN', 'ATNX', 'ATHX', 'AAPC', 'AAME', 'ACBI', 'ACFC',
                  'ABY',
                  'ATLC', 'AAWW', 'AFH', 'AFHBL', 'TEAM', 'ATNI', 'ATOM', 'ATOS', 'ATRC', 'ATRI', 'ATTU', 'LIFE',
                  'AUBN', 'BOLD',
                  'AUDC', 'AUPH', 'EARS', 'ABTL', 'ADSK', 'ADP', 'AVDL', 'ATXI', 'AVEO', 'AVXS', 'AVNW', 'AVID', 'AVGR',
                  'AVIR',
                  'CAR', 'AHPA', 'AHPAU', 'AHPAW', 'AWRE', 'AXAR', 'AXARU', 'AXARW', 'ACLS', 'AXGN', 'AAXN', 'AXSM',
                  'AXTI',
                  'AZRX', 'BCOM', 'RILY', 'RILYL', 'RILYZ', 'BOSC', 'BIDU', 'BCPC', 'BWINA', 'BWINB', 'BLDP', 'BANF',
                  'BANFP',
                  'BCTF', 'BKMU', 'BOCH', 'BMRC', 'BMLP', 'BKSC', 'BOTJ', 'OZRK', 'BFIN', 'BWFG', 'BANR', 'BZUN',
                  'TAPR', 'BHAC',
                  'BHACR', 'BHACU', 'BHACW', 'BBSI', 'BSET', 'BYBK', 'BV', 'BCBP', 'BECN', 'BSF', 'BBGI', 'BEBE',
                  'BBBY', 'BGNE',
                  'BELFA', 'BELFB', 'BLPH', 'BLCM', 'BNCL', 'BNFT', 'BNTC', 'BNTCW', 'BYSI', 'BGCP', 'BGFV', 'BASI',
                  'ORPN',
                  'BIOC', 'BCRX', 'BDSI', 'BIIB', 'BIOL', 'BLFS', 'BLRX', 'BMRN', 'BMRA', 'BVXV', 'BVXVW', 'BPTH',
                  'BIOP',
                  'BIOS', 'BBC', 'BBP', 'BSTC', 'BSTG', 'BSPM', 'TECH', 'BEAT', 'BIVV', 'BCACU', 'BJRI', 'BBOX', 'BDE',
                  'BLKB',
                  'BBRY', 'HAWK', 'BL', 'BKCC', 'ADRA', 'ADRD', 'ADRE', 'ADRU', 'BLMN', 'BCOR', 'BLBD', 'BUFF', 'BHBK',
                  'BLUE',
                  'BKEP', 'BKEPP', 'BPMC', 'ITEQ', 'BMCH', 'BOBE', 'BOFI', 'BOFIL', 'WIFI', 'BOJA', 'BOKF', 'BOKFL',
                  'BNSO',
                  'BOMN', 'BPFH', 'BPFHP', 'BPFHW', 'EPAY', 'BLVD', 'BLVDU', 'BLVDW', 'BCLI', 'BBRG', 'BDGE', 'BLIN',
                  'BRID',
                  'BCOV', 'AVGO', 'BSFT', 'BVSN', 'BYFC', 'BWEN', 'BRCD', 'BRKL', 'BRKS', 'BRKR', 'BMTC', 'BLMT',
                  'BSQR', 'BWLD',
                  'BLDR', 'BMLA', 'BUR', 'CFFI', 'CHRW', 'CA', 'CCMP', 'CDNS', 'CDZI', 'CACQ', 'CZR', 'CSTE', 'PRSS',
                  'CLBS',
                  'CHY', 'CHI', 'CCD', 'CHW', 'CGO', 'CSQ', 'CAMP', 'CVGW', 'CFNB', 'CALA', 'CALD', 'CALM', 'CLMT',
                  'ABCD',
                  'CAC', 'CAMT', 'CSIQ', 'CGIX', 'CPHC', 'CPLA', 'CBF', 'CCBG', 'CPLP', 'CSWC', 'CPTA', 'CPTAG',
                  'CPTAL',
                  'CFFN', 'CAPR', 'CSTR', 'CPST', 'CARA', 'CARB', 'CCN', 'CRME', 'CSII', 'CATM', 'CDNA', 'CECO', 'CTRE',
                  'CARO', 'CART', 'CRZO', 'TAST', 'CRTN', 'CARV', 'CASM', 'CASC', 'CWST', 'CASY', 'CASI', 'CASS',
                  'CATB',
                  'CBIO', 'CPRX', 'CATS', 'CATY', 'CATYW', 'CVCO', 'CAVM', 'CBFV', 'CBAK', 'CBOE', 'CDK', 'CDW', 'CECE',
                  'CELG', 'CELGZ', 'CLDX', 'APOP', 'APOPW', 'CLRB', 'CLRBW', 'CLRBZ', 'CLLS', 'CBMG', 'CLSN', 'CELH',
                  'CYAD'
            , 'CEMP', 'CETX', 'CETXP', 'CETXW', 'CDEV', 'CSFL', 'CETV', 'CFBK', 'CENT', 'CENTA', 'CVCY', 'CENX', 'CNBKA'
            , 'CNTY', 'CRNT', 'CERC', 'CERCW', 'CERN', 'CERU', 'CERS', 'KOOL', 'CEVA', 'CFCO', 'CFCOU', 'CFCOW', 'CSBR',
                  'CYOU', 'HOTR', 'CTHR', 'GTLS', 'CHTR', 'CHFN', 'CHKP', 'CHEK', 'CHEKW', 'CKPT', 'CEMI', 'CHFC',
                  'CCXI',
                  'CHMG', 'CHKE', 'CHFS', 'CHMA', 'PLCE', 'CMRX', 'CADC', 'CALI', 'CAAS', 'CBPO', 'CCCL', 'CCCR',
                  'CCRC',
                  'JRJC', 'HGSH', 'CNIT', 'CJJD', 'CLDC', 'HTHT', 'CHNR', 'CREG', 'CNTF', 'CXDC', 'CCIH', 'CNET',
                  'IMOS', 'CDXC',
                  'CHSCL', 'CHSCM', 'CHSCN', 'CHSCO', 'CHSCP', 'CHDN', 'CHUY', 'CDTX', 'CMCT', 'CMPR', 'CINF', 'CIDM',
                  'CTAS',
                  'CRUS', 'CSCO', 'CTRN', 'CZNC', 'CZWI', 'CZFC', 'CIZN', 'CTXS', 'CHCO', 'CIVB', 'CIVBP', 'CDTI',
                  'CLNE', 'CLNT',
                  'CACG', 'YLDE', 'LRGE', 'CLFD', 'CLRO', 'CLSD', 'CLIR', 'CLIRW', 'CBLI', 'CSBK', 'CLVS', 'CMFN',
                  'CME', 'CCNE',
                  'CWAY', 'COBZ', 'COKE', 'CDXS', 'CODX', 'CVLY', 'JVA', 'CCOI', 'CGNT', 'COGT', 'CGNX', 'CTSH', 'COHR',
                  'CHRS',
                  'COHU', 'CLCT', 'COLL', 'CIGI', 'CBAN', 'COLB', 'COLM', 'CMCO', 'CBMX', 'CBMXW', 'CMCSA', 'CBSH',
                  'CBSHP',
                  'CUBN', 'CHUBA', 'CHUBK', 'CVGI', 'COMM', 'JCS', 'ESXB', 'CFBI', 'CYHHZ', 'CTBI', 'CWBC', 'CVLT',
                  'CGEN',
                  'CPSI', 'CTG', 'CHCI', 'CMTL', 'CNAT', 'CNCE', 'CXRX', 'CCUR', 'CDOR', 'CFMS', 'CNFR', 'CNMD', 'CTWS',
                  'CNOB', 'CNXR', 'CONN', 'CNSL', 'CWCO', 'CNACU', 'CPSS', 'CFRX', 'CTRV', 'CTRL', 'CPAA', 'CPAAU',
                  'CPAAW',
                  'CPRT', 'CRBP', 'CORT', 'CORE', 'CORI', 'CSOD', 'CRVL', 'CRVS', 'CSGP', 'COST', 'CPAH', 'ICBK',
                  'COUP',
                  'CVTI', 'COVS', 'COWN', 'COWNL', 'PMTS', 'CPSH', 'CRAI', 'CBRL', 'BREW', 'CRAY', 'CACC', 'USOI',
                  'CREE',
                  'CRESY', 'CRSP', 'CRTO', 'CROX', 'CCRN', 'CRDS', 'CRWS', 'CYRX', 'CYRXW', 'CSGS', 'CCLP', 'CSPI',
                  'CSWI',
                  'CSX', 'CTIC', 'CTIB', 'CTRP', 'CUNB', 'CUI', 'CPIX', 'CMLS', 'CRIS', 'CUTR', 'CVBF', 'CVV', 'CYAN',
                  'CYBR', 'CYBE', 'CYCC', 'CYCCP', 'CBAY', 'CY', 'CYRN', 'CONE', 'CYTK', 'CTMX', 'CYTX', 'CYTXW',
                  'CTSO', 'CYTR', 'DJCO', 'DAKT', 'DRIO', 'DRIOW', 'DZSI', 'DSKE', 'DSKEW', 'DAIO', 'DWCH', 'PLAY',
                  'DTEA', 'DFNL', 'DUSA', 'DWLD', 'DWSN', 'DBVT', 'DFRG', 'TACO', 'TACOW', 'DCTH', 'DMPI', 'DGAS',
                  'DELT', 'DELTW', 'DENN', 'XRAY', 'DEPO', 'DERM', 'DEST', 'DXLG', 'DSWL', 'DTRM', 'DXCM', 'DXTR',
                  'DHXM', 'DHIL', 'FANG', 'DCIX', 'DRNA', 'DFBG', 'DFFN', 'DGII', 'DGLT', 'DMRC', 'DRAD', 'DGLY',
                  'APPS', 'DCOM', 'DMTX', 'DIOD', 'DISCA', 'DISCB', 'DISCK', 'DISH', 'DVCR', 'SAUC', 'DLHC', 'BOOM',
                  'DNBF', 'DLTR', 'DGICA', 'DGICB', 'DMLP', 'DORM', 'EAGL', 'EAGLU', 'EAGLW', 'DOVA', 'DRWI', 'DRYS',
                  'DSPG', 'DLTH', 'DNKN', 'DRRX', 'DXPE', 'DYSL', 'DYNT', 'DVAX', 'ETFC', 'EBMT', 'EGBN', 'EGLE',
                  'EGRX', 'EWBC', 'EACQ', 'EACQU', 'EACQW', 'EML', 'EVGBC', 'EVSTC', 'EVLMC', 'EBAY', 'EBAYL', 'EBIX',
                  'ELON', 'ECHO', 'SATS', 'EEI', 'ESES', 'EDAP', 'EDGE', 'EDGW', 'EDIT', 'EDUC', 'EGAN', 'EGLT', 'EHTH',
                  'EIGR', 'EKSO', 'LOCO', 'EMITF', 'ESLT', 'ERI', 'ESIO', 'EA', 'EFII', 'ELSE', 'ELEC', 'ELECU',
                  'ELECW', 'EBIO', 'DWAC', 'ESBK', 'ELTK', 'EMCI', 'EMCF', 'EMKR', 'EMMS', 'NYNY', 'ENTA', 'ECPG',
                  'WIRE', 'ENDP', 'ECYT', 'ELGX', 'NDRA', 'NDRAW', 'EIGI', 'WATT', 'EFOI', 'ERII', 'EXXI', 'ENOC',
                  'ENG', 'ENPH', 'ESGR', 'ENFC', 'ENTG', 'ENTL', 'ETRM', 'EBTC', 'EFSC', 'ENZY', '', '', '', '', '', '',
                  '', '', '', 'EPZM', 'PLUS', 'EQIX', 'EQFN', 'EQBK', 'ERIC', 'ERIE', 'ESCA', 'ESPR', 'ESQ', 'ESSA',
                  'EPIX', 'ESND', 'ETSY', 'CLWT', 'EEFT', 'ESEA', 'EVEP', 'EVBG', 'EVK', 'MRAM', 'EVLV', 'EVGN', 'EVOK',
                  'EVOL', 'EXA', 'EXAS', 'EXAC', 'EXEL', 'EXFO', 'EXLS', 'EXPE', 'EXPD', 'EXPO', 'ESRX', 'XOG', 'EXTR',
                  'EYEG', 'EYEGW', 'EZPW', 'FFIV', 'FB', 'FRP', 'FALC', 'DAVE', 'FANH', 'FARM', 'FMAO', 'FFKT', 'FMNB',
                  'FARO', 'FAST', 'FATE', 'FBSS', 'FNHC', 'FHCO', 'GSM', 'FCSC', 'FGEN', 'ONEQ', 'LION', 'FDUS', 'FRGI',
                  'FSAM', 'FSC', 'FSCFL', 'FSFR', 'FITB', 'FITBI', 'FNGN', 'FISI', 'FNSR', 'FNJN', 'FNTE', 'FNTEU',
                  'FNTEW', 'FEYE', 'FBNC', 'FNLC', 'FRBA', 'BUSE', 'FBIZ', 'FCAP', 'FCFS', 'FCNCA', 'FCBC', 'FCCO',
                  'FCFP', 'FBNK', 'FDEF', 'FFBC', 'FFBCW', 'FFIN', 'THFF', 'FFNW', 'FFWM', 'FGBI', 'FHB', 'INBK',
                  'INBKL', 'FIBK', 'FRME', 'FMBH', 'FMBI', 'FNWB', 'FSFG', 'FSLR', 'FSBK', 'FAAR', 'FPA', 'BICK', 'FBZ',
                  'FCAL', 'FCAN', 'FTCS', 'FCEF', 'FCA', 'SKYY', 'RNDM', 'FDT', 'FDTS', 'FVC', 'FV', 'IFV', 'FEM',
                  'RNEM', 'FEMB', 'FEMS', 'FTSM', 'FEP', 'FEUZ', 'FGM', 'FTGC', 'FTHI', 'HYLS', 'FHK', 'FTAG', 'FTRI',
                  'FPXI', 'YDIV', 'FJP', 'FEX', 'FTC', 'RNLC', 'FTA', 'FLN', 'FTLB', 'LMBS', 'FMB', 'FMK', 'FNX', 'FNY',
                  'RNMC', 'FNK', 'FAD', 'FAB', 'MDIV', 'MCEF', 'QABA', 'FTXO', 'QCLN', 'GRID', 'CIBR', 'FTXG', 'CARZ',
                  'FTXN', 'FTXH', 'FTXD', 'FTXL', 'FONE', 'TDIV', 'FTXR', 'QQEW', 'QQXT', 'QTEC', 'AIRR', 'QINC',
                  'RDVY', 'RFAP', 'RFDI', 'RFEM', 'RFEU', 'FTSL', 'FYX', 'FYC', 'RNSC', 'FYT', 'FKO', 'FCVT', 'FDIV',
                  'FSZ', 'FTW', 'FIXD', 'TUSA', 'FKU', 'RNDV', 'FUNC', 'FUSB', 'SVVC', 'FSV', 'FISV', 'FIVE', 'FPRX',
                  'FVE', 'FIVN', 'FLEX', 'FLKS', 'FLXN', 'SKOR', 'LKOR', 'MBSD', 'ASET', 'ESGG', 'ESG', 'QLC', 'FPAY',
                  'FLXS', 'FLIR', 'FLDM', 'FFIC', 'FNBG', 'FOMX', 'FOGO', 'FONR', 'FRSX', 'FH', 'FORM', 'FORTY', 'FORR',
                  'FRTA', 'FTNT', 'FBIO', 'FMCI', 'FMCIR', 'FMCIU', 'FMCIW', 'FWRD', 'FORD', 'FWP', 'FOSL', 'FMI',
                  'FOXF', 'FRAN', 'FELE', 'FKLYU', 'FRED', 'RAIL', 'FEIM', 'FRPT', 'FTEO', 'FTR', 'FTRPR', 'FRPH',
                  'FSBW', 'FSBC', 'FTD', 'FTEK', 'FCEL', 'FLGT', 'FORK', 'FLL', 'FULT', 'FSNN', 'FTFT', 'FFHL', 'WILC',
                  'GTHX', 'FOANC', 'MOGLC', 'GAIA', 'GLPG', 'GALT', 'GALE', 'GLMD', 'GLPI', 'GPIC', 'GRMN', 'GARS',
                  'GDS', 'GEMP', 'GENC', 'GNCMA', 'GFN', 'GFNCP', 'GFNSL', 'GENE', 'GNUS', 'GNMK', 'GNCA', 'GHDX',
                  'GNTX', 'THRM', 'GEOS', 'GABC', 'GERN', 'GEVO', 'ROCK', 'GIGM', 'GIGA', 'GIII', 'GILT', 'GILD',
                  'GBCI', 'GLAD', 'GLADO', 'GOOD', 'GOODM', 'GOODO', 'GOODP', 'GAIN', 'GAINM', 'GAINN', 'GAINO', 'LAND',
                  'LANDP', 'GLBZ', 'GBT', 'GLBR', 'ENT', 'GBLI', 'GBLIL', 'GBLIZ', 'GPAC', 'GPACU', 'GPACW', 'SELF',
                  'GSOL', 'GWRS', 'KRMA', 'FINX', 'ACTX', 'BFIT', 'SNSR', 'LNGR', 'MILN', 'EFAS', 'QQQC', 'BOTZ',
                  'CATH', 'SOCL', 'ALTY', 'SRET', 'YLCO', 'GLBS', 'GLUU', 'GLYC', 'GOGO', 'GLNG', 'GMLP', 'GDEN',
                  'GOGL', 'GBDC', 'GTIM', 'GPRO', 'GSHT', 'GSHTU', 'GSHTW', 'GOV', 'GOVNI', 'GPIA', 'GPIAU', 'GPIAW',
                  'LOPE', 'GRVY', 'FULLL', 'GECC', 'GEC', 'GLDD', 'GSBC', 'GNBC', 'GRBK', 'GPP', 'GPRE', 'GCBC', 'GLRE',
                  'GSUM', 'GRIF', 'GRFS', 'GRPN', 'OMAB', 'GGAL', 'GSIT', 'GSVC', 'GTXI', 'GTYH', 'GTYHU', 'GTYHW',
                  'GBNK', 'GNTY', 'GFED', 'GUID', 'GIFI', 'GURE', 'GPOR', 'GWPH', 'GWGH', 'GYRO', 'HEES', 'HLG', 'HNRG',
                  'HALL', 'HALO', 'HBK', 'HLNE', 'HBHC', 'HBHCL', 'HNH', 'HAFC', 'HQCL', 'HONE', 'HDNG', 'HLIT', 'HRMN',
                  'HRMNU', 'HRMNW', 'HBIO', 'HCAP', 'HCAPL', 'HAS', 'HA', 'HCOM', 'HWKN', 'HWBK', 'HAYN', 'HDS', 'HIIQ',
                  'HCSG', 'HQY', 'HSTM', 'HTLD', 'HTLF', 'HTBX', 'HEBT', 'HSII', 'HELE', 'HMNY', 'HMTV', 'HNNA', 'HSIC',
                  'HTBK', 'HFWA', 'HCCI', 'MLHR', 'HRTX', 'HSKA', 'HIBB', 'SNLN', 'HPJ', 'HIHO', 'HIMX', 'HIFS', 'HSGX',
                  'HMNF', 'HMSY', 'HOLI', 'HOLX', 'HBCP', 'HOMB', 'HFBL', 'HMST', 'HMTA', 'HTBI', 'HOFT', 'HOPE',
                  'HFBC', 'HBNC', 'HZNP', 'HRZN', 'DAX', 'QYLD', 'HDP', 'HPT', 'TWNK', 'TWNKW', 'HMHC', 'HWCC', 'HOVNP',
                  'HBMD', 'HSNI', 'HTGM', 'HUBG', 'HSON', 'HDSN', 'HUNT', 'HUNTU', 'HUNTW', 'HBAN', 'HBANN', 'HBANO',
                  'HBANP', 'HURC', 'HURN', 'HCM', 'HBP', 'HVBC', 'HYGS', 'IDSY', 'IAC', 'IBKC', 'IBKCO', 'IBKCP',
                  'ICAD', 'IEP', 'ICCH', 'ICFI', 'ICHR', 'ICLR', 'ICON', 'ICUI', 'IPWR', 'INVE', 'IDRA', 'IDXX', 'IESC',
                  'IROQ', 'IFMK', 'RXDX', 'INFO', 'IIVI', 'KANG', 'IKNX', 'ILG', 'ILMN', 'ISNS', 'IMMR', 'ICCC', 'IMDZ',
                  'IMNP', '', '', '', '', '', '', '', '', '', 'IMGN', 'IMMU', 'IMRN', 'IMRNW', 'IPXL', 'IMPV', 'PI',
                  'IMMY', 'INCR', 'INCY', 'INDB', 'IBCP', 'IBTX', 'IDSA', 'INFN', 'INFI', 'IPCC', 'III', 'IFON',
                  'IMKTA', 'INWK', 'INNL', 'INOD', 'IPHS', 'IOSP', 'ISSC', 'INVA', 'INGN', 'ITEK', 'INOV', 'INO',
                  'INPX', 'INSG', 'NSIT', 'ISIG', 'INSM', 'INSE', 'IIIN', 'PODD', 'INSY', 'NTEC', 'IART', 'IDTI',
                  'INTC', 'NTLA', 'IPCI', 'IPAR', 'IBKR', 'ICPT', 'IDCC', 'TILE', 'LINK', 'IMI', 'INAP', 'IBOC', 'ISCA',
                  'IGLD', 'IIJI', 'IDXG', 'XENT', 'INTX', 'IVAC', 'INTL', 'ITCI', 'IIN', 'INTU', 'ISRG', 'SNAK', 'ISTR',
                  'ISBC', 'ITIC', 'NVIV', 'IVTY', 'IONS', 'IOVA', 'IPAS', 'DTYS', 'DTYL', 'DTUS', 'DTUL', 'DFVS',
                  'DFVL', 'FLAT', 'DLBS', 'DLBL', 'STPP', 'IPGP', 'CSML', 'IRMD', 'IRTC', 'IRIX', 'IRDM', 'IRDMB',
                  'IRBT', 'IRWD', 'IRCP', 'PMPT', 'SLQD', 'TLT', 'AIA', 'COMT', 'IXUS', 'FALN', 'IFEU', 'IFGL', 'IGF',
                  'GNMA', 'HYXE', 'JKI', 'ACWX', 'ACWI', 'AAXJ', 'EWZS', 'MCHI', 'ESGD', 'SCZ', 'ESGE', 'EEMA', 'EUFN',
                  'IEUS', 'MPCT', 'ENZL', 'QAT', 'UAE', 'ESGU', 'IBB', 'SOXX', 'EMIF', 'ICLN', 'WOOD', 'INDY', 'ISHG',
                  'IGOV', 'ISRL', 'ITI', 'ITRI', 'ITRN', 'ITUS', 'IVENC', 'IVFGC', 'IVFVC', 'IXYS', 'IZEA', 'JJSF',
                  'MAYS', 'JBHT', 'JCOM', 'JASO', 'JKHY', 'JACK', 'JXSB', 'JAGX', 'JAKK', 'JMBA', 'JRVR', 'SGQI',
                  'JSML', 'JSMD', 'JASN', 'JASNW', 'JAZZ', 'JD', 'JSYN', 'JSYNR', 'JSYNU', 'JSYNW', 'JBLU', 'JTPY',
                  'JCTCF', 'WYIG', 'WYIGU', 'WYIGW', 'JMU', 'JBSS', 'JOUT', 'JNCE', 'JNP', 'JUNO', 'KTWO', 'KALU',
                  'KALV', 'KMDA', 'KNDI', 'KPTI', 'KAAC', 'KAACU', 'KAACW', 'KBLM', 'KBLMR', 'KBLMU', 'KBLMW', 'KBSF',
                  'KCAP', 'KRNY', 'KELYA', 'KELYB', 'KMPH', 'KFFB', 'KERX', 'KEQU', 'KTEC', 'KTCC', 'KFRC', 'KE',
                  'KBAL', 'KIN', 'KGJI', 'KINS', 'KONE', 'KNSL', 'KIRK', 'KITE', 'KTOV', 'KTOVW', 'KLAC', 'KLXI',
                  'KONA', 'KOPN', 'KRNT', 'KOSS', 'KWEB', 'KTOS', 'KLIC', 'KURA', 'KVHI', 'FSTR', 'LJPC', 'LSBK',
                  'LBAI', 'LKFN', 'LAKE', 'LRCX', 'LAMR', 'LANC', 'LCA', 'LCAHU', 'LCAHW', 'LNDC', 'LARK', 'LMRK',
                  'LMRKO', 'LMRKP', 'LE', 'LSTR', 'LNTH', 'LTRX', 'LSCC', 'LAUR', 'LAWS', 'LAYN', 'LCNB', 'LBIX',
                  'LPTX', 'LGCY', 'LGCYO', 'LGCYP', 'LTXB', 'DDBI', 'EDBI', 'INFR', 'LVHD', 'UDBI', 'LMAT', 'TREE',
                  'LXRX', 'LGIH', 'LHCG', 'LLIT', 'LBRDA', 'LBRDK', 'LEXEA', 'LEXEB', 'LBTYA', 'LBTYB', 'LBTYK', 'LILA',
                  'LILAK', 'LVNTA', 'LVNTB', 'QVCA', 'QVCB', 'BATRA', 'BATRK', 'FWONA', 'FWONK', 'LSXMA', 'LSXMB',
                  'LSXMK', 'TAX', 'LTRPA', 'LTRPB', 'LPNT', 'LCUT', 'LFVN', 'LWAY', 'LGND', 'LTBR', 'LPTH', 'LLEX',
                  'LMB', 'LLNW', 'LMNR', 'LINC', 'LECO', 'LIND', 'LINDW', 'LINU', 'LPCN', 'LQDT', 'LFUS', 'LIVN', 'LOB',
                  'LIVE', 'LPSN', 'LKQ', 'LMFA', 'LMFAW', 'LOGI', 'LOGM', 'EVAR', 'CNCR', 'LONE', 'LTEA', 'LORL',
                  'LOXO', 'LPLA', 'LRAD', 'LYTS', 'LULU', 'LITE', 'LMNX', 'LMOS', 'LUNA', 'MBTF', 'MACQ', 'MACQU',
                  'MACQW', 'MIII', 'MIIIU', 'MIIIW', 'MBVX', 'MCBC', 'MFNC', 'MTSI', 'MGNX', 'MDGL', 'MAGS', 'MGLN',
                  'MGIC', 'CALL', 'MNGA', 'MGYR', 'MHLD', 'MSFG', 'MMYT', 'MBUU', 'MLVF', 'MAMS', 'TUSK', 'MANH',
                  'LOAN', 'MNTX', 'MTEX', 'MNKD', 'MANT', 'MARA', 'MCHX', 'MARPS', 'MRNS', 'MKTX', 'MRLN', 'MAR',
                  'MBII', 'MRTN', 'MMLP', 'MRVL', 'MASI', 'MTCH', 'MTLS', 'MPAC', 'MPACU', 'MPACW', 'MTRX', 'MAT',
                  'MATR', 'MATW', 'MXIM', 'MXPT', 'MXWL', 'MZOR', 'MBFI', 'MBFIP', 'MCFT', 'MGRC', 'MDCA', 'MFIN',
                  'MFINL', 'MTBC', 'MTBCP', 'MNOV', 'MDSO', 'MDGS', 'MDWD', 'MDVX', 'MDVXW', 'MEDP', 'MEIP', 'MLCO',
                  'MLNX', 'MELR', 'MTSL', 'MELI', 'MBWM', 'MERC', 'MRCY', 'EBSB', 'VIVO', 'MRDN', 'MRDNW', 'MMSI',
                  'MACK', 'MRSN', 'MSLI', 'MRUS', 'MLAB', 'MESO', 'CASH', 'MEOH', 'MGCD', 'MGEE', 'MGPI', 'MBOT',
                  'MCHP', 'MU', 'MICT', 'MICTW', 'MSCC', 'MSFT', 'MSTR', 'MVIS', 'MPB', 'MTP', 'MCEP', 'MBCN', 'MSEX',
                  'MSBI', 'MOFG', 'MIME', 'MDXG', 'MNDO', 'MB', 'NERV', 'MGEN', 'MRTX', 'MIRN', 'MSON', 'MIND', 'MINDP',
                  'MITK', 'MITL', 'MKSI', 'MMAC', 'MINI', 'MOBL', 'MMDM', 'MMDMR', 'MMDMU', 'MMDMW', 'MLNK', 'MBRX',
                  'MNTA', 'MOMO', 'MCRI', 'MDLZ', 'MGI', 'MPWR', 'TYPE', 'MNRO', 'MRCC', 'MNST', 'MSDI', 'MSDIW',
                  'MORN', 'MOSY', 'MOTA', 'MOTAW', 'MTFB', 'MTFBW', 'MPAA', 'MPVD', 'MOXC', 'MRVC', 'MSBF', 'MSG',
                  'MTGE', 'MTGEP', 'MTSC', 'LABL', 'MFSF', 'MYSZ', 'MYL', 'MYND', 'MYNDW', 'MYOK', 'MYOS', 'MYRG',
                  'MYGN', 'NBRV', 'NAKD', 'NNDM', 'NANO', 'NSTG', 'NH', 'NK', 'NSSC', 'NDAQ', 'NTRA', 'NATH', 'NAUH',
                  'NKSH', 'FIZZ', 'NCMI', 'NCOM', 'NESR', 'NESRW', 'NGHC', 'NGHCN', 'NGHCO', 'NGHCP', 'NGHCZ', 'NHLD',
                  'NHLDW', 'NATI', 'NRCIA', 'NRCIB', 'NSEC', 'NWLI', 'NAII', 'NHTC', 'NATR', 'BABY', 'ISM', 'JSM',
                  'NAVI', 'NBTB', 'NCIT', 'NCSM', 'NKTR', 'NEOG', 'NEO', 'NEON', 'NEOS', 'NEOT', 'NVCN', 'NEPT', 'UEPS',
                  'NETE', 'NTAP', 'NTES', 'NFLX', 'NTGR', 'NLST', 'NTCT', 'NTWK', 'CUR', 'NBIX', 'NDRM', 'NURO',
                  'NUROW', 'NTRP', 'NBEV', 'NYMT', 'NYMTO', 'NYMTP', 'NLNK', 'NWS', 'NWSA', 'NEWS', 'NEWT', 'NEWTL',
                  'NEWTZ', 'NXEO', 'NXEOU', 'NXEOW', 'NXST', 'NVET', 'NFEC', 'NODK', 'EGOV', 'NICE', 'NICK', 'NCBS',
                  'NIHD', 'NVLS', 'NMIH', 'NNBR', 'NDLS', 'NDSN', 'NSYS', 'NBN', 'NTIC', 'NTRS', 'NTRSP', 'NFBK',
                  'NRIM', 'NWBI', 'NWPX', 'NCLH', 'NWFL', 'NVFY', 'NVMI', 'NVDQ', 'NOVN', 'NOVT', 'NVAX', 'NVLN',
                  'NVCR', 'NVGN', 'NVUS', 'NUAN', 'NMRX', 'NTNX', 'NUTR', 'NTRI', 'NUVA', 'NVTR', 'QQQX', 'NVEE',
                  'NVEC', 'NVDA', 'NXPI', 'NXTM', 'NXTD', 'NXTDW', 'NYMX', 'OIIM', 'OVLY', 'OASM', 'OBLN', 'OBSV',
                  'OBCI', 'OPTT', 'ORIG', 'OCFC', 'OCRX', 'OCLR', 'OFED', 'OCUL', 'OMEX', 'ODP', 'OFS', 'OHAI', 'OVBC',
                  'OHRP', 'OKTA', 'ODFL', 'OLBK', 'ONB', 'OPOF', 'OSBC', 'OSBCP', 'OLLI', 'ZEUS', 'OFLX', 'OMER',
                  'OMNT', 'OMCL', 'ON', 'OTIV', 'ONS', 'ONSIW', 'ONSIZ', 'OGXI', 'OMED', 'ONTX', 'ONTXW', 'ONCS',
                  'OHGI', 'ONVI', 'OTEX', 'OPXA', 'OPXAW', 'OPGN', 'OPGNW', 'OPHT', 'OPK', 'OBAS', 'OCC', 'OPHC', 'OPB',
                  'ORMP', 'OSUR', 'ORBC', 'ORBK', 'ORLY', 'OREX', 'ONVO', 'SEED', 'OACQ', 'OACQR', 'OACQU', 'OACQW',
                  'OESX', 'ORIT', 'ORRF', 'OFIX', 'OSIS', 'OSN', 'OTEL', 'OTIC', 'OTTW', 'OTTR', 'OVAS', 'OSTK', 'OVID',
                  'OXBR', 'OXBRW', 'OXFD', 'OXLC', 'OXLCM', 'OXLCN', 'OXLCO', 'PFIN', 'PTSI', 'PCAR', 'PACB', 'PCBK',
                  'PEIX', 'PMBC', 'PPBI', 'PAAC', 'PAACR', 'PAACU', 'PAACW', 'PCRX', 'PACW', 'PTIE', 'PAAS', 'PNRA',
                  'PANL', 'PZZA', 'FRSH', 'PBNC', 'PRTK', 'PRXL', 'PCYG', 'PSTB', 'PKBK', 'PRKR', 'PKOH', 'PTNR',
                  'PBHC', 'PATK', 'PNBK', 'PATI', 'PEGI', 'PDCO', 'PTEN', 'PAVM', 'PAVMW', 'PAYX', 'PCTY', 'PYDS',
                  'PYPL', 'PBBI', 'CNXN', 'PCMI', 'PCSB', 'PCTI', 'PDCE', 'PDFS', 'PDLI', 'PDVW', 'SKIS', 'PGC', 'PEGA',
                  'PCO', 'PENN', 'PVAC', 'PFLT', 'PNNT', 'PWOD', 'PTXP', 'PEBO', 'PEBK', 'PFBX', 'PFIS', 'PBCT',
                  'PBCTP', 'PUB', 'PRCP', 'PPHM', 'PPHMP', 'PRFT', 'PFMT', 'PERF', 'PERI', 'PESI', 'PPIH', 'PTX',
                  'PERY', 'PGLC', 'PETS', 'PFSW', 'PGTI', 'PZRX', 'PHII', 'PHIIK', 'PAHC', 'PHMD', 'PLAB', 'PICO',
                  'PIRS', 'PPC', 'PME', 'PNK', 'PNFP', 'PPSI', 'PXLW', 'PLPM', 'PLYA', 'PLYAW', 'PLXS', 'PLUG', 'PLBC',
                  'PSTI', 'PLXP', 'PBSK', 'PNTR', 'PCOM', 'POLA', 'COOL', 'POOL', 'POPE', 'BPOP', 'BPOPM', 'BPOPN',
                  'PBIB', 'PTLA', 'PBPB', 'PCH', 'POWL', 'POWI', 'PLW', 'PKW', 'PFM', 'PYZ', 'PEZ', 'PSL', 'PIZ', 'PIE',
                  'PXI', 'PFI', 'PTH', 'PRN', 'DWLV', 'PDP', 'DWAQ', 'DWAS', 'DWIN', 'DWTR', 'PTF', 'PUI', 'IDLB',
                  'PRFZ', 'PAGG', 'PSAU', 'PIO', 'PGJ', 'PEY', 'IPKW', 'PID', 'KBWB', 'KBWD', 'KBWY', 'KBWP', 'KBWR',
                  'LDRI', 'LALT', 'PNQI', 'PDBC', 'QQQ', 'USLB', 'PSCD', 'PSCC', 'PSCE', 'PSCF', 'PSCH', 'PSCI', 'PSCT',
                  'PSCM', 'PSCU', 'VRIG', 'PHO', 'PRAA', 'PRAH', 'PRAN', 'PRPO', 'PFBC', 'PLPC', 'PFBI', 'PINC', 'LENS',
                  'PSDO', 'PRGX', 'PSMT', 'PBMD', 'PNRG', 'PRMW', 'PRIM', 'BTEC', 'GENY', 'PSET', 'PY', 'PSC', 'PDEX',
                  'IPDN', 'PFIE', 'PGNX', 'PRGS', 'PFPT', 'PRPH', 'PRQR', 'BIB', 'UBIO', 'TQQQ', 'ZBIO', 'SQQQ', 'BIS',
                  'PSEC', 'PTGX', 'PRTO', 'PTI', 'PRTA', 'PVBC', 'PROV', 'PBIP', 'PSDV', 'PMD', 'PTC', 'PTCT', 'PULM',
                  'PLSE', 'PBYI', 'PCYO', 'IMED', 'FINQ', 'PXS', 'QADA', 'QADB', 'QCRH', 'QGEN', 'QIWI', 'QRVO', 'QCOM',
                  'QSII', 'QBAK', 'QLYS', 'QTNA', 'QTRH', 'QRHC', 'QUIK', 'QDEL', 'QPAC', 'QPACU', 'QPACW', 'QNST',
                  'QUMU', 'QTNT', 'RRD', 'RCM', 'RARX', 'RADA', 'RDCM', 'RSYS', 'RDUS', 'RDNT', 'RDWR', 'METC', 'RMBS',
                  'RAND', 'RLOG', 'GOLD', 'RNDB', 'RPD', 'RAVE', 'RAVN', 'ROLL', 'RICK', 'RCMT', 'RDI', 'RDIB', 'RGSE',
                  'RELY', 'RNWK', 'RP', 'RETA', 'RCON', 'REPH', 'RRGB', 'RRR', 'RDHL', 'REGN', 'RGNX', 'RGLS', 'REIS',
                  'RELV', 'MARK', 'RNST', 'REGI', 'RNVA', 'RNVAZ', 'RCII', 'RTK', 'RGEN', 'RPRX', 'RBCAA', 'FRBK',
                  'REFR', 'RESN', 'RECN', 'ROIC', 'RTRX', 'RVNC', 'RVEN', 'RVLT', 'RWLK', 'REXX', 'RFIL', 'RGCO',
                  'RIBT', 'RIBTW', 'RELL', 'RIGL', 'NAME', 'RNET', 'RTTR', 'RVSB', 'RLJE', 'RMGN', 'ROBO', 'FUEL',
                  'RMTI', 'RCKY', 'RMCF', 'ROKA', 'RTNB', 'ROSE', 'ROSEU', 'ROSEW', 'ROSG', 'ROST', 'RBPAA', 'RGLD',
                  'RPXC', 'RTIX', 'RBCN', 'RUSHA', 'RUSHB', 'RUTH', 'RXII', 'RXIIW', 'RYAAY', 'STBA', 'SANW', 'SCAC',
                  'SCACU', 'SCACW', 'SBRA', 'SBRAP', 'SABR', 'SAEX', 'SAFT', 'SAGE', 'SAIA', 'SAJA', 'SALM', 'SAL',
                  'SAFM', 'SASR', 'SGMO', 'SANM', 'GCVRZ', 'SPNS', 'SRPT', 'SVRA', 'SBFG', 'SBFGP', 'SBAC', 'SCSC',
                  'SMIT', 'SCHN', 'SCHL', 'SCLN', 'SGMS', 'SNI', 'SCYX', 'SEAC', 'SBCF', 'STX', 'SHIP', 'SHIPW', 'SRSC',
                  'SHLD', 'SHLDW', 'SHOS', 'SPNE', 'SGEN', 'EYES', 'EYESW', 'SCWX', 'SNFCA', 'SEIC', 'SLCT', 'SCSS',
                  'SIR', 'SELB', 'SIGI', 'LEDS', 'SMTC', 'SENEA', 'SENEB', 'SNES', 'SNH', 'SNHNI', 'SNHNL', 'SNMX',
                  'SRTS', 'SRTSW', 'SQBG', 'MCRB', 'SREV', 'SFBS', 'SEV', 'SVBI', 'SGBX', 'SGOC', 'SMED', 'SHSP',
                  'SHEN', 'PIXY', 'SHLO', 'TYHT', 'SHPG', 'SCVL', 'SHBI', 'SHOR', 'SSTI', 'SFLY', 'SIFI', 'SIEB',
                  'SIEN', 'BSRR', 'SRRA', 'SWIR', 'SIFY', 'SIGM', 'SGLB', 'SGLBW', 'SGMA', 'SBNY', 'SBNYW', 'SLGN',
                  'SILC', 'SLAB', 'SIMO', 'SPIL', 'SRUN', 'SRUNU', 'SRUNW', 'SSRI', 'SAMG', 'SSNT', 'SFNC', 'SLP',
                  'SINA', 'SBGI', 'SINO', 'SVA', 'SIRI', 'SITO', 'SKYS', 'SKLN', 'SKYW', 'SWKS', 'SLM', 'SLMBP', 'SGH',
                  'SND', 'SMBK', 'SMSI', 'SMTX', 'LNCE', 'SRAX', 'SCKT', 'SODA', 'SOHU', 'SLRC', 'SUNS', 'SEDG', 'SLNO',
                  'SLNOW', 'SNGX', 'SNGXW', 'SONC', 'SOFO', 'SNOA', 'SNOAW', 'SONS', 'SPHS', 'SORL', 'SRNE', 'SOHO',
                  'SOHOB', 'SOHOM', 'SFBC', 'SSB', 'SFST', 'SMBC', 'SONA', 'SBSI', 'OKSB', 'SP', 'SGRP', 'SPKE',
                  'SPKEP', 'ONCE', 'SPAR', 'SPTN', 'DWFI', 'SPPI', 'ANY', 'SPEX', 'SPI', 'SAVE', 'SPLK', 'SPOK', 'SPWH',
                  'SBPH', 'FUND', 'SFM', 'SPSC', 'SSNC', 'STAA', 'STAF', 'STMP', 'STLY', 'SPLS', 'SBLK', 'SBLKL',
                  'SBUX', 'STFC', 'STBZ', 'SNC', 'STDY', 'GASS', 'STLD', 'SMRT', 'STLR', 'STLRU', 'STLRW', 'SBOT',
                  'STML', 'SRCL', 'SRCLP', 'STRL', 'SHOO', 'SSFN', 'SYBT', 'BANX', 'SGBK', 'SSKN', 'SSYS', 'STRT',
                  'STRS', 'STRA', 'STRM', 'SBBP', 'STB', 'SCMP', 'SUMR', 'SMMF', 'SSBI', 'SMMT', 'SNBC', 'SNHY', 'SNDE',
                  'SNSS', 'STKL', 'SPWR', 'RUN', 'SBCP', 'SUNW', 'SMCI', 'SPCB', 'SCON', 'SGC', 'SUPN', 'SPRT', 'SGRY',
                  'SRDX', 'SBBX', 'SIVB', 'SIVBO', 'SYKE', 'SYMC', 'SYNC', 'SYNL', 'SYNA', 'SNCR', 'SNDX', 'SGYP',
                  'ELOS', 'SNPS', 'SYNT', 'SYMX', 'SYPR', 'SYRS', 'TROW', 'TTOO', 'TRHC', 'TCMD', 'TAIT', 'TTWO',
                  'TLND', 'TNDM', 'TLF', 'TANH', 'TPIV', 'TEDU', 'TATT', 'TAYD', 'CGBD', 'TCPC', 'AMTD', 'TEAR', 'TECD',
                  'TCCO', 'TTGT', 'TGLS', 'TGEN', 'TNAV', 'TTEC', 'TLGT', 'TELL', 'TENX', 'GLBL', 'TERP', 'TVIA',
                  'TBNK', 'TSRO', 'TESO', 'TSLA', 'TESS', 'TTEK', 'TTPH', 'TCBI', 'TCBIL', 'TCBIP', 'TCBIW', 'TXN',
                  'TXRH', 'TFSL', 'TGTX', 'ABCO', 'ANDE', 'TBBK', 'BONT', 'CG', 'CAKE', 'CHEF', 'TCFC', 'DSGX', 'DXYN',
                  'ENSG', 'XONE', 'FINL', 'FBMS', 'FLIC', 'GT', 'HABT', 'HCKT', 'HAIN', 'FITS', 'CUBA', 'INTG', 'JYNT',
                  'KEYW', 'KHC', 'OLD', 'MDCO', 'MEET', 'MIK', 'MIDD', 'NAVG', 'SLIM', 'STKS', 'ORG', 'PCLN', 'PRSC',
                  'RMR', 'SPNC', 'TTD', 'ULTI', 'YORW', 'NCTY', 'TRPX', 'TBPH', 'TST', 'TCRD', 'THLD', 'TICC', 'TICCL',
                  'TIG', 'TTS', 'TIL', 'TSBK', 'TNTR', 'TIPT', 'TITN', 'TTNP', 'TVTY', 'TIVO', 'TMUS', 'TMUSP', 'TOCA',
                  'TNXP', 'TISA', 'TOPS', 'TORM', '', '', '', '', '', '', '', '', '', 'TRCH', 'TSEM', 'CLUB', 'TOWN',
                  'TPIC', 'TCON', 'TSCO', 'TWMC', 'TACT', 'TRNS', 'TGA', 'TA', 'TANNI', 'TANNL', 'TANNZ', 'TZOO',
                  'TRVN', 'TCBK', 'TRIL', 'TRS', 'TRMB', 'TRIB', 'TRIP', 'TSC', 'TBK', 'TRVG', 'TRNC', 'TROV', 'TRUE',
                  'THST', 'TRUP', 'TRST', 'TRMK', 'TSRI', 'TTMI', 'TCX', 'TUES', 'TOUR', 'HEAR', 'TUTI', 'TUTT', 'FOX',
                  'FOXA', 'TWIN', 'TRCB', 'USCR', 'PRTS', 'USEG', 'GROW', 'USAU', 'UBNT', 'UFPT', 'ULTA', 'UCTT', 'UPL',
                  'RARE', 'ULBI', 'UMBF', 'UMPQ', 'UNAM', 'UBSH', 'UNB', 'UNXL', 'QURE', 'UBCP', 'UBOH', 'UBSI', 'UCBA',
                  'UCBI', 'UCFC', 'UBNK', 'UFCS', 'UIHC', 'UNFI', 'UBFO', 'USLM', 'UTHR', 'UG', 'UNIT', 'UNTY', 'OLED',
                  'UEIC', 'UFPI', 'ULH', 'USAP', 'UVSP', 'UPLD', 'URRE', 'UONE', 'UONEK', 'URBN', 'URGN', 'ECOL',
                  'USAT', 'USATP', 'USAK', 'UTMD', 'UTSI', 'VLRX', 'VALX', 'VALU', 'VNDA', 'BBH', 'GNRX', 'PPH', 'VWOB',
                  'VNQI', 'VGIT', 'VCIT', 'VIGI', 'VYMI', 'VCLT', 'VGLT', 'VMBS', 'VONE', 'VONG', 'VONV', 'VTWO',
                  'VTWG', 'VTWV', 'VTHR', 'VCSH', 'VGSH', 'VTIP', 'BNDX', 'VXUS', 'VEAC', 'VEACU', 'VEACW', 'VREX',
                  'VRNS', 'VDSI', 'VBLT', 'VBIV', 'WOOF', 'VECO', 'DGLD', 'DSLV', 'UGLD', 'USLV', 'TVIZ', 'TVIX', 'ZIV',
                  'XIV', 'VIIZ', 'VIIX', 'VEON', 'VRA', 'VCYT', 'VSTM', 'VCEL', 'VRNT', 'VRSN', 'VRSK', 'VBTX', 'VERI',
                  'VRML', 'VRNA', 'VSAR', 'VTNR', 'VRTX', 'VIA', 'VIAB', 'VSAT', 'VIAV', 'VICL', 'VICR', 'CIZ', 'VSDA',
                  'CEZ', 'CID', 'CIL', 'CFO', 'CFA', 'CSF', 'CDC', 'CDL', 'VSMV', 'CSB', 'CSA', 'VBND', 'VUSE', 'VIDI',
                  'VDTH', 'VRAY', 'VKTX', 'VKTXW', 'VBFC', 'VLGEA', 'VNOM', 'VIRC', 'VIRT', 'VRTS', 'VRTSP', 'VRTU',
                  'VTGN', 'VTL', 'VIVE', 'VVPR', 'VVUS', 'VOD', 'VOXX', 'VYGR', 'VSEC', 'VTVT', 'VUZI', 'VWR', 'WBA',
                  'WAFD', 'WAFDW', 'WASH', 'WFBI', 'WSBF', 'WVE', 'WAYN', 'WSTG', 'WCFB', 'WDFC', 'FLAG', 'WEB', 'WBMD',
                  'WCST', 'WB', 'WEBK', 'WEN', 'WERN', 'WSBC', 'WTBA', 'WSTC', 'WMAR', 'WABC', 'WBB', 'WSTL', 'WDC',
                  'WNEB', 'WLB', 'WPRT', 'WEYS', 'WHLR', 'WHLRD', 'WHLRP', 'WHLRW', 'WHF', 'WHFBL', 'WFM', 'WHLM',
                  'WVVI', 'WVVIP', 'WLDN', 'WLFC', 'WLTW', 'WIN', 'WING', 'WINA', 'WINS', 'WTFC', 'WTFCM', 'WTFCW',
                  'AGZD', 'AGND', 'CXSE', 'EMCG', 'EMCB', 'DGRE', 'DXGE', 'HYZD', 'WETF', 'DXJS', 'GULF', 'HYND',
                  'CRDT', 'DGRW', 'DGRS', 'DXPS', 'UBND', 'WIX', 'WMIH', 'WBKC', 'WWD', 'WKHS', 'WRLD', 'WPCS', 'WPPGY',
                  'WMGI', 'WMGIZ', 'WSFS', 'WSFSL', 'WSCI', 'WVFC', 'WYNN', 'XBIT', 'XELB', 'XCRA', 'XNCR', 'XBIO',
                  'XBKS', 'XENE', 'XGTI', 'XGTIW', 'XLNX', 'GLDI', 'SLVO', 'XOMA', 'XPER', 'XPLR', 'XTLB', 'XNET',
                  'YNDX', 'YERR', 'YTRA', 'YTEN', 'YIN', 'YGYI', 'YRCW', 'YECO', 'YY', 'ZFGN', 'ZAGG', 'ZAIS', 'ZBRA',
                  'Z', 'ZG', 'ZN', 'ZNWAA', 'ZION', 'ZIONW', 'ZIONZ', 'ZIOP', 'ZIXI', 'ZGNX', 'ZSAN', 'ZUMZ', 'ZYNE',
                  'ZNGA']

        self.testing = True

        self.trading_logic_start_time = '09:40:00'
        self.market_open = '09:30:00'
        self.eod = '15:30:00'

        self.parallel_traded_inst = 2
        self.cap_usd = 11000.0
        self.account_margin = .25
        self.vola_exposure = .07
        self.max_price_instr_usd = 500.0
        self.max_investment_per_instr = .8
        self.max_trades_per_instr_per_day = 4 #min 2, even number because of sell EOD)
        self.cnt_trades_per_instr_per_day = 0
        self.stop_loss = .2 #min 2, even because of sell EOD)
        self.book = pd.DataFrame(columns=['reqId','position','marketMaker','side','price','size'])
        self.n_willingness_to_move_up_price = 4 #times, alter deducted by 1
        self.mins_sell_before_eob = 15
        self.held_reqIds = []
        self.held_instruments = {}

        self.mas_bar_size_secs = 30
        self.mas_long_mins = 15
        self.mas_short_mins = 5
        self.ma_counter = 0
        self.ma_patience_to_turn_mins = 45

        self.winners = self.find_winners_based_on_vola_volu(island)

        if True:
            return

        contract = Contract()
        for customReqId, symbol in enumerate(self.winners):
            contract.symbol = symbol
            contract.secType = "STK"
            contract.currency = "USD"
            contract.exchange = "ISLAND"
            # if self.sim_mkt_dpt:
            #     self.sim_mkt_pos_rand_n_pos = random.randint(10,100)
            self.reqMktDepth(customReqId, contract, 5, [])

    @iswrapper
    def waiter(self, secs):
        print("wait {} secs".format(str(secs)))
        for i in range(secs):
            print(i)
            time.sleep(1)

    @iswrapper
    def find_winners_based_on_vola_volu(self, stocks):
        self.req_todays_data(stocks)
        # self.rec_todays_data()

    @iswrapper
    def req_todays_data(self, stocks):
        while datetime.datetime.now().time() < datetime.datetime.strptime(self.market_open,'%H:%M:%S').time():
            time.sleep(5)

        while datetime.datetime.now().time() < datetime.datetime.strptime(self.trading_logic_start_time,'%H:%M:%S').time():
            time.sleep(5)

        contract = Contract()
        bars = datetime.datetime.strptime(self.trading_logic_start_time,'%H:%M:%S') - datetime.datetime.strptime(self.market_open,'%H:%M:%S')
        for ix, c in enumerate(stocks[0:1]):#self.market_data_lines-1
            contract.symbol = "TSLA"#c
            contract.secType = "STK"
            contract.currency = "USD"
            contract.exchange = "SMART"
            self.reqHistoricalData(ix, contract, "20180716 10:30:00",
                                   "2 D", "1 hour", "MIDPOINT", 1, 1, False, [])#.format(str(bars.seconds))
            # datetime.datetime.now().strftime("%Y%m%d %H:%M:%S GMT")
            if ix % 5 == 0:
                if sys.getsizeof(self.hist_data_q) > 1000000000 * 8: #GB * byte

                    # self.cancelHistoricalData()

                    wrap_up = []
                    while True:
                        try:
                            wrap_up.append(self.hist_data_q.get(False))
                        except:
                            break
                    file_name = "wrap_up{}".format(datetime.datetime.now())
                    file_object = open(file_name,'wb')
                    pickle.dump(wrap_up,file_object)
                    file_object.close()
                    # file_object = open(file_name,'r')
                    # b = pickle.load(file_object)

    # @printWhenExecuting
    @iswrapper
    def rec_todays_data(self):
        wrap_up = []
        while True:
            try:
                wrap_up.append(self.hist_data_q.get(False)) # False param is important because oterhwise nothing is thrown
            except:
                if len(wrap_up) == 0:
                    print("nothing in queue yet")
                    self.waiter(3)
                    continue
                else:
                    break
        vola_volu_li = [
                [
                    i[0],
                    i[1].date,
                    i[1].volume,
                    (i[1].high - i[1].low) / i[1].low,
                    (i[1].close - i[1].open) / i[1].open
                ]
                for i in wrap_up]
        df = pd.DataFrame(vola_volu_li, columns=['reqId','tm','vol','swing','change'])
        vol = df.groupby(['reqId'])['vol'].mean().sort_values(ascending=False)
        swing = df.groupby(['reqId'])['swing'].std().sort_values(ascending=False)
        chg = df.groupby(['reqId'])['change'].mean().sort_values(ascending=False)
        matches = []
        for i in list(vol):
            for j in list(chg):
                if i[0] == j[0]:
                    matches.append(j)
                    break
            if len(matches) == self.parallel_traded_inst:
                break
        # file_object = open(file_name,'r')
        # b = pickle.load(file_object)
        return matches

    @iswrapper
    def hist_dat_pacing_violations(self, now):
        self.prior_time = ''
        # Making identical historical data requests within 15 seconds.
        # Making six or more historical data requests for the same Contract, Exchange and Tick Type within two seconds.
        # Making more than 60 requests within any ten minute period.

    # def historicalData(self, reqId: int, bar: BarData):
    #     if self.testing:
    #         print("putting ", reqId)
    #     self.hist_data_q.put([reqId, bar])

    @iswrapper
    def historicalDataEnd(self, reqId:int, start:str, end:str):
        super().historicalDataEnd(reqId, start, end)

    @iswrapper
    # ! [historicaldata]
    def historicalData(self, reqId:int, bar: BarData):
        self.hist_data_q.put([reqId, bar])
        print("HistoricalData. ", reqId, " Date:", bar.date, "Open:", bar.open,
              "High:", bar.high, "Low:", bar.low, "Close:", bar.close, "Volume:", bar.volume,
              "Count:", bar.barCount, "WAP:", bar.average)
    # ! [historicaldata]
    #
    # @iswrapper
    # # ! [historicaldataend]
    # def historicalDataEnd(self, reqId: int, start: str, end: str):
    #     super().historicalDataEnd(reqId, start, end)
    #     print("HistoricalDataEnd ", reqId, "from", start, "to", end)
    # # ! [historicaldataend]

    # @printWhenExecuting
    @iswrapper
    def make_trade_decision(self, reqId, order):
        if order == 'BUY':
            side = 1 #bid
        elif order == 'SELL':
            side = 0 #ask
        else:
            raise Exception('must be either BUY or SELL')

        buy_conditions = self.buy_conditions(reqId)
        if order == 'BUY' and not buy_conditions:
            status = -1
        elif order == 'BUY' and buy_conditions:
            buy_try = 0
            while True:
                price, size = self.price_size_sel(buy_try, side, reqId)
                if price > self.max_price_instr_usd:
                    status = 1
                    break
                budget = self.cap_usd / self.parallel_traded_inst * self.max_investment_per_instr
                offer = price * size
                if offer < budget:
                    buy_try += 1
                else:
                    status = 0
                    #BUY
                    self.held_reqIds.append(reqId)
                    break
                if buy_try == self.n_willingness_to_move_up_price - 1:
                    status = -1
                    break
        elif order == 'SELL' and not self.sell_conditions():
            status = -1
        elif order == 'SELL' and self.sell_conditions():
            sell_try = 0
            while True:
                price, size = self.price_size_sel(sell_try, side, reqId)
                # offer = price * size
                # held_position = self.held_instruments[str(reqId)]['size'] * price
                if size < self.held_instruments[str(reqId)]['size']:
                    sell_try += 1
                else:
                    status = 0
                    #SELL
                    break
                if sell_try == self.n_willingness_to_move_up_price - 1:
                    status = -1
                    break
        elif order == 'SELL' and self.stop_loss_f(reqId):
            #SELL with MKT
            pass

        # statuses:
        # -1 = next try/price up
        # 0 = ok = buy/sell
        # 1 = other conditions not met = abandon
        return status

    @iswrapper
    def price_size_sel(self, ix, side, reqId):
        if side == 1:
            asc = False
        else:
            asc = True
        price, size = tuple(
                self.book[(self.book.reqId == reqId) & (self.book.side == side)]
                    .sort(by=['price'], ascending=asc)[['price', 'size']].iloc[ix]
            )
        return price, size

    @iswrapper
    def buy_conditions(self, reqId):
        short_ma_greater_than_long = self.moving_averages(reqId)
        return_minimal = True
        while True:
            if not short_ma_greater_than_long:
                return False
            if not return_minimal:
                return False
            return True

    def sell_conditions(self):
        return True

    @iswrapper
    def stop_loss_f(self, reqId):
        current_ask_price = self.current_price(reqId, side=0)
        change = (current_ask_price - self.held_instruments[reqId]) / current_ask_price
        if change < -self.stop_loss:
            return True
        else:
            return False

    @iswrapper
    def moving_averages(self, reqId):
        # ma procedure
        ma_run_interval_mins = 2
        times_to_run_ma = []
        roughly_mins = int( ( int(self.eod[0:1]) + 1 - int(self.trading_logic_start_time[0:1])  ) * 60 ) #+ 1 in order not to have too few, safety
        n_intervals = int(roughly_mins / ma_run_interval_mins)
        curr_hour = int(self.trading_logic_start_time[0:1])
        for i in range(0,n_intervals, ma_run_interval_mins):
            if i % 60 == 0:
                curr_hour = int(self.trading_logic_start_time[0:1]) + int(i / 60)
            curr_min = int(self.trading_logic_start_time[3:4]) + i - (int(i / 60) * 60)
            time_str = str(curr_hour) + ':' + str(curr_min) + ':00'
            times_to_run_ma.append(time_str)

        item = datetime.datetime.strptime(times_to_run_ma[self.ma_counter],"%H:%M:%S")
        unix_ts = np.array(pd.DataFrame([[item]])).astype(np.int64)[0,0]
        variance_secs = 3
        unix_now = np.array(pd.DataFrame([[datetime.datetime.now()]])).astype(np.int64)[0,0]
        if unix_ts - variance_secs > unix_now or unix_ts + variance_secs < unix_now:
            long_ma, short_ma = self.ma_calc(reqId, self.ma_counter + 2000)
            self.ma_counter += 1
            if long_ma > short_ma:
                short_ma_greater_than_long = False
            else:
                short_ma_greater_than_long = True
        else:
            short_ma_greater_than_long = True

        return short_ma_greater_than_long

    @iswrapper
    def ma_calc(self, reqId, ix):
        contract = Contract()
        contract.symbol = self.winners[reqId]
        contract.secType = "STK"
        contract.currency = "USD"
        contract.exchange = "ISLAND"

        self.reqHistoricalData(ix, contract, datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"),
                               "{} S".format(str(self.mas_long_mins * 60)), "{} secs".format(str(self.mas_bar_size_secs)), "MIDPOINT", 1, 1, False, [])
        self.reqHistoricalData(999+ix, contract, datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"),
                               "{} S".format(str(self.mas_short_mins * 60)), "{} secs".format(str(self.mas_bar_size_secs)), "MIDPOINT", 1,
                               1, False, [])
        time.sleep(10)
        fetch = []
        while True:
            try:
                fetch.append(self.hist_data_q.get(False))
            except:
                break
        mas_li = [
                [
                    i[0],
                    i[1].date,
                    i[1].close
                ]
                for i in fetch]
        df = pd.DataFrame(mas_li, columns=['reqId','tm','close'])
        long_ma, short_ma = tuple(df.groupby(['reqId'])['close'].mean())#.sort_values(ascending=False)
        return long_ma, short_ma

    @iswrapper
    def current_price(self, reqId, side):
        if side == 1:
            asc = False
        else:
            asc = True
        current_price = float(self.book[(self.book.reqId == reqId) & (self.book.side == side)].sort(by=['price'], ascending=asc)[['price']].iloc[0][0])
        return current_price

    @iswrapper
    def simulate_marketDepth_init(self, reqId, i):
        position = i
        marketMaker = random.choice(['Q','I','N'])
        side = random.randint(0,1)
        ground = float("{}.{}".format(str(random.randint(3,800)),str(random.randint(0,99))))
        if i==0:
            self.prices = [ground]
            price_range = 16
            for j in range(int(price_range / 2)):
                self.prices.append(ground - float("0.0{}".format(str(j))))
            for k in range(int(price_range / 2)):
                self.prices.append(ground + float("0.0{}".format(str(k))))
            price = random.choice(self.prices)
        else:
            price = random.choice(self.prices)
        size = random.randint(30,10000)
        return [reqId, position, marketMaker, side, price, size]

    @iswrapper
    def maintain_book(self, reqId, position, marketMaker, operation, side, price, size):
        # updates
        if operation == 0:
            self.book.append([[reqId, position, marketMaker, side, price, size]])
            print("ROLAND COMMENT: check if this works")
        elif operation == 1:
            self.book[(self.book.position.reqId == reqId) & (self.book.position == position)] = [reqId, position, marketMaker, side, price, size]
            print("ROLAND COMMENT: check if this works")
        elif operation == 2:
            self.book[(self.book.position.reqId == reqId) & (self.book.position != position)]
            print("ROLAND COMMENT: check if this works")
        #initially
        else:
            # if self.sim_mkt_dpt:
            #     for i in range(self.sim_mkt_pos_rand_n_pos):
            #         self.book.loc[i] = self.simulate_marketDepth_init(reqId, i)
            # else:
            self.book.loc[position] = [reqId, position, marketMaker, side, price, size]

    @iswrapper
    def update_trade_flow(self, reqId, position, marketMaker, operation, side, price, size):
        # buy side
        if reqId not in self.held_reqIds and self.cnt_trades_per_instr_per_day < self.max_trades_per_instr_per_day:
            status = self.make_trade_decision(reqId, 'BUY')
            if status == -1:
                self.cancelMktDepth(reqId)
            elif status == 0:
                #BUY
                self.cnt_trades_per_instr_per_day += 1
        #sell side
        elif reqId in self.held_reqIds:
            status = self.make_trade_decision(reqId, 'SELL')
            if status == -1:
                pass
            elif status == 0:
                #SELL
                self.cnt_trades_per_instr_per_day += 1
        elif datetime.datetime.now().time() > datetime.datetime.strptime("15:{}:00".format(str(30-self.mins_sell_before_eob)), '%H:%M:%S'):
            #SELL
            self.cancelMktDepth(reqId)

    @iswrapper
    # ! [updatemktdepthl2]
    def updateMktDepthL2(self, reqId: TickerId, position: int, marketMaker: str,
                         operation: int, side: int, price: float, size: int):
        super().updateMktDepthL2(reqId, position, marketMaker, operation, side,
                                 price, size)

        print("UpdateMarketDepth. ", reqId, "Position:", position, "Operation:",
              operation, "Side:", side, "Price:", price, "Size", size)

        # self.maintain_book(reqId, position, marketMaker, operation, side, price, size)
        # if self.testing:
        #     print(reqId, marketMaker, price, size)
        #     return
        # self.update_trade_flow(reqId, position, marketMaker, operation, side, price, size)

    # ! [updatemktdepthl2]



    @iswrapper
    # ! [updatemktdepth]
    def updateMktDepth(self, reqId: TickerId, position: int, operation: int,
                       side: int, price: float, size: int):
        super().updateMktDepth(reqId, position, operation, side, price, size)
        print("UpdateMarketDepth. ", reqId, "Position:", position, "Operation:",
              operation, "Side:", side, "Price:", price, "Size", size)
    # ! [updatemktdepth]

    def fetch_cfds(self, ix, symbol, curr):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "CFD"
        contract.currency = curr
        contract.exchange = "SMART"

        self.current_symbol = symbol

        self.reqMktData(ix + 99, contract, "587", snapshot=False, regulatorySnapshot=False,
            mktDataOptions=[])

    def fetch_cse(self, ix, symbol):
        cse = ['CODE', 'JJJ', 'SXX', 'ATT', 'AOC', 'ADX', 'AFI', 'AJN', 'AMS', 'AXC', 'ACG', 'ALQ', 'USGD', 'AHG',
               'AFD', 'API', 'ASTI', 'AG.UN', 'ARQ', 'ARM', 'ARO', 'AREV', 'ASE', 'AKE', 'AUAG', 'AVM', 'BAXS', 'AYL',
               'BAC', 'BE', 'BLGV', 'BBT', 'BKS', 'BXV', 'BIGG', 'CURE', 'BUX', 'PLAY', 'ZRO', 'BDR', 'BRH', 'BIS',
               'TUSK', 'BLIS', 'BXXX', 'BCFN', 'BLK', 'BLOX', 'BLVD', 'BAMM', 'BCA', 'BTH', 'BZI', 'BNKR', 'CXXI',
               'LILY', 'CHV', 'DPC', 'CME', 'CSQ', 'CGOC', 'CGOC.WT', 'BLO', 'CRZ', 'CRZ.WT', 'MTEC', 'CNNX', 'PILL',
               'CPTR', 'CRL', 'CRL.WT', 'OLG', 'CFE', 'CK', 'CAI', 'CMS', 'CUBE', 'CEG', 'CBP', 'CHM', 'CAT', 'CHOO',
               'CMC', 'CIM', 'CNI', 'CXC', 'CGN', 'CZC', 'CBK', 'CBK.WT', 'CROP', 'NITE', 'CRYP', 'CYN', 'DDB', 'DDI',
               'LAN', 'DHC', 'DLMA', 'DVR', 'KDZ', 'DNI', 'DST', 'EA', 'EAC', 'EZM', 'EOM', 'EPW', 'TOP', 'ETI', 'EPY',
               'OPI', 'EI', 'ECU', 'ECU.WT', 'EVI', 'EHC', 'EVA', 'EVG', 'XBLK', 'EX', 'XRO', 'FDM', 'FAT', 'CALI',
               'FNQ', 'FOG', 'FNAU', 'FOX', 'TGIF', 'HUGE', 'FFT', 'NETC', 'GCA', 'GENM', 'GGC', 'GNI', 'GET', 'GET.WT',
               'GTI', 'BLOC', 'BLOC.WT', 'APP', 'GHG', 'LION', 'UAV', 'GCIT', 'GOCO', 'GLR', 'GLH', 'GOR', 'GT', 'MPLS',
               'GPK', 'GRE', 'GFI', 'GFI.DB.A', 'GFI.DB.B', 'GTBE', 'GBC', 'CCR', 'GTII', 'GPC', 'GPC.PR.A', 'HS', 'HP',
               'CANN', 'HGP', 'HC', 'HHS', 'HIKU', 'CYBX', 'SIX', 'HYPR', 'IAN', 'ITV', 'IGN', 'IME', 'IP', 'INR',
               'ISM', 'ICAN', 'IBAT', 'JUJU.A', 'CO', 'IRV', 'ISOL', 'IZO', 'JEM', 'JBR', 'JDF', 'JGW', 'KBB', 'KRI',
               'KOT', 'KBEV', 'KNR', 'ZNK', 'KWG', 'KWG.A', 'LAI', 'LEAD', 'LLL', 'LLP', 'LEGN', 'LEO', 'EPIC', 'LXX',
               'LNB', 'LHS', 'LIB', 'LDS', 'LVI', 'BUDD', 'LOTO', 'J', 'MDD', 'MKNA', 'BBN.DB.B', 'BBN.DB.C',
               'BBN.DB.D', 'MHL.DB.B', 'MHL.DB.D', 'MHL.DB.C', 'BMB.DB.A', 'BMB.DB.B', 'BMB.DB.D', 'BMB.DB.C', 'MDM',
               'MDM.WT', 'MHY.UN', 'MMF.UN', 'MARI', 'MMJ', 'MVT', 'MAY', 'MCL', 'MEC', 'MMEN', 'NSAU', 'MMI', 'XMG',
               'XMG.WT', 'XMG.WT.A', 'XMG.WT.B', 'MRM', 'MWM', 'STV', 'MIRL', 'MIT.DB.C', 'MONT', 'MIS', 'MOG', 'MY',
               'MLK', 'MPV', 'MPX', 'MYM', 'MYR', 'NSHS', 'NVG', 'SUV', 'NC', 'NF', 'NJMC', 'LUX', 'NP', 'NTM', 'NXU',
               'NHS', 'NSM', 'NOM', 'NVS', 'NUR', 'EAT', 'OWLI', 'OSH', 'OAA', 'OPC', 'URG', 'ORTH', 'BOLT', 'COPR',
               'PKG', 'PRL', 'PSE', 'PGOL', 'PKK', 'PMC', 'OIL', 'PCE.UN', 'VIDA', 'VIDA.WT', 'PIVT', 'PVOT', 'NPT',
               'PLTH', 'PTX', 'PDTI', 'PDH', 'PHGI', 'PREV', 'PRIM', 'PRI', 'PAU', 'PDO', 'PUF', 'QCC', 'QBOT', 'QCA',
               'QMI', 'RGO', 'RQB', 'RQB.WT', 'RZR', 'RELA', 'RNG', 'RFR', 'RIN', 'RVR', 'RISE', 'RLSC', 'RWI', 'RIW',
               'RZX', 'RXM', 'RKS', 'SV', 'SBD', 'SHV', 'SRS', 'SHRC', 'SHP', 'SP', 'SIG', 'SXTY', 'EASY', 'SPO', 'SPR',
               'SQR', 'SX', 'SNA', 'STX', 'JOB', 'SQX', 'SAAS', 'SNN', 'ABJ', 'SYDF', 'TGC', 'TAK', 'TAI', 'TTX', 'TCI',
               'TCI.RT', 'TN', 'TER', 'THC', 'TNY', 'IDK', 'TLP.UN', 'TPS', 'TO', 'TO.WT', 'TOKI', 'MJ', 'UTL', 'UPCO',
               'UP', 'URB', 'URB.A', 'VGW', 'VCT', 'VRT', 'VS', 'NI', 'VST', 'VIN', 'VAI', 'VP', 'VGO', 'VGO.DB', 'WAB',
               'WEI', 'RLG', 'WST', 'WUC', 'SUN', 'WGC', 'WRW', 'WSM', 'XTHC', 'XRX', 'ZRI', 'ZTE']
        contract = Contract()
        for ix, c in enumerate(cse[0:99]):
            self.fetch_cse(ix, c)
            contract.symbol = symbol
            contract.secType = "STK"
            contract.currency = "CAD"
            contract.exchange = "SMART"

            self.current_symbol = contract.symbol

            self.reqMktData(ix + 99, contract, "", snapshot=False, regulatorySnapshot=False,
                            mktDataOptions=[])

    def fetch_island(self):
        island = ['PIH', 'TURN', 'FLWS', 'FCCY', 'SRCE', 'VNET', 'TWOU', 'JOBS', 'CAFD', 'EGHT', 'AVHI', 'SHLM', 'AAON',
                  'ABAX',
                  'ABEO', 'ABEOW', 'ABIL', 'ABMD', 'AXAS', 'ACIU', 'ACIA', 'ACTG', 'ACHC', 'ACAD', 'ACST', 'AXDX',
                  'XLRN', 'ANCX',
                  'ARAY', 'ACRX', 'ACET', 'AKAO', 'ACHN', 'ACIW', 'ACRS', 'ACNB', 'ACOR', 'SQZZ', 'ATVI', 'ACTA',
                  'ACXM', 'ADMS',
                  'ADMP', 'ADAP', 'ADUS', 'AEY', 'IOTS', 'ADMA', 'ADBE', 'ADOM', 'ADTN', 'ADRO', 'AAAP', 'ADES', 'AEIS',
                  'AMD',
                  'ADXS', 'ADXSW', 'ADVM', 'AEGN', 'AGLE', 'AEHR', 'AMTX', 'AERI', 'AVAV', 'AEZS', 'AEMD', 'GNMX',
                  'AFMD', 'AGEN',
                  'AGRX', 'AGYS', 'AGIO', 'AGNC', 'AGNCB', 'AGNCP', 'AGFS', 'AGFSW', 'ALRN', 'AIMT', 'AIRT', 'ATSG',
                  'AIRG', 'AMCN',
                  'AKAM', 'AKTX', 'AKCA', 'AKBA', 'AKER', 'AKRX', 'AKTS', 'ALRM', 'ALSK', 'AMRI', 'ALBO', 'ABDC',
                  'ADHD', 'ALDR',
                  'ALDX', 'ALXN', 'ALCO', 'ALGN', 'ALIM', 'ALJJ', 'ALKS', 'ABTX', 'ALGT', 'AIQ', 'AHGP', 'AMMA', 'ARLP',
                  'AHPI',
                  'AMOT', 'ALQA', 'ALLT', 'MDRX', 'AFAM', 'ALNY', 'AOSL', 'GOOG', 'GOOGL', 'SMCP', 'ATEC', 'SWIN',
                  'AABA', 'ALT',
                  'ASPS', 'AIMC', 'AMAG', 'AMRN', 'AMRK', 'AYA', 'AMZN', 'AMBC', 'AMBCW', 'AMBA', 'AMCX', 'DOX', 'AMDA',
                  'AMED',
                  'UHAL', 'ATAX', 'AMOV', 'AAL', 'ACSF', 'AETI', 'AMNB', 'ANAT', 'AOBC', 'APEI', 'ARII', 'AMRB',
                  'AMSWA', 'AMSC',
                  'AMWD', 'CRMT', 'ABCB', 'AMSF', 'ASRV', 'ASRVP', 'ATLO', 'AMGN', 'FOLD', 'AMKR', 'AMPH', 'IBUY',
                  'ASYS', 'AFSI',
                  'AMRS', 'ADI', 'ALOG', 'ANAB', 'AVXL', 'ANCB', 'ANDA', 'ANDAR', 'ANDAU', 'ANDAW', 'ANGI', 'ANGO',
                  'ANIP',
                  'ANIK', 'ANSS', 'ATRS', 'ANTH', 'ABAC', 'APOG', 'APEN', 'AINV', 'APPF', 'APPN', 'AAPL', 'ARCI',
                  'APDN',
                  'APDNW', 'AGTC', 'AMAT', 'AAOI', 'AREX', 'APTI', 'APRI', 'APVO', 'APTO', 'AQMS', 'AQB', 'AQXP',
                  'ARDM',
                  'ARLZ', 'PETX', 'ABUS', 'ARCW', 'ABIO', 'RKDA', 'ARCB', 'ACGL', 'ACGLP', 'APLP', 'ARDX', 'ARNA',
                  'ARCC',
                  'ARGX', 'AGII', 'AGIIL', 'ARGS', 'ARIS', 'ARKR', 'ARTX', 'ARQL', 'ARRY', 'ARRS', 'DWAT', 'AROW',
                  'ARWR',
                  'ARTNA', 'ARTW', 'ASBB', 'ASNA', 'ASND', 'ASCMA', 'APWC', 'ASML', 'AZPN', 'ASMB', 'ASFI', 'ASTE',
                  'ATRO',
                  'ALOT', 'ASTC', 'ASUR', 'ASV', 'ATAI', 'ATRA', 'ATHN', 'ATNX', 'ATHX', 'AAPC', 'AAME', 'ACBI', 'ACFC',
                  'ABY',
                  'ATLC', 'AAWW', 'AFH', 'AFHBL', 'TEAM', 'ATNI', 'ATOM', 'ATOS', 'ATRC', 'ATRI', 'ATTU', 'LIFE',
                  'AUBN', 'BOLD',
                  'AUDC', 'AUPH', 'EARS', 'ABTL', 'ADSK', 'ADP', 'AVDL', 'ATXI', 'AVEO', 'AVXS', 'AVNW', 'AVID', 'AVGR',
                  'AVIR',
                  'CAR', 'AHPA', 'AHPAU', 'AHPAW', 'AWRE', 'AXAR', 'AXARU', 'AXARW', 'ACLS', 'AXGN', 'AAXN', 'AXSM',
                  'AXTI',
                  'AZRX', 'BCOM', 'RILY', 'RILYL', 'RILYZ', 'BOSC', 'BIDU', 'BCPC', 'BWINA', 'BWINB', 'BLDP', 'BANF',
                  'BANFP',
                  'BCTF', 'BKMU', 'BOCH', 'BMRC', 'BMLP', 'BKSC', 'BOTJ', 'OZRK', 'BFIN', 'BWFG', 'BANR', 'BZUN',
                  'TAPR', 'BHAC',
                  'BHACR', 'BHACU', 'BHACW', 'BBSI', 'BSET', 'BYBK', 'BV', 'BCBP', 'BECN', 'BSF', 'BBGI', 'BEBE',
                  'BBBY', 'BGNE',
                  'BELFA', 'BELFB', 'BLPH', 'BLCM', 'BNCL', 'BNFT', 'BNTC', 'BNTCW', 'BYSI', 'BGCP', 'BGFV', 'BASI',
                  'ORPN',
                  'BIOC', 'BCRX', 'BDSI', 'BIIB', 'BIOL', 'BLFS', 'BLRX', 'BMRN', 'BMRA', 'BVXV', 'BVXVW', 'BPTH',
                  'BIOP',
                  'BIOS', 'BBC', 'BBP', 'BSTC', 'BSTG', 'BSPM', 'TECH', 'BEAT', 'BIVV', 'BCACU', 'BJRI', 'BBOX', 'BDE',
                  'BLKB',
                  'BBRY', 'HAWK', 'BL', 'BKCC', 'ADRA', 'ADRD', 'ADRE', 'ADRU', 'BLMN', 'BCOR', 'BLBD', 'BUFF', 'BHBK',
                  'BLUE',
                  'BKEP', 'BKEPP', 'BPMC', 'ITEQ', 'BMCH', 'BOBE', 'BOFI', 'BOFIL', 'WIFI', 'BOJA', 'BOKF', 'BOKFL',
                  'BNSO',
                  'BOMN', 'BPFH', 'BPFHP', 'BPFHW', 'EPAY', 'BLVD', 'BLVDU', 'BLVDW', 'BCLI', 'BBRG', 'BDGE', 'BLIN',
                  'BRID',
                  'BCOV', 'AVGO', 'BSFT', 'BVSN', 'BYFC', 'BWEN', 'BRCD', 'BRKL', 'BRKS', 'BRKR', 'BMTC', 'BLMT',
                  'BSQR', 'BWLD',
                  'BLDR', 'BMLA', 'BUR', 'CFFI', 'CHRW', 'CA', 'CCMP', 'CDNS', 'CDZI', 'CACQ', 'CZR', 'CSTE', 'PRSS',
                  'CLBS',
                  'CHY', 'CHI', 'CCD', 'CHW', 'CGO', 'CSQ', 'CAMP', 'CVGW', 'CFNB', 'CALA', 'CALD', 'CALM', 'CLMT',
                  'ABCD',
                  'CAC', 'CAMT', 'CSIQ', 'CGIX', 'CPHC', 'CPLA', 'CBF', 'CCBG', 'CPLP', 'CSWC', 'CPTA', 'CPTAG',
                  'CPTAL',
                  'CFFN', 'CAPR', 'CSTR', 'CPST', 'CARA', 'CARB', 'CCN', 'CRME', 'CSII', 'CATM', 'CDNA', 'CECO', 'CTRE',
                  'CARO', 'CART', 'CRZO', 'TAST', 'CRTN', 'CARV', 'CASM', 'CASC', 'CWST', 'CASY', 'CASI', 'CASS',
                  'CATB',
                  'CBIO', 'CPRX', 'CATS', 'CATY', 'CATYW', 'CVCO', 'CAVM', 'CBFV', 'CBAK', 'CBOE', 'CDK', 'CDW', 'CECE',
                  'CELG', 'CELGZ', 'CLDX', 'APOP', 'APOPW', 'CLRB', 'CLRBW', 'CLRBZ', 'CLLS', 'CBMG', 'CLSN', 'CELH',
                  'CYAD'
            , 'CEMP', 'CETX', 'CETXP', 'CETXW', 'CDEV', 'CSFL', 'CETV', 'CFBK', 'CENT', 'CENTA', 'CVCY', 'CENX', 'CNBKA'
            , 'CNTY', 'CRNT', 'CERC', 'CERCW', 'CERN', 'CERU', 'CERS', 'KOOL', 'CEVA', 'CFCO', 'CFCOU', 'CFCOW', 'CSBR',
                  'CYOU', 'HOTR', 'CTHR', 'GTLS', 'CHTR', 'CHFN', 'CHKP', 'CHEK', 'CHEKW', 'CKPT', 'CEMI', 'CHFC',
                  'CCXI',
                  'CHMG', 'CHKE', 'CHFS', 'CHMA', 'PLCE', 'CMRX', 'CADC', 'CALI', 'CAAS', 'CBPO', 'CCCL', 'CCCR',
                  'CCRC',
                  'JRJC', 'HGSH', 'CNIT', 'CJJD', 'CLDC', 'HTHT', 'CHNR', 'CREG', 'CNTF', 'CXDC', 'CCIH', 'CNET',
                  'IMOS', 'CDXC',
                  'CHSCL', 'CHSCM', 'CHSCN', 'CHSCO', 'CHSCP', 'CHDN', 'CHUY', 'CDTX', 'CMCT', 'CMPR', 'CINF', 'CIDM',
                  'CTAS',
                  'CRUS', 'CSCO', 'CTRN', 'CZNC', 'CZWI', 'CZFC', 'CIZN', 'CTXS', 'CHCO', 'CIVB', 'CIVBP', 'CDTI',
                  'CLNE', 'CLNT',
                  'CACG', 'YLDE', 'LRGE', 'CLFD', 'CLRO', 'CLSD', 'CLIR', 'CLIRW', 'CBLI', 'CSBK', 'CLVS', 'CMFN',
                  'CME', 'CCNE',
                  'CWAY', 'COBZ', 'COKE', 'CDXS', 'CODX', 'CVLY', 'JVA', 'CCOI', 'CGNT', 'COGT', 'CGNX', 'CTSH', 'COHR',
                  'CHRS',
                  'COHU', 'CLCT', 'COLL', 'CIGI', 'CBAN', 'COLB', 'COLM', 'CMCO', 'CBMX', 'CBMXW', 'CMCSA', 'CBSH',
                  'CBSHP',
                  'CUBN', 'CHUBA', 'CHUBK', 'CVGI', 'COMM', 'JCS', 'ESXB', 'CFBI', 'CYHHZ', 'CTBI', 'CWBC', 'CVLT',
                  'CGEN',
                  'CPSI', 'CTG', 'CHCI', 'CMTL', 'CNAT', 'CNCE', 'CXRX', 'CCUR', 'CDOR', 'CFMS', 'CNFR', 'CNMD', 'CTWS',
                  'CNOB', 'CNXR', 'CONN', 'CNSL', 'CWCO', 'CNACU', 'CPSS', 'CFRX', 'CTRV', 'CTRL', 'CPAA', 'CPAAU',
                  'CPAAW',
                  'CPRT', 'CRBP', 'CORT', 'CORE', 'CORI', 'CSOD', 'CRVL', 'CRVS', 'CSGP', 'COST', 'CPAH', 'ICBK',
                  'COUP',
                  'CVTI', 'COVS', 'COWN', 'COWNL', 'PMTS', 'CPSH', 'CRAI', 'CBRL', 'BREW', 'CRAY', 'CACC', 'USOI',
                  'CREE',
                  'CRESY', 'CRSP', 'CRTO', 'CROX', 'CCRN', 'CRDS', 'CRWS', 'CYRX', 'CYRXW', 'CSGS', 'CCLP', 'CSPI',
                  'CSWI',
                  'CSX', 'CTIC', 'CTIB', 'CTRP', 'CUNB', 'CUI', 'CPIX', 'CMLS', 'CRIS', 'CUTR', 'CVBF', 'CVV', 'CYAN',
                  'CYBR', 'CYBE', 'CYCC', 'CYCCP', 'CBAY', 'CY', 'CYRN', 'CONE', 'CYTK', 'CTMX', 'CYTX', 'CYTXW',
                  'CTSO', 'CYTR', 'DJCO', 'DAKT', 'DRIO', 'DRIOW', 'DZSI', 'DSKE', 'DSKEW', 'DAIO', 'DWCH', 'PLAY',
                  'DTEA', 'DFNL', 'DUSA', 'DWLD', 'DWSN', 'DBVT', 'DFRG', 'TACO', 'TACOW', 'DCTH', 'DMPI', 'DGAS',
                  'DELT', 'DELTW', 'DENN', 'XRAY', 'DEPO', 'DERM', 'DEST', 'DXLG', 'DSWL', 'DTRM', 'DXCM', 'DXTR',
                  'DHXM', 'DHIL', 'FANG', 'DCIX', 'DRNA', 'DFBG', 'DFFN', 'DGII', 'DGLT', 'DMRC', 'DRAD', 'DGLY',
                  'APPS', 'DCOM', 'DMTX', 'DIOD', 'DISCA', 'DISCB', 'DISCK', 'DISH', 'DVCR', 'SAUC', 'DLHC', 'BOOM',
                  'DNBF', 'DLTR', 'DGICA', 'DGICB', 'DMLP', 'DORM', 'EAGL', 'EAGLU', 'EAGLW', 'DOVA', 'DRWI', 'DRYS',
                  'DSPG', 'DLTH', 'DNKN', 'DRRX', 'DXPE', 'DYSL', 'DYNT', 'DVAX', 'ETFC', 'EBMT', 'EGBN', 'EGLE',
                  'EGRX', 'EWBC', 'EACQ', 'EACQU', 'EACQW', 'EML', 'EVGBC', 'EVSTC', 'EVLMC', 'EBAY', 'EBAYL', 'EBIX',
                  'ELON', 'ECHO', 'SATS', 'EEI', 'ESES', 'EDAP', 'EDGE', 'EDGW', 'EDIT', 'EDUC', 'EGAN', 'EGLT', 'EHTH',
                  'EIGR', 'EKSO', 'LOCO', 'EMITF', 'ESLT', 'ERI', 'ESIO', 'EA', 'EFII', 'ELSE', 'ELEC', 'ELECU',
                  'ELECW', 'EBIO', 'DWAC', 'ESBK', 'ELTK', 'EMCI', 'EMCF', 'EMKR', 'EMMS', 'NYNY', 'ENTA', 'ECPG',
                  'WIRE', 'ENDP', 'ECYT', 'ELGX', 'NDRA', 'NDRAW', 'EIGI', 'WATT', 'EFOI', 'ERII', 'EXXI', 'ENOC',
                  'ENG', 'ENPH', 'ESGR', 'ENFC', 'ENTG', 'ENTL', 'ETRM', 'EBTC', 'EFSC', 'ENZY', '', '', '', '', '', '',
                  '', '', '', 'EPZM', 'PLUS', 'EQIX', 'EQFN', 'EQBK', 'ERIC', 'ERIE', 'ESCA', 'ESPR', 'ESQ', 'ESSA',
                  'EPIX', 'ESND', 'ETSY', 'CLWT', 'EEFT', 'ESEA', 'EVEP', 'EVBG', 'EVK', 'MRAM', 'EVLV', 'EVGN', 'EVOK',
                  'EVOL', 'EXA', 'EXAS', 'EXAC', 'EXEL', 'EXFO', 'EXLS', 'EXPE', 'EXPD', 'EXPO', 'ESRX', 'XOG', 'EXTR',
                  'EYEG', 'EYEGW', 'EZPW', 'FFIV', 'FB', 'FRP', 'FALC', 'DAVE', 'FANH', 'FARM', 'FMAO', 'FFKT', 'FMNB',
                  'FARO', 'FAST', 'FATE', 'FBSS', 'FNHC', 'FHCO', 'GSM', 'FCSC', 'FGEN', 'ONEQ', 'LION', 'FDUS', 'FRGI',
                  'FSAM', 'FSC', 'FSCFL', 'FSFR', 'FITB', 'FITBI', 'FNGN', 'FISI', 'FNSR', 'FNJN', 'FNTE', 'FNTEU',
                  'FNTEW', 'FEYE', 'FBNC', 'FNLC', 'FRBA', 'BUSE', 'FBIZ', 'FCAP', 'FCFS', 'FCNCA', 'FCBC', 'FCCO',
                  'FCFP', 'FBNK', 'FDEF', 'FFBC', 'FFBCW', 'FFIN', 'THFF', 'FFNW', 'FFWM', 'FGBI', 'FHB', 'INBK',
                  'INBKL', 'FIBK', 'FRME', 'FMBH', 'FMBI', 'FNWB', 'FSFG', 'FSLR', 'FSBK', 'FAAR', 'FPA', 'BICK', 'FBZ',
                  'FCAL', 'FCAN', 'FTCS', 'FCEF', 'FCA', 'SKYY', 'RNDM', 'FDT', 'FDTS', 'FVC', 'FV', 'IFV', 'FEM',
                  'RNEM', 'FEMB', 'FEMS', 'FTSM', 'FEP', 'FEUZ', 'FGM', 'FTGC', 'FTHI', 'HYLS', 'FHK', 'FTAG', 'FTRI',
                  'FPXI', 'YDIV', 'FJP', 'FEX', 'FTC', 'RNLC', 'FTA', 'FLN', 'FTLB', 'LMBS', 'FMB', 'FMK', 'FNX', 'FNY',
                  'RNMC', 'FNK', 'FAD', 'FAB', 'MDIV', 'MCEF', 'QABA', 'FTXO', 'QCLN', 'GRID', 'CIBR', 'FTXG', 'CARZ',
                  'FTXN', 'FTXH', 'FTXD', 'FTXL', 'FONE', 'TDIV', 'FTXR', 'QQEW', 'QQXT', 'QTEC', 'AIRR', 'QINC',
                  'RDVY', 'RFAP', 'RFDI', 'RFEM', 'RFEU', 'FTSL', 'FYX', 'FYC', 'RNSC', 'FYT', 'FKO', 'FCVT', 'FDIV',
                  'FSZ', 'FTW', 'FIXD', 'TUSA', 'FKU', 'RNDV', 'FUNC', 'FUSB', 'SVVC', 'FSV', 'FISV', 'FIVE', 'FPRX',
                  'FVE', 'FIVN', 'FLEX', 'FLKS', 'FLXN', 'SKOR', 'LKOR', 'MBSD', 'ASET', 'ESGG', 'ESG', 'QLC', 'FPAY',
                  'FLXS', 'FLIR', 'FLDM', 'FFIC', 'FNBG', 'FOMX', 'FOGO', 'FONR', 'FRSX', 'FH', 'FORM', 'FORTY', 'FORR',
                  'FRTA', 'FTNT', 'FBIO', 'FMCI', 'FMCIR', 'FMCIU', 'FMCIW', 'FWRD', 'FORD', 'FWP', 'FOSL', 'FMI',
                  'FOXF', 'FRAN', 'FELE', 'FKLYU', 'FRED', 'RAIL', 'FEIM', 'FRPT', 'FTEO', 'FTR', 'FTRPR', 'FRPH',
                  'FSBW', 'FSBC', 'FTD', 'FTEK', 'FCEL', 'FLGT', 'FORK', 'FLL', 'FULT', 'FSNN', 'FTFT', 'FFHL', 'WILC',
                  'GTHX', 'FOANC', 'MOGLC', 'GAIA', 'GLPG', 'GALT', 'GALE', 'GLMD', 'GLPI', 'GPIC', 'GRMN', 'GARS',
                  'GDS', 'GEMP', 'GENC', 'GNCMA', 'GFN', 'GFNCP', 'GFNSL', 'GENE', 'GNUS', 'GNMK', 'GNCA', 'GHDX',
                  'GNTX', 'THRM', 'GEOS', 'GABC', 'GERN', 'GEVO', 'ROCK', 'GIGM', 'GIGA', 'GIII', 'GILT', 'GILD',
                  'GBCI', 'GLAD', 'GLADO', 'GOOD', 'GOODM', 'GOODO', 'GOODP', 'GAIN', 'GAINM', 'GAINN', 'GAINO', 'LAND',
                  'LANDP', 'GLBZ', 'GBT', 'GLBR', 'ENT', 'GBLI', 'GBLIL', 'GBLIZ', 'GPAC', 'GPACU', 'GPACW', 'SELF',
                  'GSOL', 'GWRS', 'KRMA', 'FINX', 'ACTX', 'BFIT', 'SNSR', 'LNGR', 'MILN', 'EFAS', 'QQQC', 'BOTZ',
                  'CATH', 'SOCL', 'ALTY', 'SRET', 'YLCO', 'GLBS', 'GLUU', 'GLYC', 'GOGO', 'GLNG', 'GMLP', 'GDEN',
                  'GOGL', 'GBDC', 'GTIM', 'GPRO', 'GSHT', 'GSHTU', 'GSHTW', 'GOV', 'GOVNI', 'GPIA', 'GPIAU', 'GPIAW',
                  'LOPE', 'GRVY', 'FULLL', 'GECC', 'GEC', 'GLDD', 'GSBC', 'GNBC', 'GRBK', 'GPP', 'GPRE', 'GCBC', 'GLRE',
                  'GSUM', 'GRIF', 'GRFS', 'GRPN', 'OMAB', 'GGAL', 'GSIT', 'GSVC', 'GTXI', 'GTYH', 'GTYHU', 'GTYHW',
                  'GBNK', 'GNTY', 'GFED', 'GUID', 'GIFI', 'GURE', 'GPOR', 'GWPH', 'GWGH', 'GYRO', 'HEES', 'HLG', 'HNRG',
                  'HALL', 'HALO', 'HBK', 'HLNE', 'HBHC', 'HBHCL', 'HNH', 'HAFC', 'HQCL', 'HONE', 'HDNG', 'HLIT', 'HRMN',
                  'HRMNU', 'HRMNW', 'HBIO', 'HCAP', 'HCAPL', 'HAS', 'HA', 'HCOM', 'HWKN', 'HWBK', 'HAYN', 'HDS', 'HIIQ',
                  'HCSG', 'HQY', 'HSTM', 'HTLD', 'HTLF', 'HTBX', 'HEBT', 'HSII', 'HELE', 'HMNY', 'HMTV', 'HNNA', 'HSIC',
                  'HTBK', 'HFWA', 'HCCI', 'MLHR', 'HRTX', 'HSKA', 'HIBB', 'SNLN', 'HPJ', 'HIHO', 'HIMX', 'HIFS', 'HSGX',
                  'HMNF', 'HMSY', 'HOLI', 'HOLX', 'HBCP', 'HOMB', 'HFBL', 'HMST', 'HMTA', 'HTBI', 'HOFT', 'HOPE',
                  'HFBC', 'HBNC', 'HZNP', 'HRZN', 'DAX', 'QYLD', 'HDP', 'HPT', 'TWNK', 'TWNKW', 'HMHC', 'HWCC', 'HOVNP',
                  'HBMD', 'HSNI', 'HTGM', 'HUBG', 'HSON', 'HDSN', 'HUNT', 'HUNTU', 'HUNTW', 'HBAN', 'HBANN', 'HBANO',
                  'HBANP', 'HURC', 'HURN', 'HCM', 'HBP', 'HVBC', 'HYGS', 'IDSY', 'IAC', 'IBKC', 'IBKCO', 'IBKCP',
                  'ICAD', 'IEP', 'ICCH', 'ICFI', 'ICHR', 'ICLR', 'ICON', 'ICUI', 'IPWR', 'INVE', 'IDRA', 'IDXX', 'IESC',
                  'IROQ', 'IFMK', 'RXDX', 'INFO', 'IIVI', 'KANG', 'IKNX', 'ILG', 'ILMN', 'ISNS', 'IMMR', 'ICCC', 'IMDZ',
                  'IMNP', '', '', '', '', '', '', '', '', '', 'IMGN', 'IMMU', 'IMRN', 'IMRNW', 'IPXL', 'IMPV', 'PI',
                  'IMMY', 'INCR', 'INCY', 'INDB', 'IBCP', 'IBTX', 'IDSA', 'INFN', 'INFI', 'IPCC', 'III', 'IFON',
                  'IMKTA', 'INWK', 'INNL', 'INOD', 'IPHS', 'IOSP', 'ISSC', 'INVA', 'INGN', 'ITEK', 'INOV', 'INO',
                  'INPX', 'INSG', 'NSIT', 'ISIG', 'INSM', 'INSE', 'IIIN', 'PODD', 'INSY', 'NTEC', 'IART', 'IDTI',
                  'INTC', 'NTLA', 'IPCI', 'IPAR', 'IBKR', 'ICPT', 'IDCC', 'TILE', 'LINK', 'IMI', 'INAP', 'IBOC', 'ISCA',
                  'IGLD', 'IIJI', 'IDXG', 'XENT', 'INTX', 'IVAC', 'INTL', 'ITCI', 'IIN', 'INTU', 'ISRG', 'SNAK', 'ISTR',
                  'ISBC', 'ITIC', 'NVIV', 'IVTY', 'IONS', 'IOVA', 'IPAS', 'DTYS', 'DTYL', 'DTUS', 'DTUL', 'DFVS',
                  'DFVL', 'FLAT', 'DLBS', 'DLBL', 'STPP', 'IPGP', 'CSML', 'IRMD', 'IRTC', 'IRIX', 'IRDM', 'IRDMB',
                  'IRBT', 'IRWD', 'IRCP', 'PMPT', 'SLQD', 'TLT', 'AIA', 'COMT', 'IXUS', 'FALN', 'IFEU', 'IFGL', 'IGF',
                  'GNMA', 'HYXE', 'JKI', 'ACWX', 'ACWI', 'AAXJ', 'EWZS', 'MCHI', 'ESGD', 'SCZ', 'ESGE', 'EEMA', 'EUFN',
                  'IEUS', 'MPCT', 'ENZL', 'QAT', 'UAE', 'ESGU', 'IBB', 'SOXX', 'EMIF', 'ICLN', 'WOOD', 'INDY', 'ISHG',
                  'IGOV', 'ISRL', 'ITI', 'ITRI', 'ITRN', 'ITUS', 'IVENC', 'IVFGC', 'IVFVC', 'IXYS', 'IZEA', 'JJSF',
                  'MAYS', 'JBHT', 'JCOM', 'JASO', 'JKHY', 'JACK', 'JXSB', 'JAGX', 'JAKK', 'JMBA', 'JRVR', 'SGQI',
                  'JSML', 'JSMD', 'JASN', 'JASNW', 'JAZZ', 'JD', 'JSYN', 'JSYNR', 'JSYNU', 'JSYNW', 'JBLU', 'JTPY',
                  'JCTCF', 'WYIG', 'WYIGU', 'WYIGW', 'JMU', 'JBSS', 'JOUT', 'JNCE', 'JNP', 'JUNO', 'KTWO', 'KALU',
                  'KALV', 'KMDA', 'KNDI', 'KPTI', 'KAAC', 'KAACU', 'KAACW', 'KBLM', 'KBLMR', 'KBLMU', 'KBLMW', 'KBSF',
                  'KCAP', 'KRNY', 'KELYA', 'KELYB', 'KMPH', 'KFFB', 'KERX', 'KEQU', 'KTEC', 'KTCC', 'KFRC', 'KE',
                  'KBAL', 'KIN', 'KGJI', 'KINS', 'KONE', 'KNSL', 'KIRK', 'KITE', 'KTOV', 'KTOVW', 'KLAC', 'KLXI',
                  'KONA', 'KOPN', 'KRNT', 'KOSS', 'KWEB', 'KTOS', 'KLIC', 'KURA', 'KVHI', 'FSTR', 'LJPC', 'LSBK',
                  'LBAI', 'LKFN', 'LAKE', 'LRCX', 'LAMR', 'LANC', 'LCA', 'LCAHU', 'LCAHW', 'LNDC', 'LARK', 'LMRK',
                  'LMRKO', 'LMRKP', 'LE', 'LSTR', 'LNTH', 'LTRX', 'LSCC', 'LAUR', 'LAWS', 'LAYN', 'LCNB', 'LBIX',
                  'LPTX', 'LGCY', 'LGCYO', 'LGCYP', 'LTXB', 'DDBI', 'EDBI', 'INFR', 'LVHD', 'UDBI', 'LMAT', 'TREE',
                  'LXRX', 'LGIH', 'LHCG', 'LLIT', 'LBRDA', 'LBRDK', 'LEXEA', 'LEXEB', 'LBTYA', 'LBTYB', 'LBTYK', 'LILA',
                  'LILAK', 'LVNTA', 'LVNTB', 'QVCA', 'QVCB', 'BATRA', 'BATRK', 'FWONA', 'FWONK', 'LSXMA', 'LSXMB',
                  'LSXMK', 'TAX', 'LTRPA', 'LTRPB', 'LPNT', 'LCUT', 'LFVN', 'LWAY', 'LGND', 'LTBR', 'LPTH', 'LLEX',
                  'LMB', 'LLNW', 'LMNR', 'LINC', 'LECO', 'LIND', 'LINDW', 'LINU', 'LPCN', 'LQDT', 'LFUS', 'LIVN', 'LOB',
                  'LIVE', 'LPSN', 'LKQ', 'LMFA', 'LMFAW', 'LOGI', 'LOGM', 'EVAR', 'CNCR', 'LONE', 'LTEA', 'LORL',
                  'LOXO', 'LPLA', 'LRAD', 'LYTS', 'LULU', 'LITE', 'LMNX', 'LMOS', 'LUNA', 'MBTF', 'MACQ', 'MACQU',
                  'MACQW', 'MIII', 'MIIIU', 'MIIIW', 'MBVX', 'MCBC', 'MFNC', 'MTSI', 'MGNX', 'MDGL', 'MAGS', 'MGLN',
                  'MGIC', 'CALL', 'MNGA', 'MGYR', 'MHLD', 'MSFG', 'MMYT', 'MBUU', 'MLVF', 'MAMS', 'TUSK', 'MANH',
                  'LOAN', 'MNTX', 'MTEX', 'MNKD', 'MANT', 'MARA', 'MCHX', 'MARPS', 'MRNS', 'MKTX', 'MRLN', 'MAR',
                  'MBII', 'MRTN', 'MMLP', 'MRVL', 'MASI', 'MTCH', 'MTLS', 'MPAC', 'MPACU', 'MPACW', 'MTRX', 'MAT',
                  'MATR', 'MATW', 'MXIM', 'MXPT', 'MXWL', 'MZOR', 'MBFI', 'MBFIP', 'MCFT', 'MGRC', 'MDCA', 'MFIN',
                  'MFINL', 'MTBC', 'MTBCP', 'MNOV', 'MDSO', 'MDGS', 'MDWD', 'MDVX', 'MDVXW', 'MEDP', 'MEIP', 'MLCO',
                  'MLNX', 'MELR', 'MTSL', 'MELI', 'MBWM', 'MERC', 'MRCY', 'EBSB', 'VIVO', 'MRDN', 'MRDNW', 'MMSI',
                  'MACK', 'MRSN', 'MSLI', 'MRUS', 'MLAB', 'MESO', 'CASH', 'MEOH', 'MGCD', 'MGEE', 'MGPI', 'MBOT',
                  'MCHP', 'MU', 'MICT', 'MICTW', 'MSCC', 'MSFT', 'MSTR', 'MVIS', 'MPB', 'MTP', 'MCEP', 'MBCN', 'MSEX',
                  'MSBI', 'MOFG', 'MIME', 'MDXG', 'MNDO', 'MB', 'NERV', 'MGEN', 'MRTX', 'MIRN', 'MSON', 'MIND', 'MINDP',
                  'MITK', 'MITL', 'MKSI', 'MMAC', 'MINI', 'MOBL', 'MMDM', 'MMDMR', 'MMDMU', 'MMDMW', 'MLNK', 'MBRX',
                  'MNTA', 'MOMO', 'MCRI', 'MDLZ', 'MGI', 'MPWR', 'TYPE', 'MNRO', 'MRCC', 'MNST', 'MSDI', 'MSDIW',
                  'MORN', 'MOSY', 'MOTA', 'MOTAW', 'MTFB', 'MTFBW', 'MPAA', 'MPVD', 'MOXC', 'MRVC', 'MSBF', 'MSG',
                  'MTGE', 'MTGEP', 'MTSC', 'LABL', 'MFSF', 'MYSZ', 'MYL', 'MYND', 'MYNDW', 'MYOK', 'MYOS', 'MYRG',
                  'MYGN', 'NBRV', 'NAKD', 'NNDM', 'NANO', 'NSTG', 'NH', 'NK', 'NSSC', 'NDAQ', 'NTRA', 'NATH', 'NAUH',
                  'NKSH', 'FIZZ', 'NCMI', 'NCOM', 'NESR', 'NESRW', 'NGHC', 'NGHCN', 'NGHCO', 'NGHCP', 'NGHCZ', 'NHLD',
                  'NHLDW', 'NATI', 'NRCIA', 'NRCIB', 'NSEC', 'NWLI', 'NAII', 'NHTC', 'NATR', 'BABY', 'ISM', 'JSM',
                  'NAVI', 'NBTB', 'NCIT', 'NCSM', 'NKTR', 'NEOG', 'NEO', 'NEON', 'NEOS', 'NEOT', 'NVCN', 'NEPT', 'UEPS',
                  'NETE', 'NTAP', 'NTES', 'NFLX', 'NTGR', 'NLST', 'NTCT', 'NTWK', 'CUR', 'NBIX', 'NDRM', 'NURO',
                  'NUROW', 'NTRP', 'NBEV', 'NYMT', 'NYMTO', 'NYMTP', 'NLNK', 'NWS', 'NWSA', 'NEWS', 'NEWT', 'NEWTL',
                  'NEWTZ', 'NXEO', 'NXEOU', 'NXEOW', 'NXST', 'NVET', 'NFEC', 'NODK', 'EGOV', 'NICE', 'NICK', 'NCBS',
                  'NIHD', 'NVLS', 'NMIH', 'NNBR', 'NDLS', 'NDSN', 'NSYS', 'NBN', 'NTIC', 'NTRS', 'NTRSP', 'NFBK',
                  'NRIM', 'NWBI', 'NWPX', 'NCLH', 'NWFL', 'NVFY', 'NVMI', 'NVDQ', 'NOVN', 'NOVT', 'NVAX', 'NVLN',
                  'NVCR', 'NVGN', 'NVUS', 'NUAN', 'NMRX', 'NTNX', 'NUTR', 'NTRI', 'NUVA', 'NVTR', 'QQQX', 'NVEE',
                  'NVEC', 'NVDA', 'NXPI', 'NXTM', 'NXTD', 'NXTDW', 'NYMX', 'OIIM', 'OVLY', 'OASM', 'OBLN', 'OBSV',
                  'OBCI', 'OPTT', 'ORIG', 'OCFC', 'OCRX', 'OCLR', 'OFED', 'OCUL', 'OMEX', 'ODP', 'OFS', 'OHAI', 'OVBC',
                  'OHRP', 'OKTA', 'ODFL', 'OLBK', 'ONB', 'OPOF', 'OSBC', 'OSBCP', 'OLLI', 'ZEUS', 'OFLX', 'OMER',
                  'OMNT', 'OMCL', 'ON', 'OTIV', 'ONS', 'ONSIW', 'ONSIZ', 'OGXI', 'OMED', 'ONTX', 'ONTXW', 'ONCS',
                  'OHGI', 'ONVI', 'OTEX', 'OPXA', 'OPXAW', 'OPGN', 'OPGNW', 'OPHT', 'OPK', 'OBAS', 'OCC', 'OPHC', 'OPB',
                  'ORMP', 'OSUR', 'ORBC', 'ORBK', 'ORLY', 'OREX', 'ONVO', 'SEED', 'OACQ', 'OACQR', 'OACQU', 'OACQW',
                  'OESX', 'ORIT', 'ORRF', 'OFIX', 'OSIS', 'OSN', 'OTEL', 'OTIC', 'OTTW', 'OTTR', 'OVAS', 'OSTK', 'OVID',
                  'OXBR', 'OXBRW', 'OXFD', 'OXLC', 'OXLCM', 'OXLCN', 'OXLCO', 'PFIN', 'PTSI', 'PCAR', 'PACB', 'PCBK',
                  'PEIX', 'PMBC', 'PPBI', 'PAAC', 'PAACR', 'PAACU', 'PAACW', 'PCRX', 'PACW', 'PTIE', 'PAAS', 'PNRA',
                  'PANL', 'PZZA', 'FRSH', 'PBNC', 'PRTK', 'PRXL', 'PCYG', 'PSTB', 'PKBK', 'PRKR', 'PKOH', 'PTNR',
                  'PBHC', 'PATK', 'PNBK', 'PATI', 'PEGI', 'PDCO', 'PTEN', 'PAVM', 'PAVMW', 'PAYX', 'PCTY', 'PYDS',
                  'PYPL', 'PBBI', 'CNXN', 'PCMI', 'PCSB', 'PCTI', 'PDCE', 'PDFS', 'PDLI', 'PDVW', 'SKIS', 'PGC', 'PEGA',
                  'PCO', 'PENN', 'PVAC', 'PFLT', 'PNNT', 'PWOD', 'PTXP', 'PEBO', 'PEBK', 'PFBX', 'PFIS', 'PBCT',
                  'PBCTP', 'PUB', 'PRCP', 'PPHM', 'PPHMP', 'PRFT', 'PFMT', 'PERF', 'PERI', 'PESI', 'PPIH', 'PTX',
                  'PERY', 'PGLC', 'PETS', 'PFSW', 'PGTI', 'PZRX', 'PHII', 'PHIIK', 'PAHC', 'PHMD', 'PLAB', 'PICO',
                  'PIRS', 'PPC', 'PME', 'PNK', 'PNFP', 'PPSI', 'PXLW', 'PLPM', 'PLYA', 'PLYAW', 'PLXS', 'PLUG', 'PLBC',
                  'PSTI', 'PLXP', 'PBSK', 'PNTR', 'PCOM', 'POLA', 'COOL', 'POOL', 'POPE', 'BPOP', 'BPOPM', 'BPOPN',
                  'PBIB', 'PTLA', 'PBPB', 'PCH', 'POWL', 'POWI', 'PLW', 'PKW', 'PFM', 'PYZ', 'PEZ', 'PSL', 'PIZ', 'PIE',
                  'PXI', 'PFI', 'PTH', 'PRN', 'DWLV', 'PDP', 'DWAQ', 'DWAS', 'DWIN', 'DWTR', 'PTF', 'PUI', 'IDLB',
                  'PRFZ', 'PAGG', 'PSAU', 'PIO', 'PGJ', 'PEY', 'IPKW', 'PID', 'KBWB', 'KBWD', 'KBWY', 'KBWP', 'KBWR',
                  'LDRI', 'LALT', 'PNQI', 'PDBC', 'QQQ', 'USLB', 'PSCD', 'PSCC', 'PSCE', 'PSCF', 'PSCH', 'PSCI', 'PSCT',
                  'PSCM', 'PSCU', 'VRIG', 'PHO', 'PRAA', 'PRAH', 'PRAN', 'PRPO', 'PFBC', 'PLPC', 'PFBI', 'PINC', 'LENS',
                  'PSDO', 'PRGX', 'PSMT', 'PBMD', 'PNRG', 'PRMW', 'PRIM', 'BTEC', 'GENY', 'PSET', 'PY', 'PSC', 'PDEX',
                  'IPDN', 'PFIE', 'PGNX', 'PRGS', 'PFPT', 'PRPH', 'PRQR', 'BIB', 'UBIO', 'TQQQ', 'ZBIO', 'SQQQ', 'BIS',
                  'PSEC', 'PTGX', 'PRTO', 'PTI', 'PRTA', 'PVBC', 'PROV', 'PBIP', 'PSDV', 'PMD', 'PTC', 'PTCT', 'PULM',
                  'PLSE', 'PBYI', 'PCYO', 'IMED', 'FINQ', 'PXS', 'QADA', 'QADB', 'QCRH', 'QGEN', 'QIWI', 'QRVO', 'QCOM',
                  'QSII', 'QBAK', 'QLYS', 'QTNA', 'QTRH', 'QRHC', 'QUIK', 'QDEL', 'QPAC', 'QPACU', 'QPACW', 'QNST',
                  'QUMU', 'QTNT', 'RRD', 'RCM', 'RARX', 'RADA', 'RDCM', 'RSYS', 'RDUS', 'RDNT', 'RDWR', 'METC', 'RMBS',
                  'RAND', 'RLOG', 'GOLD', 'RNDB', 'RPD', 'RAVE', 'RAVN', 'ROLL', 'RICK', 'RCMT', 'RDI', 'RDIB', 'RGSE',
                  'RELY', 'RNWK', 'RP', 'RETA', 'RCON', 'REPH', 'RRGB', 'RRR', 'RDHL', 'REGN', 'RGNX', 'RGLS', 'REIS',
                  'RELV', 'MARK', 'RNST', 'REGI', 'RNVA', 'RNVAZ', 'RCII', 'RTK', 'RGEN', 'RPRX', 'RBCAA', 'FRBK',
                  'REFR', 'RESN', 'RECN', 'ROIC', 'RTRX', 'RVNC', 'RVEN', 'RVLT', 'RWLK', 'REXX', 'RFIL', 'RGCO',
                  'RIBT', 'RIBTW', 'RELL', 'RIGL', 'NAME', 'RNET', 'RTTR', 'RVSB', 'RLJE', 'RMGN', 'ROBO', 'FUEL',
                  'RMTI', 'RCKY', 'RMCF', 'ROKA', 'RTNB', 'ROSE', 'ROSEU', 'ROSEW', 'ROSG', 'ROST', 'RBPAA', 'RGLD',
                  'RPXC', 'RTIX', 'RBCN', 'RUSHA', 'RUSHB', 'RUTH', 'RXII', 'RXIIW', 'RYAAY', 'STBA', 'SANW', 'SCAC',
                  'SCACU', 'SCACW', 'SBRA', 'SBRAP', 'SABR', 'SAEX', 'SAFT', 'SAGE', 'SAIA', 'SAJA', 'SALM', 'SAL',
                  'SAFM', 'SASR', 'SGMO', 'SANM', 'GCVRZ', 'SPNS', 'SRPT', 'SVRA', 'SBFG', 'SBFGP', 'SBAC', 'SCSC',
                  'SMIT', 'SCHN', 'SCHL', 'SCLN', 'SGMS', 'SNI', 'SCYX', 'SEAC', 'SBCF', 'STX', 'SHIP', 'SHIPW', 'SRSC',
                  'SHLD', 'SHLDW', 'SHOS', 'SPNE', 'SGEN', 'EYES', 'EYESW', 'SCWX', 'SNFCA', 'SEIC', 'SLCT', 'SCSS',
                  'SIR', 'SELB', 'SIGI', 'LEDS', 'SMTC', 'SENEA', 'SENEB', 'SNES', 'SNH', 'SNHNI', 'SNHNL', 'SNMX',
                  'SRTS', 'SRTSW', 'SQBG', 'MCRB', 'SREV', 'SFBS', 'SEV', 'SVBI', 'SGBX', 'SGOC', 'SMED', 'SHSP',
                  'SHEN', 'PIXY', 'SHLO', 'TYHT', 'SHPG', 'SCVL', 'SHBI', 'SHOR', 'SSTI', 'SFLY', 'SIFI', 'SIEB',
                  'SIEN', 'BSRR', 'SRRA', 'SWIR', 'SIFY', 'SIGM', 'SGLB', 'SGLBW', 'SGMA', 'SBNY', 'SBNYW', 'SLGN',
                  'SILC', 'SLAB', 'SIMO', 'SPIL', 'SRUN', 'SRUNU', 'SRUNW', 'SSRI', 'SAMG', 'SSNT', 'SFNC', 'SLP',
                  'SINA', 'SBGI', 'SINO', 'SVA', 'SIRI', 'SITO', 'SKYS', 'SKLN', 'SKYW', 'SWKS', 'SLM', 'SLMBP', 'SGH',
                  'SND', 'SMBK', 'SMSI', 'SMTX', 'LNCE', 'SRAX', 'SCKT', 'SODA', 'SOHU', 'SLRC', 'SUNS', 'SEDG', 'SLNO',
                  'SLNOW', 'SNGX', 'SNGXW', 'SONC', 'SOFO', 'SNOA', 'SNOAW', 'SONS', 'SPHS', 'SORL', 'SRNE', 'SOHO',
                  'SOHOB', 'SOHOM', 'SFBC', 'SSB', 'SFST', 'SMBC', 'SONA', 'SBSI', 'OKSB', 'SP', 'SGRP', 'SPKE',
                  'SPKEP', 'ONCE', 'SPAR', 'SPTN', 'DWFI', 'SPPI', 'ANY', 'SPEX', 'SPI', 'SAVE', 'SPLK', 'SPOK', 'SPWH',
                  'SBPH', 'FUND', 'SFM', 'SPSC', 'SSNC', 'STAA', 'STAF', 'STMP', 'STLY', 'SPLS', 'SBLK', 'SBLKL',
                  'SBUX', 'STFC', 'STBZ', 'SNC', 'STDY', 'GASS', 'STLD', 'SMRT', 'STLR', 'STLRU', 'STLRW', 'SBOT',
                  'STML', 'SRCL', 'SRCLP', 'STRL', 'SHOO', 'SSFN', 'SYBT', 'BANX', 'SGBK', 'SSKN', 'SSYS', 'STRT',
                  'STRS', 'STRA', 'STRM', 'SBBP', 'STB', 'SCMP', 'SUMR', 'SMMF', 'SSBI', 'SMMT', 'SNBC', 'SNHY', 'SNDE',
                  'SNSS', 'STKL', 'SPWR', 'RUN', 'SBCP', 'SUNW', 'SMCI', 'SPCB', 'SCON', 'SGC', 'SUPN', 'SPRT', 'SGRY',
                  'SRDX', 'SBBX', 'SIVB', 'SIVBO', 'SYKE', 'SYMC', 'SYNC', 'SYNL', 'SYNA', 'SNCR', 'SNDX', 'SGYP',
                  'ELOS', 'SNPS', 'SYNT', 'SYMX', 'SYPR', 'SYRS', 'TROW', 'TTOO', 'TRHC', 'TCMD', 'TAIT', 'TTWO',
                  'TLND', 'TNDM', 'TLF', 'TANH', 'TPIV', 'TEDU', 'TATT', 'TAYD', 'CGBD', 'TCPC', 'AMTD', 'TEAR', 'TECD',
                  'TCCO', 'TTGT', 'TGLS', 'TGEN', 'TNAV', 'TTEC', 'TLGT', 'TELL', 'TENX', 'GLBL', 'TERP', 'TVIA',
                  'TBNK', 'TSRO', 'TESO', 'TSLA', 'TESS', 'TTEK', 'TTPH', 'TCBI', 'TCBIL', 'TCBIP', 'TCBIW', 'TXN',
                  'TXRH', 'TFSL', 'TGTX', 'ABCO', 'ANDE', 'TBBK', 'BONT', 'CG', 'CAKE', 'CHEF', 'TCFC', 'DSGX', 'DXYN',
                  'ENSG', 'XONE', 'FINL', 'FBMS', 'FLIC', 'GT', 'HABT', 'HCKT', 'HAIN', 'FITS', 'CUBA', 'INTG', 'JYNT',
                  'KEYW', 'KHC', 'OLD', 'MDCO', 'MEET', 'MIK', 'MIDD', 'NAVG', 'SLIM', 'STKS', 'ORG', 'PCLN', 'PRSC',
                  'RMR', 'SPNC', 'TTD', 'ULTI', 'YORW', 'NCTY', 'TRPX', 'TBPH', 'TST', 'TCRD', 'THLD', 'TICC', 'TICCL',
                  'TIG', 'TTS', 'TIL', 'TSBK', 'TNTR', 'TIPT', 'TITN', 'TTNP', 'TVTY', 'TIVO', 'TMUS', 'TMUSP', 'TOCA',
                  'TNXP', 'TISA', 'TOPS', 'TORM', '', '', '', '', '', '', '', '', '', 'TRCH', 'TSEM', 'CLUB', 'TOWN',
                  'TPIC', 'TCON', 'TSCO', 'TWMC', 'TACT', 'TRNS', 'TGA', 'TA', 'TANNI', 'TANNL', 'TANNZ', 'TZOO',
                  'TRVN', 'TCBK', 'TRIL', 'TRS', 'TRMB', 'TRIB', 'TRIP', 'TSC', 'TBK', 'TRVG', 'TRNC', 'TROV', 'TRUE',
                  'THST', 'TRUP', 'TRST', 'TRMK', 'TSRI', 'TTMI', 'TCX', 'TUES', 'TOUR', 'HEAR', 'TUTI', 'TUTT', 'FOX',
                  'FOXA', 'TWIN', 'TRCB', 'USCR', 'PRTS', 'USEG', 'GROW', 'USAU', 'UBNT', 'UFPT', 'ULTA', 'UCTT', 'UPL',
                  'RARE', 'ULBI', 'UMBF', 'UMPQ', 'UNAM', 'UBSH', 'UNB', 'UNXL', 'QURE', 'UBCP', 'UBOH', 'UBSI', 'UCBA',
                  'UCBI', 'UCFC', 'UBNK', 'UFCS', 'UIHC', 'UNFI', 'UBFO', 'USLM', 'UTHR', 'UG', 'UNIT', 'UNTY', 'OLED',
                  'UEIC', 'UFPI', 'ULH', 'USAP', 'UVSP', 'UPLD', 'URRE', 'UONE', 'UONEK', 'URBN', 'URGN', 'ECOL',
                  'USAT', 'USATP', 'USAK', 'UTMD', 'UTSI', 'VLRX', 'VALX', 'VALU', 'VNDA', 'BBH', 'GNRX', 'PPH', 'VWOB',
                  'VNQI', 'VGIT', 'VCIT', 'VIGI', 'VYMI', 'VCLT', 'VGLT', 'VMBS', 'VONE', 'VONG', 'VONV', 'VTWO',
                  'VTWG', 'VTWV', 'VTHR', 'VCSH', 'VGSH', 'VTIP', 'BNDX', 'VXUS', 'VEAC', 'VEACU', 'VEACW', 'VREX',
                  'VRNS', 'VDSI', 'VBLT', 'VBIV', 'WOOF', 'VECO', 'DGLD', 'DSLV', 'UGLD', 'USLV', 'TVIZ', 'TVIX', 'ZIV',
                  'XIV', 'VIIZ', 'VIIX', 'VEON', 'VRA', 'VCYT', 'VSTM', 'VCEL', 'VRNT', 'VRSN', 'VRSK', 'VBTX', 'VERI',
                  'VRML', 'VRNA', 'VSAR', 'VTNR', 'VRTX', 'VIA', 'VIAB', 'VSAT', 'VIAV', 'VICL', 'VICR', 'CIZ', 'VSDA',
                  'CEZ', 'CID', 'CIL', 'CFO', 'CFA', 'CSF', 'CDC', 'CDL', 'VSMV', 'CSB', 'CSA', 'VBND', 'VUSE', 'VIDI',
                  'VDTH', 'VRAY', 'VKTX', 'VKTXW', 'VBFC', 'VLGEA', 'VNOM', 'VIRC', 'VIRT', 'VRTS', 'VRTSP', 'VRTU',
                  'VTGN', 'VTL', 'VIVE', 'VVPR', 'VVUS', 'VOD', 'VOXX', 'VYGR', 'VSEC', 'VTVT', 'VUZI', 'VWR', 'WBA',
                  'WAFD', 'WAFDW', 'WASH', 'WFBI', 'WSBF', 'WVE', 'WAYN', 'WSTG', 'WCFB', 'WDFC', 'FLAG', 'WEB', 'WBMD',
                  'WCST', 'WB', 'WEBK', 'WEN', 'WERN', 'WSBC', 'WTBA', 'WSTC', 'WMAR', 'WABC', 'WBB', 'WSTL', 'WDC',
                  'WNEB', 'WLB', 'WPRT', 'WEYS', 'WHLR', 'WHLRD', 'WHLRP', 'WHLRW', 'WHF', 'WHFBL', 'WFM', 'WHLM',
                  'WVVI', 'WVVIP', 'WLDN', 'WLFC', 'WLTW', 'WIN', 'WING', 'WINA', 'WINS', 'WTFC', 'WTFCM', 'WTFCW',
                  'AGZD', 'AGND', 'CXSE', 'EMCG', 'EMCB', 'DGRE', 'DXGE', 'HYZD', 'WETF', 'DXJS', 'GULF', 'HYND',
                  'CRDT', 'DGRW', 'DGRS', 'DXPS', 'UBND', 'WIX', 'WMIH', 'WBKC', 'WWD', 'WKHS', 'WRLD', 'WPCS', 'WPPGY',
                  'WMGI', 'WMGIZ', 'WSFS', 'WSFSL', 'WSCI', 'WVFC', 'WYNN', 'XBIT', 'XELB', 'XCRA', 'XNCR', 'XBIO',
                  'XBKS', 'XENE', 'XGTI', 'XGTIW', 'XLNX', 'GLDI', 'SLVO', 'XOMA', 'XPER', 'XPLR', 'XTLB', 'XNET',
                  'YNDX', 'YERR', 'YTRA', 'YTEN', 'YIN', 'YGYI', 'YRCW', 'YECO', 'YY', 'ZFGN', 'ZAGG', 'ZAIS', 'ZBRA',
                  'Z', 'ZG', 'ZN', 'ZNWAA', 'ZION', 'ZIONW', 'ZIONZ', 'ZIOP', 'ZIXI', 'ZGNX', 'ZSAN', 'ZUMZ', 'ZYNE',
                  'ZNGA']
        contract = Contract()
        for ix, c in enumerate(['IBKR']): #island[0:99]
            contract.symbol = c
            contract.secType = "STK"
            contract.currency = "USD"
            contract.exchange = "ISLAND"

            self.current_symbol = contract.symbol
            id = ix + 99
            self.reqMktData(id, contract, "", snapshot=False, regulatorySnapshot=False,
                        mktDataOptions=[])

    def keyboardInterrupt(self):
        self.nKeybInt += 1
        if self.nKeybInt == 1:
            self.stop()
        else:
            print("Finishing test")
            self.done = True

    def stop(self):
        print("Executing cancels")
        self.orderOperations_cancel()
        self.accountOperations_cancel()
        self.tickDataOperations_cancel()
        self.marketDepthOperations_cancel()
        self.realTimeBars_cancel()
        self.historicalDataRequests_cancel()
        self.optionsOperations_cancel()
        self.marketScanners_cancel()
        self.reutersFundamentals_cancel()
        self.bulletins_cancel()
        print("Executing cancels ... finished")

    def nextOrderId(self):
        oid = self.nextValidOrderId
        self.nextValidOrderId += 1
        return oid

    @iswrapper
    # ! [error]
    def error(self, reqId: TickerId, errorCode: int, errorString: str):
        super().error(reqId, errorCode, errorString)
        print("Error. Id: ", reqId, " Code: ", errorCode, " Msg: ", errorString)

    # ! [error] self.reqId2nErr[reqId] += 1


    @iswrapper
    def winError(self, text: str, lastError: int):
        super().winError(text, lastError)

    @iswrapper
    # ! [openorder]
    def openOrder(self, orderId: OrderId, contract: Contract, order: Order,
                  orderState: OrderState):
        super().openOrder(orderId, contract, order, orderState)
        print("OpenOrder. ID:", orderId, contract.symbol, contract.secType,
              "@", contract.exchange, ":", order.action, order.orderType,
              order.totalQuantity, orderState.status)
        # ! [openorder]

        if order.whatIf:
            print("WhatIf: ", orderId, "initMarginBefore: ", orderState.initMarginBefore, " maintMarginBefore: ", orderState.maintMarginBefore,
             "equityWithLoanBefore ", orderState.equityWithLoanBefore, " initMarginChange ", orderState.initMarginChange, " maintMarginChange: ", orderState.maintMarginChange,
                  " equityWithLoanChange: ", orderState.equityWithLoanChange, " initMarginAfter: ", orderState.initMarginAfter, " maintMarginAfter: ", orderState.maintMarginAfter,
            " equityWithLoanAfter: ", orderState.equityWithLoanAfter)

        order.contract = contract
        self.permId2ord[order.permId] = order

    @iswrapper
    # ! [openorderend]
    def openOrderEnd(self):
        super().openOrderEnd()
        print("OpenOrderEnd")
        # ! [openorderend]

        logging.debug("Received %d openOrders", len(self.permId2ord))

    @iswrapper
    # ! [orderstatus]
    def orderStatus(self, orderId: OrderId, status: str, filled: float,
                    remaining: float, avgFillPrice: float, permId: int,
                    parentId: int, lastFillPrice: float, clientId: int,
                    whyHeld: str, mktCapPrice: float):
        super().orderStatus(orderId, status, filled, remaining,
                            avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        print("OrderStatus. Id: ", orderId, ", Status: ", status, ", Filled: ", filled,
              ", Remaining: ", remaining, ", AvgFillPrice: ", avgFillPrice,
              ", PermId: ", permId, ", ParentId: ", parentId, ", LastFillPrice: ",
              lastFillPrice, ", ClientId: ", clientId, ", WhyHeld: ",
              whyHeld, ", MktCapPrice: ", mktCapPrice)

    # ! [orderstatus]


    @printWhenExecuting
    def accountOperations_req(self):
        # Requesting managed accounts***/
        # ! [reqmanagedaccts]
        self.reqManagedAccts()
        # ! [reqmanagedaccts]
        # Requesting accounts' summary ***/

        # ! [reqaaccountsummary]
        self.reqAccountSummary(9001, "All", AccountSummaryTags.AllTags)
        # ! [reqaaccountsummary]

        # ! [reqaaccountsummaryledger]
        self.reqAccountSummary(9002, "All", "$LEDGER")
        # ! [reqaaccountsummaryledger]

        # ! [reqaaccountsummaryledgercurrency]
        self.reqAccountSummary(9003, "All", "$LEDGER:EUR")
        # ! [reqaaccountsummaryledgercurrency]

        # ! [reqaaccountsummaryledgerall]
        self.reqAccountSummary(9004, "All", "$LEDGER:ALL")
        # ! [reqaaccountsummaryledgerall]

        # Subscribing to an account's information. Only one at a time!
        # ! [reqaaccountupdates]
        self.reqAccountUpdates(True, self.account)
        # ! [reqaaccountupdates]

        # ! [reqaaccountupdatesmulti]
        self.reqAccountUpdatesMulti(9005, self.account, "", True)
        # ! [reqaaccountupdatesmulti]

        # Requesting all accounts' positions.
        # ! [reqpositions]
        self.reqPositions()
        # ! [reqpositions]

        # ! [reqpositionsmulti]
        self.reqPositionsMulti(9006, self.account, "")
        # ! [reqpositionsmulti]

        # ! [reqfamilycodes]
        self.reqFamilyCodes()
        # ! [reqfamilycodes]

    @printWhenExecuting
    def accountOperations_cancel(self):
        # ! [cancelaaccountsummary]
        self.cancelAccountSummary(9001)
        self.cancelAccountSummary(9002)
        self.cancelAccountSummary(9003)
        self.cancelAccountSummary(9004)
        # ! [cancelaaccountsummary]

        # ! [cancelaaccountupdates]
        self.reqAccountUpdates(False, self.account)
        # ! [cancelaaccountupdates]

        # ! [cancelaaccountupdatesmulti]
        self.cancelAccountUpdatesMulti(9005)
        # ! [cancelaaccountupdatesmulti]

        # ! [cancelpositions]
        self.cancelPositions()
        # ! [cancelpositions]

        # ! [cancelpositionsmulti]
        self.cancelPositionsMulti(9006)
        # ! [cancelpositionsmulti]

    def pnlOperations(self):
        # ! [reqpnl]
        self.reqPnL(17001, "DU242650", "")
        # ! [reqpnl]
        time.sleep(1)
        # ! [cancelpnl]
        self.cancelPnL(17001)
        # ! [cancelpnl]

        # ! [reqpnlsingle]
        self.reqPnLSingle(17002, "DU242650", "", 265598);
        # ! [reqpnlsingle]
        time.sleep(1)
        # ! [cancelpnlsingle]
        self.cancelPnLSingle(17002);
        # ! [cancelpnlsingle]

    @iswrapper
    # ! [managedaccounts]
    def managedAccounts(self, accountsList: str):
        super().managedAccounts(accountsList)
        print("Account list: ", accountsList)
        # ! [managedaccounts]

        self.account = accountsList.split(",")[0]

    @iswrapper
    # ! [accountsummary]
    def accountSummary(self, reqId: int, account: str, tag: str, value: str,
                       currency: str):
        super().accountSummary(reqId, account, tag, value, currency)
        print("Acct Summary. ReqId:", reqId, "Acct:", account,
              "Tag: ", tag, "Value:", value, "Currency:", currency)

    # ! [accountsummary]


    @iswrapper
    # ! [accountsummaryend]
    def accountSummaryEnd(self, reqId: int):
        super().accountSummaryEnd(reqId)
        print("AccountSummaryEnd. Req Id: ", reqId)

    # ! [accountsummaryend]


    @iswrapper
    # ! [updateaccountvalue]
    def updateAccountValue(self, key: str, val: str, currency: str,
                           accountName: str):
        super().updateAccountValue(key, val, currency, accountName)
        print("UpdateAccountValue. Key:", key, "Value:", val,
              "Currency:", currency, "AccountName:", accountName)

    # ! [updateaccountvalue]


    @iswrapper
    # ! [updateportfolio]
    def updatePortfolio(self, contract: Contract, position: float,
                        marketPrice: float, marketValue: float,
                        averageCost: float, unrealizedPNL: float,
                        realizedPNL: float, accountName: str):
        super().updatePortfolio(contract, position, marketPrice, marketValue,
                                averageCost, unrealizedPNL, realizedPNL, accountName)
        print("UpdatePortfolio.", contract.symbol, "", contract.secType, "@",
              contract.exchange, "Position:", position, "MarketPrice:", marketPrice,
              "MarketValue:", marketValue, "AverageCost:", averageCost,
              "UnrealizedPNL:", unrealizedPNL, "RealizedPNL:", realizedPNL,
              "AccountName:", accountName)

    # ! [updateportfolio]


    @iswrapper
    # ! [updateaccounttime]
    def updateAccountTime(self, timeStamp: str):
        super().updateAccountTime(timeStamp)
        print("UpdateAccountTime. Time:", timeStamp)

    # ! [updateaccounttime]


    @iswrapper
    # ! [accountdownloadend]
    def accountDownloadEnd(self, accountName: str):
        super().accountDownloadEnd(accountName)
        print("Account download finished:", accountName)

    # ! [accountdownloadend]


    @iswrapper
    # ! [position]
    def position(self, account: str, contract: Contract, position: float,
                 avgCost: float):
        super().position(account, contract, position, avgCost)
        print("Position.", account, "Symbol:", contract.symbol, "SecType:",
              contract.secType, "Currency:", contract.currency,
              "Position:", position, "Avg cost:", avgCost)

    # ! [position]


    @iswrapper
    # ! [positionend]
    def positionEnd(self):
        super().positionEnd()
        print("PositionEnd")

    # ! [positionend]


    @iswrapper
    # ! [positionmulti]
    def positionMulti(self, reqId: int, account: str, modelCode: str,
                      contract: Contract, pos: float, avgCost: float):
        super().positionMulti(reqId, account, modelCode, contract, pos, avgCost)
        print("Position Multi. Request:", reqId, "Account:", account,
              "ModelCode:", modelCode, "Symbol:", contract.symbol, "SecType:",
              contract.secType, "Currency:", contract.currency, ",Position:",
              pos, "AvgCost:", avgCost)

    # ! [positionmulti]


    @iswrapper
    # ! [positionmultiend]
    def positionMultiEnd(self, reqId: int):
        super().positionMultiEnd(reqId)
        print("Position Multi End. Request:", reqId)

    # ! [positionmultiend]


    @iswrapper
    # ! [accountupdatemulti]
    def accountUpdateMulti(self, reqId: int, account: str, modelCode: str,
                           key: str, value: str, currency: str):
        super().accountUpdateMulti(reqId, account, modelCode, key, value,
                                   currency)
        print("Account Update Multi. Request:", reqId, "Account:", account,
              "ModelCode:", modelCode, "Key:", key, "Value:", value,
              "Currency:", currency)

    # ! [accountupdatemulti]


    @iswrapper
    # ! [accountupdatemultiend]
    def accountUpdateMultiEnd(self, reqId: int):
        super().accountUpdateMultiEnd(reqId)
        print("Account Update Multi End. Request:", reqId)

    # ! [accountupdatemultiend]


    @iswrapper
    # ! [familyCodes]
    def familyCodes(self, familyCodes: ListOfFamilyCode):
        super().familyCodes(familyCodes)
        print("Family Codes:")
        for familyCode in familyCodes:
            print("Account ID: %s, Family Code Str: %s" % (
                familyCode.accountID, familyCode.familyCodeStr))

    # ! [familyCodes]

    @iswrapper
    # ! [pnl]
    def pnl(self, reqId: int, dailyPnL: float,
            unrealizedPnL: float, realizedPnL: float):
        super().pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)
        print("Daily PnL. Req Id: ", reqId, ", daily PnL: ", dailyPnL,
              ", unrealizedPnL: ", unrealizedPnL, ", realizedPnL: ", realizedPnL)
    # ! [pnl]

    @iswrapper
    # ! [pnlsingle]
    def pnlSingle(self, reqId: int, pos: int, dailyPnL: float,
                  unrealizedPnL: float, realizedPnL: float, value: float):
        super().pnlSingle(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value)
        print("Daily PnL Single. Req Id: ", reqId, ", pos: ", pos,
              ", daily PnL: ", dailyPnL, ", unrealizedPnL: ", unrealizedPnL,
              ", realizedPnL: ", realizedPnL, ", value: ", value)
    # ! [pnlsingle]

    def marketDataType_req(self):
        # ! [reqmarketdatatype]
        # Switch to live (1) frozen (2) delayed (3) delayed frozen (4).
        self.reqMarketDataType(MarketDataTypeEnum.DELAYED)
        # ! [reqmarketdatatype]

    @iswrapper
    # ! [marketdatatype]
    def marketDataType(self, reqId: TickerId, marketDataType: int):
        super().marketDataType(reqId, marketDataType)
        print("MarketDataType. ", reqId, "Type:", marketDataType)

    # ! [marketdatatype]

    @printWhenExecuting
    # def tickDataOperations_req(self):
    def tickDataOperations_req(self):
        # Requesting real time market data

        pass
        self.reqMktData(1000, ContractSamples.CFD(), "", False, False, [])

        # ! [reqmktdata]
        # self.reqMktData(1000, ContractSamples.USStockAtSmart(), "", False, False, [])
        # self.reqMktData(1001, ContractSamples.StockComboContract(), "", True, False, [])
        # ! [reqmktdata]

        # ! [reqmktdata_snapshot]
        # self.reqMktData(1002, ContractSamples.FutureComboContract(), "", False, False, [])
        # ! [reqmktdata_snapshot]

        # ! [regulatorysnapshot]
        # Each regulatory snapshot request incurs a 0.01 USD fee
        # self.reqMktData(1003, ContractSamples.USStock(), "", False, True, [])
        # ! [regulatorysnapshot]

        # ! [reqmktdata_genticks]
        # Requesting RTVolume (Time & Sales), shortable and Fundamental Ratios generic ticks
        # self.reqMktData(1004, ContractSamples.USStock(), "233,236,258", False, False, [])
        # ! [reqmktdata_genticks]

        # ! [reqmktdata_contractnews]
        # Without the API news subscription this will generate an "invalid tick type" error
        # self.reqMktData(1005, ContractSamples.USStock(), "mdoff,292:BZ", False, False, [])
        # self.reqMktData(1006, ContractSamples.USStock(), "mdoff,292:BT", False, False, [])
        # self.reqMktData(1007, ContractSamples.USStock(), "mdoff,292:FLY", False, False, [])
        # self.reqMktData(1008, ContractSamples.USStock(), "mdoff,292:MT", False, False, [])
        # ! [reqmktdata_contractnews]


        # ! [reqmktdata_broadtapenews]
        # self.reqMktData(1009, ContractSamples.BTbroadtapeNewsFeed(),
        #                 "mdoff,292", False, False, [])
        # self.reqMktData(1010, ContractSamples.BZbroadtapeNewsFeed(),
        #                 "mdoff,292", False, False, [])
        # self.reqMktData(1011, ContractSamples.FLYbroadtapeNewsFeed(),
        #                 "mdoff,292", False, False, [])
        # self.reqMktData(1012, ContractSamples.MTbroadtapeNewsFeed(),
        #                 "mdoff,292", False, False, [])
        # ! [reqmktdata_broadtapenews]

        # ! [reqoptiondatagenticks]
        # Requesting data for an option contract will return the greek values
        # self.reqMktData(1013, ContractSamples.OptionWithLocalSymbol(), "", False, False, [])
        # ! [reqoptiondatagenticks]

        # ! [reqsmartcomponents]
        # Requests description of map of single letter exchange codes to full exchange names
        # self.reqSmartComponents(1013, "a6")
        # ! [reqsmartcomponents]

        # ! [reqfuturesopeninterest]
        # self.reqMktData(1014, ContractSamples.SimpleFuture(), "mdoff,588", False, False, [])
        # ! [reqfuturesopeninterest]

        # ! [reqmktdatapreopenbidask]
        # self.reqMktData(1015, ContractSamples.SimpleFuture(), "", False, False, [])
        # ! [reqmktdatapreopenbidask]

        # ! [reqavgoptvolume]
        # self.reqMktData(1016, ContractSamples.USStockAtSmart(), "mdoff,105", False, False, [])
        # ! [reqavgoptvolume]

    @printWhenExecuting
    def tickDataOperations_cancel(self):
        # Canceling the market data subscription
        # ! [cancelmktdata]


        #ROLAND
        self.cancelMktData(999)


        # self.cancelMktData(1000)
        # self.cancelMktData(1001)
        # self.cancelMktData(1002)
        # self.cancelMktData(1003)
        # # ! [cancelmktdata]
        #
        # self.cancelMktData(1004)
        # self.cancelMktData(1005)
        # self.cancelMktData(1006)
        # self.cancelMktData(1007)
        # self.cancelMktData(1008)
        # self.cancelMktData(1009)
        # self.cancelMktData(1010)
        # self.cancelMktData(1011)
        # self.cancelMktData(1012)
        # self.cancelMktData(1013)
        # self.cancelMktData(1014)
        # self.cancelMktData(1015)
        # self.cancelMktData(1016)

    # @iswrapper
    # ! [tickprice]
    # def tickPrice(self, reqId: TickerId, tickType: TickType, price: float,
    #               attrib: TickAttrib):
    #     super().tickPrice(reqId, tickType, price, attrib)
    #     print("Tick Price. Ticker Id:", reqId, "tickType:", tickType,
    #           "Price:", price, "CanAutoExecute:", attrib.canAutoExecute,
    #           "PastLimit:", attrib.pastLimit, end=' ')
    #     if tickType == TickTypeEnum.BID or tickType == TickTypeEnum.ASK:
    #         print("PreOpen:", attrib.preOpen)
    #     else:
    #         print()

    @iswrapper
    # ! [tickprice]
    def tickPrice(self, reqId: TickerId, tickType: TickType, price: float,
                  attrib: TickAttrib):
        super().tickPrice(reqId, tickType, price, attrib)

        anls = Analysis()
        anls.receive_tick_price(self.current_symbol, datetime.datetime.now(), tickType, price)
        # print(reqId)
        # if self.current_symbol == 'AUD':
        #     self.done = True

        if tickType == TickTypeEnum.BID or tickType == TickTypeEnum.ASK:
            pass#print("PreOpen:", attrib.preOpen)
        else:
            pass#print()

    # ! [tickprice]


    # @iswrapper
    # # ! [ticksize]
    # def tickSize(self, reqId: TickerId, tickType: TickType, size: int):
    #     super().tickSize(reqId, tickType, size)
    #     print("Tick Size. Ticker Id:", reqId, "tickType:", tickType, "Size:", size)
    #
    # # ! [ticksize]

    @iswrapper
    # ! [ticksize]
    def tickSize(self, reqId: TickerId, tickType: TickType, size: int):
        super().tickSize(reqId, tickType, size)

        anls = Analysis()
        anls.receive_tick_size(self.current_symbol, datetime.datetime.now(), tickType, size)
        # print(reqId)
        # ! [ticksize]

    @iswrapper
    # ! [tickgeneric]
    def tickGeneric(self, reqId: TickerId, tickType: TickType, value: float):
        super().tickGeneric(reqId, tickType, value)
        print("Tick Generic. Ticker Id:", reqId, "tickType:", tickType, "Value:", value)

    # ! [tickgeneric]


    @iswrapper
    # ! [tickstring]
    def tickString(self, reqId: TickerId, tickType: TickType, value: str):
        super().tickString(reqId, tickType, value)
        print("Tick string. Ticker Id:", reqId, "Type:", tickType, "Value:", value)

    # ! [tickstring]


    @iswrapper
    # ! [ticksnapshotend]
    def tickSnapshotEnd(self, reqId: int):
        super().tickSnapshotEnd(reqId)
        print("TickSnapshotEnd:", reqId)

    # ! [ticksnapshotend]

    @iswrapper
    # ! [rerouteMktDataReq]
    def rerouteMktDataReq(self, reqId: int, conId: int, exchange: str):
        super().rerouteMktDataReq(reqId, conId, exchange)
        print("Re-route market data request. Req Id: ", reqId,
              ", ConId: ", conId, " Exchange: ", exchange)

    # ! [rerouteMktDataReq]

    @iswrapper
    # ! [marketRule]
    def marketRule(self, marketRuleId: int, priceIncrements: ListOfPriceIncrements):
        super().marketRule(marketRuleId, priceIncrements)
        print("Market Rule ID: ", marketRuleId)
        for priceIncrement in priceIncrements:
            print("Price Increment. Low Edge: ", priceIncrement.lowEdge,
                  ", Increment: ", priceIncrement.increment)
    # ! [marketRule]

    @printWhenExecuting
    def tickByTickOperations(self):
        # Requesting tick-by-tick data (only refresh)
        # ! [reqtickbytick]
        self.reqTickByTickData(19001, ContractSamples.USStockAtSmart(), "Last", 0, True)
        self.reqTickByTickData(19002, ContractSamples.USStockAtSmart(), "AllLast", 0, False)
        self.reqTickByTickData(19003, ContractSamples.USStockAtSmart(), "BidAsk", 0, True)
        self.reqTickByTickData(19004, ContractSamples.USStockAtSmart(), "MidPoint", 0, False)
        # ! [reqtickbytick]

        time.sleep(1)

        # ! [canceltickbytick]
        self.cancelTickByTickData(19001)
        self.cancelTickByTickData(19002)
        self.cancelTickByTickData(19003)
        self.cancelTickByTickData(19004)
        # ! [canceltickbytick]

        # Requesting tick-by-tick data (refresh + historicalticks)
        # ! [reqtickbytickwithhist]
        self.reqTickByTickData(19001, ContractSamples.EuropeanStock(), "Last", 10, False)
        self.reqTickByTickData(19002, ContractSamples.EuropeanStock(), "AllLast", 10, False)
        self.reqTickByTickData(19003, ContractSamples.EuropeanStock(), "BidAsk", 10, False)
        self.reqTickByTickData(19004, ContractSamples.EurGbpFx(), "MidPoint", 10, True)
        # ! [reqtickbytickwithhist]

        time.sleep(1)

        # ! [canceltickbytickwithhist]
        self.cancelTickByTickData(19005)
        self.cancelTickByTickData(19006)
        self.cancelTickByTickData(19007)
        self.cancelTickByTickData(19008)
        # ! [canceltickbytickwithhist]

    @iswrapper
	# ! [tickbytickalllast]
    def tickByTickAllLast(self, reqId: int, tickType: int, time: int, price: float,
                          size: int, attribs: TickAttrib, exchange: str,
                          specialConditions: str):
        super().tickByTickAllLast(reqId, tickType, time, price, size, attribs,
                                  exchange, specialConditions)
        if tickType == 1:
            print("Last.", end='')
        else:
            print("AllLast.", end='')
        print(" ReqId: ", reqId,
              " Time: ", datetime.datetime.fromtimestamp(time).strftime("%Y%m%d %H:%M:%S"),
              " Price: ", price, " Size: ", size, " Exch: " , exchange,
              "Spec Cond: ", specialConditions, end='')
        if attribs.pastLimit:
            print(" pastLimit ", end='')
        if attribs.unreported:
            print(" unreported", end='')
        print()
	# ! [tickbytickalllast]
		
    @iswrapper
	# ! [tickbytickbidask]
    def tickByTickBidAsk(self, reqId: int, time: int, bidPrice: float, askPrice: float,
                         bidSize: int, askSize: int, attribs: TickAttrib):
        super().tickByTickBidAsk(reqId, time, bidPrice, askPrice, bidSize,
                                 askSize, attribs)
        print("BidAsk. Req Id: ", reqId,
              " Time: ", datetime.datetime.fromtimestamp(time).strftime("%Y%m%d %H:%M:%S"),
              " BidPrice: ", bidPrice, " AskPrice: ", askPrice, " BidSize: ", bidSize,
              " AskSize: ", askSize, end='')
        if attribs.bidPastLow:
            print(" bidPastLow", end='')
        if attribs.askPastHigh:
            print(" askPastHigh", end='')
        print()
		
	# ! [tickbytickbidask]
		
	# ! [tickbytickmidpoint]
    @iswrapper
    def tickByTickMidPoint(self, reqId: int, time: int, midPoint: float):
        super().tickByTickMidPoint(reqId, time, midPoint)
        print("Midpoint. Req Id: ", reqId,
              " Time: ", datetime.datetime.fromtimestamp(time).strftime("%Y%m%d %H:%M:%S"),
              " MidPoint: ", midPoint)

	# ! [tickbytickmidpoint]
			  
    @printWhenExecuting
    def marketDepthOperations_req(self):
        # Requesting the Deep Book
        # ! [reqmarketdepth]
        self.reqMktDepth(2101, ContractSamples.USStock(), 5, [])
        # self.reqMktDepth(2001, ContractSamples.EurGbpFx(), 5, [])
        # ! [reqmarketdepth]

        # Request list of exchanges sending market depth to UpdateMktDepthL2()
        # ! [reqMktDepthExchanges]
        # self.reqMktDepthExchanges()
        # ! [reqMktDepthExchanges]

    @iswrapper
    # ! [rerouteMktDepthReq]
    def rerouteMktDepthReq(self, reqId: int, conId: int, exchange: str):
        super().rerouteMktDataReq(reqId, conId, exchange)
        print("Re-route market data request. Req Id: ", reqId,
              ", ConId: ", conId, " Exchange: ", exchange)
    # ! [rerouteMktDepthReq]

    @printWhenExecuting
    def marketDepthOperations_cancel(self):
        # Canceling the Deep Book request
        # ! [cancelmktdepth]
        self.cancelMktDepth(2101)
        self.cancelMktDepth(2001)
        # ! [cancelmktdepth]

    @printWhenExecuting
    def realTimeBars_req(self):
        # Requesting real time bars
        # ! [reqrealtimebars]
        self.reqRealTimeBars(3101, ContractSamples.USStockAtSmart(), 5, "MIDPOINT", True, [])
        self.reqRealTimeBars(3001, ContractSamples.EurGbpFx(), 5, "MIDPOINT", True, [])
        # ! [reqrealtimebars]

    @iswrapper
    # ! [realtimebar]
    def realtimeBar(self, reqId:TickerId, time:int, open:float, high:float,
                    low:float, close:float, volume:int, wap:float, count:int):
        super().realtimeBar(reqId, time, open, high, low, close, volume, wap, count)
        print("RealTimeBars. ", reqId, ": time ", time, ", open: ",open,
              ", high: ", high, ", low: ", low, ", close: ", close, ", volume: ", volume,
              ", wap: ", wap, ", count: ", count)
    # ! [realtimebar]

    @printWhenExecuting
    def realTimeBars_cancel(self):
        # Canceling real time bars
        # ! [cancelrealtimebars]
        self.cancelRealTimeBars(3101)
        self.cancelRealTimeBars(3001)
        # ! [cancelrealtimebars]

    @printWhenExecuting
    def historicalDataRequests_req(self):
        # Requesting historical data
        # ! [reqHeadTimeStamp]
        self.reqHeadTimeStamp(4103, ContractSamples.USStockAtSmart(), "TRADES", 0, 1)
        # ! [reqHeadTimeStamp]

        time.sleep(1)

        # ! [cancelHeadTimestamp]
        self.cancelHeadTimeStamp(4103)
        # ! [cancelHeadTimestamp]

        # ! [reqhistoricaldata]
        queryTime = (datetime.datetime.today() -
                     datetime.timedelta(days=180)).strftime("%Y%m%d %H:%M:%S")
        self.reqHistoricalData(4101, ContractSamples.USStockAtSmart(), queryTime,
                               "1 M", "1 day", "MIDPOINT", 1, 1, False, [])
        self.reqHistoricalData(4001, ContractSamples.EurGbpFx(), queryTime,
                               "1 M", "1 day", "MIDPOINT", 1, 1, False, [])
        self.reqHistoricalData(4002, ContractSamples.EuropeanStock(), queryTime,
                               "10 D", "1 min", "TRADES", 1, 1, False, [])
        # ! [reqhistoricaldata]

        # ! [reqHistogramData]
        self.reqHistogramData(4104, ContractSamples.USStock(), False, "3 days")
        # ! [reqHistogramData]
        time.sleep(2)
        # ! [cancelHistogramData]
        self.cancelHistogramData(4104)
        # ! [cancelHistogramData]


    @printWhenExecuting
    def historicalDataRequests_cancel(self):
        # Canceling historical data requests
        self.cancelHistoricalData(4101)
        self.cancelHistoricalData(4001)
        self.cancelHistoricalData(4002)

    @printWhenExecuting
    def historicalTicksRequests_req(self):
        # ! [reqhistoricalticks]
        self.reqHistoricalTicks(18001, ContractSamples.USStockAtSmart(),
                                "20170712 21:39:33", "", 10, "TRADES", 1, True, [])
        self.reqHistoricalTicks(18002, ContractSamples.USStockAtSmart(),
                                "20170712 21:39:33", "", 10, "BID_ASK", 1, True, [])
        self.reqHistoricalTicks(18003, ContractSamples.USStockAtSmart(),
                                "20170712 21:39:33", "", 10, "MIDPOINT", 1, True, [])
        # ! [reqhistoricalticks]

    @iswrapper
    # ! [headTimestamp]
    def headTimestamp(self, reqId:int, headTimestamp:str):
        print("HeadTimestamp: ", reqId, " ", headTimestamp)
    # ! [headTimestamp]

    @iswrapper
    # ! [histogramData]
    def histogramData(self, reqId:int, items:HistogramDataList):
        print("HistogramData: ", reqId, " ", items)
    # ! [histogramData]

    @iswrapper
    # ! [historicalDataUpdate]
    def historicalDataUpdate(self, reqId: int, bar: BarData):
        print("HistoricalDataUpdate. ", reqId, " Date:", bar.date, "Open:", bar.open,
              "High:", bar.high, "Low:", bar.low, "Close:", bar.close, "Volume:", bar.volume,
              "Count:", bar.barCount, "WAP:", bar.average)
    # ! [historicalDataUpdate]

    @iswrapper
    # ! [historicalticks]
    def historicalTicks(self, reqId: int, ticks: ListOfHistoricalTick, done: bool):
        for tick in ticks:
            print("Historical Tick. Req Id: ", reqId, ", time: ", tick.time,
                  ", price: ", tick.price, ", size: ", tick.size)
    # ! [historicalticks]

    @iswrapper
    # ! [historicalticksbidask]
    def historicalTicksBidAsk(self, reqId: int, ticks: ListOfHistoricalTickBidAsk,
                              done: bool):
        for tick in ticks:
            print("Historical Tick Bid/Ask. Req Id: ", reqId, ", time: ", tick.time,
                  ", bid price: ", tick.priceBid, ", ask price: ", tick.priceAsk,
                  ", bid size: ", tick.sizeBid, ", ask size: ", tick.sizeAsk)
    # ! [historicalticksbidask]

    @iswrapper
    # ! [historicaltickslast]
    def historicalTicksLast(self, reqId: int, ticks: ListOfHistoricalTickLast,
                            done: bool):
        for tick in ticks:
            print("Historical Tick Last. Req Id: ", reqId, ", time: ", tick.time,
                  ", price: ", tick.price, ", size: ", tick.size, ", exchange: ", tick.exchange,
                  ", special conditions:", tick.specialConditions)
    # ! [historicaltickslast]

    @printWhenExecuting
    def optionsOperations_req(self):
        # ! [reqsecdefoptparams]
        self.reqSecDefOptParams(0, "IBM", "", "STK", 8314)
        # ! [reqsecdefoptparams]

        # Calculating implied volatility
        # ! [calculateimpliedvolatility]
        self.calculateImpliedVolatility(5001, ContractSamples.OptionAtBOX(), 5, 85, [])
        # ! [calculateimpliedvolatility]

        # Calculating option's price
        # ! [calculateoptionprice]
        self.calculateOptionPrice(5002, ContractSamples.OptionAtBOX(), 0.22, 85, [])
        # ! [calculateoptionprice]

        # Exercising options
        # ! [exercise_options]
        self.exerciseOptions(5003, ContractSamples.OptionWithTradingClass(), 1,
                             1, self.account, 1)
        # ! [exercise_options]

    @printWhenExecuting
    def optionsOperations_cancel(self):
        # Canceling implied volatility
        self.cancelCalculateImpliedVolatility(5001)
        # Canceling option's price calculation
        self.cancelCalculateOptionPrice(5002)

    @iswrapper
    # ! [securityDefinitionOptionParameter]
    def securityDefinitionOptionParameter(self, reqId: int, exchange: str,
                                          underlyingConId: int, tradingClass: str, multiplier: str,
                                          expirations: SetOfString, strikes: SetOfFloat):
        super().securityDefinitionOptionParameter(reqId, exchange,
                                                  underlyingConId, tradingClass, multiplier, expirations, strikes)
        print("Security Definition Option Parameter. ReqId:%d Exchange:%s "
              "Underlying conId: %d TradingClass:%s Multiplier:%s Exp:%s Strikes:%s",
              reqId, exchange, underlyingConId, tradingClass, multiplier,
              ",".join(expirations), ",".join(str(strikes)))

    # ! [securityDefinitionOptionParameter]


    @iswrapper
    # ! [securityDefinitionOptionParameterEnd]
    def securityDefinitionOptionParameterEnd(self, reqId: int):
        super().securityDefinitionOptionParameterEnd(reqId)
        print("Security Definition Option Parameter End. Request: ", reqId)

    # ! [securityDefinitionOptionParameterEnd]


    @iswrapper
    # ! [tickoptioncomputation]
    def tickOptionComputation(self, reqId: TickerId, tickType: TickType,
                              impliedVol: float, delta: float, optPrice: float, pvDividend: float,
                              gamma: float, vega: float, theta: float, undPrice: float):
        super().tickOptionComputation(reqId, tickType, impliedVol, delta,
                                      optPrice, pvDividend, gamma, vega, theta, undPrice)
        print("TickOptionComputation. TickerId:", reqId, "tickType:", tickType,
              "ImpliedVolatility:", impliedVol, "Delta:", delta, "OptionPrice:",
              optPrice, "pvDividend:", pvDividend, "Gamma: ", gamma, "Vega:", vega,
              "Theta:", theta, "UnderlyingPrice:", undPrice)

    # ! [tickoptioncomputation]


    @printWhenExecuting
    def contractOperations_req(self):
        # ! [reqcontractdetails]
        self.reqContractDetails(209, ContractSamples.EurGbpFx())
        self.reqContractDetails(210, ContractSamples.OptionForQuery())
        self.reqContractDetails(211, ContractSamples.Bond())
        self.reqContractDetails(212, ContractSamples.FuturesOnOptions())
        # ! [reqcontractdetails]

        # ! [reqmatchingsymbols]
        self.reqMatchingSymbols(212, "IB")
        # ! [reqmatchingsymbols]

    @printWhenExecuting
    def contractNewsFeed_req(self):
        # ! [reqcontractdetailsnews]
        self.reqContractDetails(213, ContractSamples.NewsFeedForQuery())
        # ! [reqcontractdetailsnews]

        # Returns list of subscribed news providers
        # ! [reqNewsProviders]
        self.reqNewsProviders()
        # ! [reqNewsProviders]

        # Returns body of news article given article ID
        # ! [reqNewsArticle]
        self.reqNewsArticle(214,"BZ", "BZ$04507322", [])
        # ! [reqNewsArticle]

        # Returns list of historical news headlines with IDs
        # ! [reqHistoricalNews]
        self.reqHistoricalNews(215, 8314, "BZ+FLY", "", "", 10, [])
        # ! [reqHistoricalNews]

    @iswrapper
    #! [tickNews]
    def tickNews(self, tickerId: int, timeStamp: int, providerCode: str,
                 articleId: str, headline: str, extraData: str):
        print("tickNews: ", tickerId, ", timeStamp: ", timeStamp,
              ", providerCode: ", providerCode, ", articleId: ", articleId,
              ", headline: ", headline, "extraData: ", extraData)
    #! [tickNews]

    @iswrapper
    #! [historicalNews]
    def historicalNews(self, reqId: int, time: str, providerCode: str,
                       articleId: str, headline: str):
        print("historicalNews: ", reqId, ", time: ", time,
              ", providerCode: ", providerCode, ", articleId: ", articleId,
              ", headline: ", headline)
    #! [historicalNews]

    @iswrapper
    #! [historicalNewsEnd]
    def historicalNewsEnd(self, reqId:int, hasMore:bool):
        print("historicalNewsEnd: ", reqId, ", hasMore: ", hasMore)
    #! [historicalNewsEnd]

    @iswrapper
    #! [newsProviders]
    def newsProviders(self, newsProviders: ListOfNewsProviders):
        print("newsProviders: ")
        for provider in newsProviders:
            print(provider)
    #! [newsProviders]

    @iswrapper
    #! [newsArticle]
    def newsArticle(self, reqId: int, articleType: int, articleText: str):
        print("newsArticle: ", reqId, ", articleType: ", articleType,
              ", articleText: ", articleText)
    #! [newsArticle]

    @iswrapper
    # ! [contractdetails]
    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        super().contractDetails(reqId, contractDetails)
        printinstance(contractDetails.contract)

    # ! [contractdetails]


    @iswrapper
    # ! [bondcontractdetails]
    def bondContractDetails(self, reqId: int, contractDetails: ContractDetails):
        super().bondContractDetails(reqId, contractDetails)

    # ! [bondcontractdetails]

    @iswrapper
    # ! [contractdetailsend]
    def contractDetailsEnd(self, reqId: int):
        super().contractDetailsEnd(reqId)
        print("ContractDetailsEnd. ", reqId, "\n")

    # ! [contractdetailsend]


    @iswrapper
    # ! [symbolSamples]
    def symbolSamples(self, reqId: int,
                      contractDescriptions: ListOfContractDescription):
        super().symbolSamples(reqId, contractDescriptions)
        print("Symbol Samples. Request Id: ", reqId)

        for contractDescription in contractDescriptions:
            derivSecTypes = ""
            for derivSecType in contractDescription.derivativeSecTypes:
                derivSecTypes += derivSecType
                derivSecTypes += " "
            print("Contract: conId:%s, symbol:%s, secType:%s primExchange:%s, "
                  "currency:%s, derivativeSecTypes:%s" % (
                contractDescription.contract.conId,
                contractDescription.contract.symbol,
                contractDescription.contract.secType,
                contractDescription.contract.primaryExchange,
                contractDescription.contract.currency, derivSecTypes))

    # ! [symbolSamples]


    @printWhenExecuting
    def marketScanners_req(self):
        # Requesting list of valid scanner parameters which can be used in TWS
        # ! [reqscannerparameters]
        self.reqScannerParameters()
        # ! [reqscannerparameters]

        # Triggering a scanner subscription
        # ! [reqscannersubscription]
        self.reqScannerSubscription(7001,
                                    ScannerSubscriptionSamples.TopPercentGainersIbis(), [])
        # ! [reqscannersubscription]

    @printWhenExecuting
    def marketScanners_cancel(self):
        # Canceling the scanner subscription
        # ! [cancelscannersubscription]
        self.cancelScannerSubscription(7001)
        # ! [cancelscannersubscription]

    @iswrapper
    # ! [scannerparameters]
    def scannerParameters(self, xml: str):
        super().scannerParameters(xml)
        open('log/scanner.xml', 'w').write(xml)

    # ! [scannerparameters]


    @iswrapper
    # ! [scannerdata]
    def scannerData(self, reqId: int, rank: int, contractDetails: ContractDetails,
                    distance: str, benchmark: str, projection: str, legsStr: str):
        super().scannerData(reqId, rank, contractDetails, distance, benchmark,
                            projection, legsStr)
        print("ScannerData. ", reqId, "Rank:", rank, "Symbol:", contractDetails.contract.symbol,
              "SecType:", contractDetails.contract.secType,
              "Currency:", contractDetails.contract.currency,
              "Distance:", distance, "Benchmark:", benchmark,
              "Projection:", projection, "Legs String:", legsStr)

    # ! [scannerdata]


    @iswrapper
    # ! [scannerdataend]
    def scannerDataEnd(self, reqId: int):
        super().scannerDataEnd(reqId)
        print("ScannerDataEnd. ", reqId)
        # ! [scannerdataend]

    @iswrapper
    # ! [smartcomponents]
    def smartComponents(self, reqId:int, map:SmartComponentMap):
        super().smartComponents(reqId, map)
        print("smartComponents: ")
        for exch in map:
            print(exch.bitNumber, ", Exchange Name: ", exch.exchange,
                  ", Letter: ", exch.exchangeLetter)
    # ! [smartcomponents]

    @iswrapper
    # ! [tickReqParams]
    def tickReqParams(self, tickerId:int, minTick:float,
                      bboExchange:str, snapshotPermissions:int):
        super().tickReqParams(tickerId, minTick, bboExchange, snapshotPermissions)
        print("tickReqParams: ", tickerId, " minTick: ", minTick,
              " bboExchange: ", bboExchange, " snapshotPermissions: ", snapshotPermissions)
    # ! [tickReqParams]

    @iswrapper
    # ! [mktDepthExchanges]
    def mktDepthExchanges(self, depthMktDataDescriptions:ListOfDepthExchanges):
        super().mktDepthExchanges(depthMktDataDescriptions)
        print("mktDepthExchanges:")
        for desc in depthMktDataDescriptions:
            printinstance(desc)
    # ! [mktDepthExchanges]

    @printWhenExecuting
    def reutersFundamentals_req(self):
        # Requesting Fundamentals
        # ! [reqfundamentaldata]
        self.reqFundamentalData(8001, ContractSamples.USStock(),
                                "ReportsFinSummary", [])
        # ! [reqfundamentaldata]

    @printWhenExecuting
    def reutersFundamentals_cancel(self):
        # Canceling fundamentals request ***/
        # ! [cancelfundamentaldata]
        self.cancelFundamentalData(8001)
        # ! [cancelfundamentaldata]

    @iswrapper
    # ! [fundamentaldata]
    def fundamentalData(self, reqId: TickerId, data: str):
        super().fundamentalData(reqId, data)
        print("FundamentalData. ", reqId, data)
    # ! [fundamentaldata]

    @printWhenExecuting
    def bulletins_req(self):
        # Requesting Interactive Broker's news bulletins
        # ! [reqnewsbulletins]
        self.reqNewsBulletins(True)
        # ! [reqnewsbulletins]

    @printWhenExecuting
    def bulletins_cancel(self):
        # Canceling IB's news bulletins
        # ! [cancelnewsbulletins]
        self.cancelNewsBulletins()
        # ! [cancelnewsbulletins]

    @iswrapper
    # ! [updatenewsbulletin]
    def updateNewsBulletin(self, msgId: int, msgType: int, newsMessage: str,
                           originExch: str):
        super().updateNewsBulletin(msgId, msgType, newsMessage, originExch)
        print("News Bulletins. ", msgId, " Type: ", msgType, "Message:", newsMessage,
              "Exchange of Origin: ", originExch)
        # ! [updatenewsbulletin]

        self.bulletins_cancel()

    def ocaSample(self):
        # OCA ORDER
        # ! [ocasubmit]
        ocaOrders = [OrderSamples.LimitOrder("BUY", 1, 10), OrderSamples.LimitOrder("BUY", 1, 11),
                     OrderSamples.LimitOrder("BUY", 1, 12)]
        OrderSamples.OneCancelsAll("TestOCA_" + self.nextValidOrderId, ocaOrders, 2)
        for o in ocaOrders:
            self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), o)
            # ! [ocasubmit]

    def conditionSamples(self):
        # ! [order_conditioning_activate]
        mkt = OrderSamples.MarketOrder("BUY", 100)
        # Order will become active if conditioning criteria is met
        mkt.conditionsCancelOrder = True
        mkt.conditions.append(
            OrderSamples.PriceCondition(PriceCondition.TriggerMethodEnum.Default,
                                        208813720, "SMART", 600, False, False))
        mkt.conditions.append(OrderSamples.ExecutionCondition("EUR.USD", "CASH", "IDEALPRO", True))
        mkt.conditions.append(OrderSamples.MarginCondition(30, True, False))
        mkt.conditions.append(OrderSamples.PercentageChangeCondition(15.0, 208813720, "SMART", True, True))
        mkt.conditions.append(OrderSamples.TimeCondition("20160118 23:59:59", True, False))
        mkt.conditions.append(OrderSamples.VolumeCondition(208813720, "SMART", False, 100, True))
        self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), mkt)
        # ! [order_conditioning_activate]

        # Conditions can make the order active or cancel it. Only LMT orders can be conditionally canceled.
        # ! [order_conditioning_cancel]
        lmt = OrderSamples.LimitOrder("BUY", 100, 20)
        # The active order will be cancelled if conditioning criteria is met
        lmt.conditionsCancelOrder = True
        lmt.conditions.append(
            OrderSamples.PriceCondition(PriceCondition.TriggerMethodEnum.Last,
                                        208813720, "SMART", 600, False, False))
        self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), lmt)
        # ! [order_conditioning_cancel]

    def bracketSample(self):
        # BRACKET ORDER
        # ! [bracketsubmit]
        bracket = OrderSamples.BracketOrder(self.nextOrderId(), "BUY", 100, 30, 40, 20)
        for o in bracket:
            self.placeOrder(o.orderId, ContractSamples.EuropeanStock(), o)
            self.nextOrderId()  # need to advance this we'll skip one extra oid, it's fine
            # ! [bracketsubmit]

    def hedgeSample(self):
        # F Hedge order
        # ! [hedgesubmit]
        # Parent order on a contract which currency differs from your base currency
        parent = OrderSamples.LimitOrder("BUY", 100, 10)
        parent.orderId = self.nextOrderId()
        # Hedge on the currency conversion
        hedge = OrderSamples.MarketFHedge(parent.orderId, "BUY")
        # Place the parent first...
        self.placeOrder(parent.orderId, ContractSamples.EuropeanStock(), parent)
        # Then the hedge order
        self.placeOrder(self.nextOrderId(), ContractSamples.EurGbpFx(), hedge)
        # ! [hedgesubmit]

    def testAlgoSamples(self):
        # ! [algo_base_order]
        baseOrder = OrderSamples.LimitOrder("BUY", 1000, 1)
        # ! [algo_base_order]

        # ! [arrivalpx]
        AvailableAlgoParams.FillArrivalPriceParams(baseOrder, 0.1,
                                                   "Aggressive", "09:00:00 CET", "16:00:00 CET", True, True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [arrivalpx]


        # ! [darkice]
        AvailableAlgoParams.FillDarkIceParams(baseOrder, 10,
                                              "09:00:00 CET", "16:00:00 CET", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [darkice]


        # ! [ad]
        # The Time Zone in "startTime" and "endTime" attributes is ignored and always defaulted to GMT
        AvailableAlgoParams.FillAccumulateDistributeParams(baseOrder, 10, 60,
                                                           True, True, 1, True, True,
                                                           "20161010-12:00:00 GMT", "20161010-16:00:00 GMT")
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [ad]


        # ! [twap]
        AvailableAlgoParams.FillTwapParams(baseOrder, "Marketable",
                                           "09:00:00 CET", "16:00:00 CET", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [twap]


        # ! [vwap]
        AvailableAlgoParams.FillVwapParams(baseOrder, 0.2,
                                           "09:00:00 CET", "16:00:00 CET", True, True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [vwap]


        # ! [balanceimpactrisk]
        AvailableAlgoParams.FillBalanceImpactRiskParams(baseOrder, 0.1,
                                                        "Aggressive", True)
        self.placeOrder(self.nextOrderId(), ContractSamples.USOptionContract(), baseOrder)
        # ! [balanceimpactrisk]


        # ! [minimpact]
        AvailableAlgoParams.FillMinImpactParams(baseOrder, 0.3)
        self.placeOrder(self.nextOrderId(), ContractSamples.USOptionContract(), baseOrder)
        # ! [minimpact]

        # ! [adaptive]
        AvailableAlgoParams.FillAdaptiveParams(baseOrder, "Normal")
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [adaptive]

        # ! [closepx]
        AvailableAlgoParams.FillClosePriceParams(baseOrder, 0.5, "Neutral",
                                                 "12:00:00 EST", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [closepx]

        # ! [pctvol]
        AvailableAlgoParams.FillPctVolParams(baseOrder, 0.5,
                                             "12:00:00 EST", "14:00:00 EST", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [pctvol]

        # ! [pctvolpx]
        AvailableAlgoParams.FillPriceVariantPctVolParams(baseOrder,
                                                         0.1, 0.05, 0.01, 0.2, "12:00:00 EST", "14:00:00 EST", True,
                                                         100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [pctvolpx]

        # ! [pctvolsz]
        AvailableAlgoParams.FillSizeVariantPctVolParams(baseOrder,
                                                        0.2, 0.4, "12:00:00 EST", "14:00:00 EST", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [pctvolsz]

        # ! [pctvoltm]
        AvailableAlgoParams.FillTimeVariantPctVolParams(baseOrder,
                                                        0.2, 0.4, "12:00:00 EST", "14:00:00 EST", True, 100000)
        self.placeOrder(self.nextOrderId(), ContractSamples.USStockAtSmart(), baseOrder)
        # ! [pctvoltm]

        # ! [jeff_vwap_algo]
        AvailableAlgoParams.FillJefferiesVWAPParams(baseOrder,
                                                    "10:00:00 EST", "16:00:00 EST", 10, 10, "Exclude_Both",
                                                    130, 135, 1, 10, "Patience", False, "Midpoint")

        self.placeOrder(self.nextOrderId(), ContractSamples.JefferiesContract(), baseOrder)
        # ! [jeff_vwap_algo]

        # ! [csfb_inline_algo]
        AvailableAlgoParams.FillCSFBInlineParams(baseOrder,
                                                 "10:00:00 EST", "16:00:00 EST", "Patient",
                                                 10, 20, 100, "Default", False, 40, 100, 100, 35)

        self.placeOrder(self.nextOrderId(), ContractSamples.CSFBContract(), baseOrder)
        # ! [csfb_inline_algo]

    @printWhenExecuting
    def financialAdvisorOperations(self):
        # Requesting FA information ***/
        # ! [requestfaaliases]
        self.requestFA(FaDataTypeEnum.ALIASES)
        # ! [requestfaaliases]

        # ! [requestfagroups]
        self.requestFA(FaDataTypeEnum.GROUPS)
        # ! [requestfagroups]

        # ! [requestfaprofiles]
        self.requestFA(FaDataTypeEnum.PROFILES)
        # ! [requestfaprofiles]

        # Replacing FA information - Fill in with the appropriate XML string. ***/
        # ! [replacefaonegroup]
        self.replaceFA(FaDataTypeEnum.GROUPS, FaAllocationSamples.FaOneGroup)
        # ! [replacefaonegroup]

        # ! [replacefatwogroups]
        self.replaceFA(FaDataTypeEnum.GROUPS, FaAllocationSamples.FaTwoGroups)
        # ! [replacefatwogroups]

        # ! [replacefaoneprofile]
        self.replaceFA(FaDataTypeEnum.PROFILES, FaAllocationSamples.FaOneProfile)
        # ! [replacefaoneprofile]

        # ! [replacefatwoprofiles]
        self.replaceFA(FaDataTypeEnum.PROFILES, FaAllocationSamples.FaTwoProfiles)
        # ! [replacefatwoprofiles]

        # ! [reqSoftDollarTiers]
        self.reqSoftDollarTiers(14001)
        # ! [reqSoftDollarTiers]

    @iswrapper
    # ! [receivefa]
    def receiveFA(self, faData: FaDataType, cxml: str):
        super().receiveFA(faData, cxml)
        print("Receiving FA: ", faData)
        open('log/fa.xml', 'w').write(cxml)

    # ! [receivefa]


    @iswrapper
    # ! [softDollarTiers]
    def softDollarTiers(self, reqId: int, tiers: list):
        super().softDollarTiers(reqId, tiers)
        print("Soft Dollar Tiers:", tiers)

    # ! [softDollarTiers]


    @printWhenExecuting
    def miscelaneous_req(self):
        # Request TWS' current time ***/
        self.reqCurrentTime()
        # Setting TWS logging level  ***/
        self.setServerLogLevel(1)

    @printWhenExecuting
    def linkingOperations(self):
        # ! [querydisplaygroups]
        self.queryDisplayGroups(19001)
        # ! [querydisplaygroups]

        # ! [subscribetogroupevents]
        self.subscribeToGroupEvents(19002, 1)
        # ! [subscribetogroupevents]

        # ! [updatedisplaygroup]
        self.updateDisplayGroup(19002, "8314@SMART")
        # ! [updatedisplaygroup]

        # ! [subscribefromgroupevents]
        self.unsubscribeFromGroupEvents(19002)
        # ! [subscribefromgroupevents]

    @iswrapper
    # ! [displaygrouplist]
    def displayGroupList(self, reqId: int, groups: str):
        super().displayGroupList(reqId, groups)
        print("DisplayGroupList. Request: ", reqId, "Groups", groups)

    # ! [displaygrouplist]


    @iswrapper
    # ! [displaygroupupdated]
    def displayGroupUpdated(self, reqId: int, contractInfo: str):
        super().displayGroupUpdated(reqId, contractInfo)
        print("displayGroupUpdated. Request:", reqId, "ContractInfo:", contractInfo)

    # ! [displaygroupupdated]


    @printWhenExecuting
    def whatIfOrder_req(self):
    # ! [whatiflimitorder]
        whatIfOrder = OrderSamples.LimitOrder("SELL", 5, 70)
        whatIfOrder.whatIf = True
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), whatIfOrder)
    # ! [whatiflimitorder]
        time.sleep(2)


    @printWhenExecuting
    def orderOperations_req(self):
        # Requesting the next valid id ***/
        # ! [reqids]
        # The parameter is always ignored.
        self.reqIds(-1)
        # ! [reqids]

        # Requesting all open orders ***/
        # ! [reqallopenorders]
        self.reqAllOpenOrders()
        # ! [reqallopenorders]

        # Taking over orders to be submitted via TWS ***/
        # ! [reqautoopenorders]
        self.reqAutoOpenOrders(True)
        # ! [reqautoopenorders]

        # Requesting this API client's orders ***/
        # ! [reqopenorders]
        self.reqOpenOrders()
        # ! [reqopenorders]


        # Placing/modifying an order - remember to ALWAYS increment the
        # nextValidId after placing an order so it can be used for the next one!
        # Note if there are multiple clients connected to an account, the
        # order ID must also be greater than all order IDs returned for orders
        # to orderStatus and openOrder to this client.

        # ! [order_submission]
        self.simplePlaceOid = self.nextOrderId()
        self.placeOrder(self.simplePlaceOid, ContractSamples.USStock(),
                        OrderSamples.LimitOrder("SELL", 1, 50))
        # ! [order_submission]

        # ! [faorderoneaccount]
        faOrderOneAccount = OrderSamples.MarketOrder("BUY", 100)
        # Specify the Account Number directly
        faOrderOneAccount.account = "DU119915"
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), faOrderOneAccount)
        # ! [faorderoneaccount]

        # ! [faordergroupequalquantity]
        faOrderGroupEQ = OrderSamples.LimitOrder("SELL", 200, 2000)
        faOrderGroupEQ.faGroup = "Group_Equal_Quantity"
        faOrderGroupEQ.faMethod = "EqualQuantity"
        self.placeOrder(self.nextOrderId(), ContractSamples.SimpleFuture(), faOrderGroupEQ)
        # ! [faordergroupequalquantity]

        # ! [faordergrouppctchange]
        faOrderGroupPC = OrderSamples.MarketOrder("BUY", 0)
        # You should not specify any order quantity for PctChange allocation method
        faOrderGroupPC.faGroup = "Pct_Change"
        faOrderGroupPC.faMethod = "PctChange"
        faOrderGroupPC.faPercentage = "100"
        self.placeOrder(self.nextOrderId(), ContractSamples.EurGbpFx(), faOrderGroupPC)
        # ! [faordergrouppctchange]

        # ! [faorderprofile]
        faOrderProfile = OrderSamples.LimitOrder("BUY", 200, 100)
        faOrderProfile.faProfile = "Percent_60_40"
        self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), faOrderProfile)
        # ! [faorderprofile]

        # ! [modelorder]
        modelOrder = OrderSamples.LimitOrder("BUY", 200, 100)
        modelOrder.account = "DF12345"
        modelOrder.modelCode = "Technology" # model for tech stocks first created in TWS
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), modelOrder)
        # ! [modelorder]

        self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(),
                        OrderSamples.Block("BUY", 50, 20))
        self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(),
                        OrderSamples.BoxTop("SELL", 10))
        self.placeOrder(self.nextOrderId(), ContractSamples.FutureComboContract(),
                        OrderSamples.ComboLimitOrder("SELL", 1, 1, False))
        self.placeOrder(self.nextOrderId(), ContractSamples.StockComboContract(),
                        OrderSamples.ComboMarketOrder("BUY", 1, True))
        self.placeOrder(self.nextOrderId(), ContractSamples.OptionComboContract(),
                        OrderSamples.ComboMarketOrder("BUY", 1, False))
        self.placeOrder(self.nextOrderId(), ContractSamples.StockComboContract(),
                        OrderSamples.LimitOrderForComboWithLegPrices("BUY", 1, [10, 5], True))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.Discretionary("SELL", 1, 45, 0.5))
        self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(),
                        OrderSamples.LimitIfTouched("BUY", 1, 30, 34))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.LimitOnClose("SELL", 1, 34))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.LimitOnOpen("BUY", 1, 35))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketIfTouched("BUY", 1, 30))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketOnClose("SELL", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketOnOpen("BUY", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketOrder("SELL", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketToLimit("BUY", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtIse(),
                        OrderSamples.MidpointMatch("BUY", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.MarketToLimit("BUY", 1))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.Stop("SELL", 1, 34.4))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.StopLimit("BUY", 1, 35, 33))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.StopWithProtection("SELL", 1, 45))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.SweepToFill("BUY", 1, 35))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.TrailingStop("SELL", 1, 0.5, 30))
        self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
                        OrderSamples.TrailingStopLimit("BUY", 1, 2, 5, 50))
        self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtIse(),
                        OrderSamples.Volatility("SELL", 1, 5, 2))

        self.bracketSample()

        self.conditionSamples()

        self.hedgeSample()

        # NOTE: the following orders are not supported for Paper Trading
        # self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), OrderSamples.AtAuction("BUY", 100, 30.0))
        # self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(), OrderSamples.AuctionLimit("SELL", 10, 30.0, 2))
        # self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(), OrderSamples.AuctionPeggedToStock("BUY", 10, 30, 0.5))
        # self.placeOrder(self.nextOrderId(), ContractSamples.OptionAtBOX(), OrderSamples.AuctionRelative("SELL", 10, 0.6))
        # self.placeOrder(self.nextOrderId(), ContractSamples.SimpleFuture(), OrderSamples.MarketWithProtection("BUY", 1))
        # self.placeOrder(self.nextOrderId(), ContractSamples.USStock(), OrderSamples.PassiveRelative("BUY", 1, 0.5))

        # 208813720 (GOOG)
        # self.placeOrder(self.nextOrderId(), ContractSamples.USStock(),
        #    OrderSamples.PeggedToBenchmark("SELL", 100, 33, True, 0.1, 1, 208813720, "ISLAND", 750, 650, 800))

        # STOP ADJUSTABLE ORDERS
        # Order stpParent = OrderSamples.Stop("SELL", 100, 30)
        # stpParent.OrderId = self.nextOrderId()
        # self.placeOrder(stpParent.OrderId, ContractSamples.EuropeanStock(), stpParent)
        # self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), OrderSamples.AttachAdjustableToStop(stpParent, 35, 32, 33))
        # self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), OrderSamples.AttachAdjustableToStopLimit(stpParent, 35, 33, 32, 33))
        # self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), OrderSamples.AttachAdjustableToTrail(stpParent, 35, 32, 32, 1, 0))

        # Order lmtParent = OrderSamples.LimitOrder("BUY", 100, 30)
        # lmtParent.OrderId = self.nextOrderId()
        # self.placeOrder(lmtParent.OrderId, ContractSamples.EuropeanStock(), lmtParent)
        # Attached TRAIL adjusted can only be attached to LMT parent orders.
        # self.placeOrder(self.nextOrderId(), ContractSamples.EuropeanStock(), OrderSamples.AttachAdjustableToTrailAmount(lmtParent, 34, 32, 33, 0.008))
        self.testAlgoSamples()

        # Cancel all orders for all accounts ***/
        # ! [reqglobalcancel]
        self.reqGlobalCancel()
        # ! [reqglobalcancel]

        # Request the day's executions ***/
        # ! [reqexecutions]
        self.reqExecutions(10001, ExecutionFilter())
        # ! [reqexecutions]

    def orderOperations_cancel(self):
        if self.simplePlaceOid is not None:
            # ! [cancelorder]
            self.cancelOrder(self.simplePlaceOid)
            # ! [cancelorder]

    def marketRuleOperations(self):
        self.reqContractDetails(17001, ContractSamples.USStock())
        self.reqContractDetails(17002, ContractSamples.Bond())
		
        time.sleep(1)

        # ! [reqmarketrule]
        self.reqMarketRule(26)
        self.reqMarketRule(240)
        # ! [reqmarketrule]

    @iswrapper
    # ! [execdetails]
    def execDetails(self, reqId: int, contract: Contract, execution: Execution):
        super().execDetails(reqId, contract, execution)
        print("ExecDetails. ", reqId, contract.symbol, contract.secType, contract.currency,
              execution.execId, execution.orderId, execution.shares, execution.lastLiquidity)

    # ! [execdetails]


    @iswrapper
    # ! [execdetailsend]
    def execDetailsEnd(self, reqId: int):
        super().execDetailsEnd(reqId)
        print("ExecDetailsEnd. ", reqId)

    # ! [execdetailsend]


    @iswrapper
    # ! [commissionreport]
    def commissionReport(self, commissionReport: CommissionReport):
        super().commissionReport(commissionReport)
        print("CommissionReport. ", commissionReport.execId, commissionReport.commission,
              commissionReport.currency, commissionReport.realizedPNL)
        # ! [commissionreport]


def main():
    SetupLogger()
    logging.debug("now is %s", datetime.datetime.now())
    logging.getLogger().setLevel(logging.ERROR)

    cmdLineParser = argparse.ArgumentParser("api tests")
    # cmdLineParser.add_option("-c", action="store_True", dest="use_cache", default = False, help = "use the cache")
    # cmdLineParser.add_option("-f", action="store", type="string", dest="file", default="", help="the input file")
    cmdLineParser.add_argument("-p", "--port", action="store", type=int,
                               dest="port", default=7497, help="The TCP port to use")
    cmdLineParser.add_argument("-C", "--global-cancel", action="store_true",
                               dest="global_cancel", default=False,
                               help="whether to trigger a globalCancel req")

    #Roland
    # cmdLineParser.add_argument("-C", "--global-cancel", action="store_true",
    #                            dest="global_cancel", default=False,
    #                            help="whether to trigger a globalCancel req")

    args = cmdLineParser.parse_args()
    print("Using args", args)
    logging.debug("Using args %s", args)
    # print(args)


    # enable logging when member vars are assigned
    from ibapi import utils
    from ibapi.order import Order
    Order.__setattr__ = utils.setattr_log
    from ibapi.contract import Contract, DeltaNeutralContract
    Contract.__setattr__ = utils.setattr_log
    DeltaNeutralContract.__setattr__ = utils.setattr_log
    from ibapi.tag_value import TagValue
    TagValue.__setattr__ = utils.setattr_log
    TimeCondition.__setattr__ = utils.setattr_log
    ExecutionCondition.__setattr__ = utils.setattr_log
    MarginCondition.__setattr__ = utils.setattr_log
    PriceCondition.__setattr__ = utils.setattr_log
    PercentChangeCondition.__setattr__ = utils.setattr_log
    VolumeCondition.__setattr__ = utils.setattr_log

    # from inspect import signature as sig
    # import code code.interact(local=dict(globals(), **locals()))
    # sys.exit(1)

    # tc = KumaroPaperClient(None)
    # tc.reqMktData(1101, ContractSamples.USStockAtSmart(), "", False, None)
    # print(tc.reqId2nReq)
    # sys.exit(1)

    try:
        app = KumaroPaperApp()
        if args.global_cancel:
            app.globalCancelOnly = True
        # ! [connect]
        app.connect("127.0.0.1", args.port, clientId=0)
        # ! [connect]
        print("serverVersion:%s connectionTime:%s" % (app.serverVersion(),
                                                      app.twsConnectionTime()))

        # ! [clientrun]
        app.run()
        # ! [clientrun]
    except:
        raise
    finally:
        app.dumpTestCoverageSituation()
        app.dumpReqAnsErrSituation()


if __name__ == "__main__":
    main()
