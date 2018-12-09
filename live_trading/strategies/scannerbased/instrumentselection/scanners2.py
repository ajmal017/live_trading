from .scanners1 import Scanners_1, FACTORS

BAR_SIZE_SECS = 10

class FACTORS(FACTORS):
    def __init__(self, *args):
        super(FACTORS, self).__init__(*args)

class Scanners_2(Scanners_1):
    def __init__(self, *args):
        super(Scanners_2, self).__init__(*args)
