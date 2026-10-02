"""Descriptive method and column names used in the reported tables."""
NAMES = {
    'A0-U': 'Join-restricted MILP',
    'A0': 'Global MILP baseline',
    'A1': 'Preprocessed global MILP',
    'A2': 'Preprocessed component MILP',
    'All-U': 'Maximal sharing',
    'All_U': 'Maximal sharing',
    'RG-add': 'Residual greedy addition',
    'RG-prune': 'Residual greedy pruning',
    'Greedy-add': 'Greedy addition',
    'Greedy-prune': 'Greedy pruning',
    'No-sharing': 'Unshared representation',
    'Forest': 'Forest algorithm',
    'LP-on': 'LP with presolve',
    'LP-off': 'LP without presolve',
}

def header(name):
    
    for key, value in NAMES.items():
        name = name.replace(key, value.lower().replace(' ', '_').replace('-', '_'))
    return name

def value(name):
    return ' / '.join(NAMES.get(part.strip(), part.strip()) for part in name.split('/'))
