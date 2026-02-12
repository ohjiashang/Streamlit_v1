import numpy as np
from datetime import datetime

def get_t2_date():
    """Returns the date 2 business days before today."""
    today = np.datetime64('today')
    t2 = np.busday_offset(today, -2)
    return datetime.fromisoformat(str(t2))

def generate_forwards(t2_date, max_year_2digit, include_prompt_month=True):
    """Generate forward contract list from T-2 month onwards through max_year."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    t2_month_idx = t2_date.month - 1  # 0-indexed
    t2_year_2digit = t2_date.year % 100

    start_month_idx = t2_month_idx if include_prompt_month else t2_month_idx + 1
    start_year = t2_year_2digit
    if start_month_idx >= 12:
        start_month_idx = 0
        start_year += 1

    forwards = []
    for year in range(start_year, max_year_2digit + 1):
        start = start_month_idx if year == start_year else 0
        for m in range(start, 12):
            forwards.append(f"{months[m]}{year}")
    return forwards

######################################################################

dct = {
    "S92": ['SMT', 'GDK', 'STB'],
    "Ebob": ['AEO', 'GDK', 'EOB', 'GDO', 'EON'],
    "Rbob": ['RBS', 'RBR', 'GDO', 'UHU'],
    "MOPJ Naph": ['NJC', 'NBG', 'JOE'],
    "NWE Naph": ['NEC', 'JOE', 'NOB', 'EON'],  
}

dist_dct = {
    "SGO": ['GST.J', 'SGB', 'BAP', 'BAQ', 'BAO'],
    "SKO": ['SRS', 'SFF', 'BAQ'],
    "ICEGO": ['GAS', 'ULA', 'ULD', 'ULJ', 'BAP', 'ULM'],
    "NWE Jet": ['JCN', 'JNB', 'ULJ'],
    "HO": ['UHO', 'HOF', 'HBT', 'ULM'],  
}

name_map = {
    'GDK': ['92 EW', 'Lights'],
    'EOB': ['Ebob-Brt', 'Lights'],
    'EON': ['Ebob-NWE Naph', 'Lights'],
    'NBG': ['MOPJ Naph-Brt', 'Lights'],
    'JOE': ['Naph EW', 'Lights'],
    'NOB': ['NWE Naph-Brt', 'Lights'],
    'RBR': ['Rbob-Brt', 'Lights'],
    'GDO': ['Rbob-Ebob', 'Lights'],
    'STB': ['S92-Brt', 'Lights'],
    
    'BAP': ['GO EW', 'Dist'],
    'BAQ': ['Regrade', 'Dist'],
    'BAO': ['SGO-Dub', 'Dist'],
    'SFF': ['SKO-Dub', 'Dist'],
    'SGB': ['SGO-Brt', 'Dist'],
    'ULA': ['ICEGO Swap', 'Dist'],
    'ULD': ['ICEGO-Brt', 'Dist'],
    'ULJ': ['Jet diff', 'Dist'],
}

symbols = [
    'GDK',
    'EOB',
    'EON',
    'NBG',
    'JOE',
    'NOB',
    'RBR',
    'GDO',
    'STB', 
]

dist_symbols = [
    'BAP',
    'BAQ',
    'BAO',
    'SFF',
    'SGB',
    'ULA',
    'ULD',
    'ULJ',

]

product_fam_map_main = {
    "S92": 'Lights',
    "Ebob": 'Lights',
    "Rbob": 'Lights',
    "MOPJ Naph": 'Lights',
    "NWE Naph": 'Lights',  
    "SGO": 'Dist',
    "SKO": 'Dist',
    "ICEGO": 'Dist',
    "NWE Jet": 'Dist',
    "HO": 'Dist',  
}

######################################################################

OI_V2_SYMBOLS = ["SMT", "GDK", "STB"]

OI_V2_YEARS = [18, 19, 20, 21, 22, 23, 24, 25, 26, 27]

OI_V2_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_t2_date = get_t2_date()
_max_year = max(OI_V2_YEARS)
OI_V2_FORWARDS = generate_forwards(_t2_date, _max_year, include_prompt_month=True)
OI_V2_FORWARDS_MOD = generate_forwards(_t2_date, _max_year, include_prompt_month=False)

OI_V2_SPREAD_SYMBOLS = [
    'SMT',
    'AEO',
    'UHU',
    # 'RBS',
    'NJC',
    'NEC',
    'GST.J',
    'GAS',
    'ULA',
    'SRS',
    'JCN',
    'UHO',
    'HOF',
    'MF4',
    'MF3',
    'SYS',
    'BAR',
]