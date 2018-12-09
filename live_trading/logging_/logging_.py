import datetime
import time
import pickle
import os
import pandas as pd
import numpy as np

class Logging:
    def __init__(self, runtime_tm, log_start, meth_str):
        self.runtime_tm = runtime_tm
        self.log_start = log_start
        self.meth_str = meth_str
        self.logging = True
        self.monitor_toggle = True

    def log(self, *args):
        self.logging_behavior = 'write'#'print write'
        self.saving_behavior = 'folder' #single_file
        self.pickle_obj = []
        if self.logging:
            # self.runtime_tm = str(np.array(pd.DataFrame([[runtime_tm]])).astype(np.int64)[0, 0])
            # self.runtime_tm = str(int(time.time()))
            # log_start_unix_ts = str(np.array(pd.DataFrame([[log_start]])).astype(np.int64)[0, 0])
            log_start_unix_ts = str(float(time.mktime(self.log_start.timetuple())))
            pickle_name = '{}'
            path = str(os.path.dirname(os.path.realpath(__file__))) + '\\..\\log\\'
            dur = datetime.datetime.now() - self.log_start
            dur_microsecs = dur.seconds * 1000000 + dur.microseconds
            line = [log_start_unix_ts, dur_microsecs, self.meth_str, -1]
            if self.logging_behavior == 'write':
                self.pickle_obj.append(line)
            elif self.logging_behavior == 'print':
                print(line)
            if len(args) > 0:
                for arg in args:
                    line = [-1, self.meth_str, -1, arg]
                    if self.logging_behavior == 'write':
                        self.pickle_obj.append(line)
                    elif self.logging_behavior == 'print':
                        print(line)
            if self.logging_behavior == 'print':
                return
            file_name = int(time.mktime(self.runtime_tm.timetuple()))
            dir = os.listdir(path)
            first_log = True if str(file_name) not in dir else False
            if self.saving_behavior == 'folder':
                store_in = path + '\\{}'.format(str(file_name))
                pickle_name2 = str(time.time()).replace('.','')
                if not os.path.exists(store_in):
                    os.makedirs(store_in)
                with open(store_in + '\\{}'.format(pickle_name2), 'wb') as f:
                    pickle.dump(self.pickle_obj, f)
            elif self.saving_behavior == 'single_file':
                if first_log:
                    with open(path + pickle_name.format(str(file_name)), 'wb') as f:
                        pickle.dump(self.pickle_obj, f)
                else:
                    with open(path + str(file_name), 'rb') as p:
                        read_ = pickle.load(p)
                    with open(path + pickle_name.format(str(file_name)), 'wb') as f:
                        store = read_ + self.pickle_obj
                        store2 = np.array(store)
                        pickle.dump(store, f)

    def monitor(self):
        return ('curr_meth', self.meth_str) if self.monitor_toggle else ('curr_meth', '')

    @classmethod
    def reader(cls, file_name):
        path_ = str(os.path.dirname(os.path.realpath(__file__))) + '\\..\\log\\'
        with open(path_ + file_name, 'rb') as p:
            read_ = pickle.load(p)
        return read_, path_

    @classmethod
    def export_csv(cls, file_name):
        read_, path_ = cls.reader(file_name)
        df = pd.DataFrame(read_[0])
        df.to_csv(path_ + str(file_name) + '.csv')

    @classmethod
    def folder_concat_n_export_csv(cls, folder_name):
        path_ = str(os.path.dirname(os.path.realpath(__file__))) + '\\..\\log\\{}\\'.format(str(folder_name))
        # read_, path_ = cls.reader(file_name)
        dir = os.listdir(path_)
        for j, i in enumerate(dir):
            with open(path_ + i, 'rb') as p:
                try:
                    read_ = pickle.load(p)
                except:
                    print('couldnt read')
            if j == 0:
                df = pd.DataFrame(read_)
            else:
                prel_df = pd.DataFrame(read_)
                df = pd.concat([df, prel_df])
        df.to_csv(path_ + str(folder_name) + '.csv')