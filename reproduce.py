"""Reproduce the frozen E31 numerical study in a new, offline workspace."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True,type=Path,help='Original bayesdata_bitfinex.csv.gz')
    parser.add_argument('--output',type=Path,default=Path('replay_workspace'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    h=hashlib.sha256()
    with args.data.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    if h.hexdigest()!='9883d1e66c87e6694144bea22ee8b5a09af70c5cf3e06884553d453e979665d5':
        raise ValueError('Exact original archive required; source hash disagrees')
    work=args.output.resolve()
    work.mkdir(exist_ok=False)
    (work/'raw_bitcoinpricedata').mkdir()
    (work/'evidence').mkdir();(work/'figures').mkdir()
    for name in ['e31_engine.py','e31_study.py','e31_independent.py','e31_figures.py','PREREGISTRATION_E31.md']:
        shutil.copyfile(root/name,work/name)
    shutil.copyfile(args.data,work/'raw_bitcoinpricedata/bayesdata_bitfinex.csv.gz')
    for name in ['e31_study.py','e31_independent.py','e31_figures.py']:
        subprocess.run([sys.executable,name],cwd=work,check=True)
    original=json.loads((root/'evidence/e31/summary.json').read_text())
    rebuilt=json.loads((work/'evidence/e31/summary.json').read_text())
    if rebuilt['status']!=original['status'] or rebuilt['holdout_opened']:
        raise AssertionError('Disposition or sealed-date mismatch')
    expected={f'd{d}_f{f}' for d in [10,30,60] for f in [0,10,20,30]}
    expected.update(['d30_f20_slip5','d30_f20_noise3101','d30_f20_noise3102'])
    for result in [original,rebuilt]:
        if len(result['cells'])!=15 or {c['name'] for c in result['cells']}!=expected:
            raise AssertionError('Missing, duplicate or unexpected registered cells')
    fields=['net_pnl_usd','completed_trades','exit_dates','baseline_pnl_usd',
            'adjusted_lower_cash_usd','adjusted_lower_exposure_usd']
    for left,right in zip(original['cells'],rebuilt['cells']):
        if left['name']!=right['name']:raise AssertionError('Cell identity mismatch')
        for key in fields:
            if not math.isclose(left[key],right[key],rel_tol=1e-9,abs_tol=1e-8):
                raise AssertionError('Reproduction mismatch: '+left['name']+' '+key)
    print('PASS: all 15 frozen numerical cases and independent audit reproduced offline')


if __name__=='__main__':main()
