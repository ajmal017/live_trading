class ConsoleDisplay:
    def __init__(self):
        """
        https://stackoverflow.com/questions/287871/print-in-terminal-with-colors
        """
        self.pd_width = 300 # 'display.width'
        self.pd_column_space = 9 # 'display.column_space'
        self.pd_max_rows = 22 # 'display.max_rows'
        self.pd_max_columns = 10 # 'display.max_columns'

        self.general_print_header = '\033[95m'
        self.general_print_okblue = '\033[94m'
        self.general_print_okgreen = '\033[92m'
        self.general_print_warning = '\033[93m'
        self.general_print_fail = '\033[91m'
        self.general_print_endc = '\033[0m'
        self.general_print_bold = '\033[1m'
        self.general_print_underline = '\033[4m'

    def print_warning(self, _val):
        print(self.general_print_warning, str(_val), self.general_print_endc)
