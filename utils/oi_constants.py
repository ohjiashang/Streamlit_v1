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

FORWARD_CONTRACTS_TO_SKIP = ["Aug25", "Sep25", "Oct25", "Nov25", "Dec25"]

######################################################################

OI_V2_SYMBOLS = ["SMT", "GDK", "STB"]

OI_V2_YEARS = [18, 19, 20, 21, 22, 23, 24, 25, 26]

OI_V2_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

OI_V2_FORWARDS = [
    "Jul25", "Aug25", "Sep25", "Oct25", "Nov25", "Dec25",
    "Jan26", "Feb26", "Mar26", "Apr26", "May26", "Jun26", "Jul26", "Aug26", "Sep26", "Oct26", "Nov26", "Dec26"
]