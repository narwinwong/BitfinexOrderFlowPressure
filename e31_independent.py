"""Independent E31 audit from the development cache; no engine import/network.

Primary policy is reconstructed with eligible-event indices. Other cells are
audited from saved trades, not independently regenerated signal decisions.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
START, END, CUTOFF, Q = 1420070400, 1435708800, 1435622400, 0.01
NDAYS = 181


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def close(actual, expected, tolerance=1e-8):
    if not math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=tolerance):
        raise AssertionError(f'Independent arithmetic mismatch: {actual!r} versus {expected!r}')


def primary_events(grid, bid, ask, ratio, fresh):
    """Search eligible events, rather than iterating the engine's grid states."""
    quotes = np.flatnonzero(fresh)
    signals = np.flatnonzero(fresh & (ratio >= .5) & (grid < CUTOFF))
    quote_times, signal_times = grid[quotes], grid[signals]
    next_signal, cash = START, 10000.0
    output, expired, unaffordable = [], 0, 0
    unresolved = None
    while True:
        cursor = np.searchsorted(signal_times, next_signal)
        if cursor == len(signals):
            break
        signal_index = signals[cursor]
        signal = int(grid[signal_index])
        target = signal + 30
        entry_cursor = np.searchsorted(quote_times, target)
        if entry_cursor == len(quotes) or int(quote_times[entry_cursor]) > target+120:
            # The grid clears an expired order at target+130, then continues.
            # If that point is beyond the available grid, it remains pending.
            if target+130 < END:
                expired += 1
            next_signal = target + 140
            continue
        entry_index = quotes[entry_cursor]
        entry = int(grid[entry_index])
        debit = Q * float(ask[entry_index]) * 1.002
        if debit > cash:
            unaffordable += 1
            next_signal = entry + 10
            continue
        cash -= debit
        exit_cursor = np.searchsorted(quote_times, entry + 90)
        if exit_cursor == len(quotes):
            unresolved = {'entry_time':entry, 'buy_debit':debit}
            break
        exit_index = quotes[exit_cursor]
        exit_time = int(grid[exit_index])
        credit = Q * float(bid[exit_index]) * .998
        cash += credit
        output.append({'signal_time':signal, 'entry_time':entry, 'exit_time':exit_time,
                       'entry_ask':float(ask[entry_index]), 'exit_bid':float(bid[exit_index]),
                       'buy_debit':debit, 'sell_credit':credit, 'pnl':credit-debit})
        next_signal = exit_time + 300
    return output,cash,unresolved,expired,unaffordable


def allocate_exposure(target, start, stop, quantity):
    while start < stop:
        day = (start-START)//86400
        boundary = min(stop, START+(day+1)*86400)
        target[day] += quantity*(boundary-start)
        start = boundary


def audit():
    folder = ROOT/'evidence/e31'
    claim = json.loads((folder/'run_claim.json').read_text())
    if claim.get('status') != 'COMPLETE':
        raise RuntimeError('Main financial run has not completed; no results inspected')
    summary = json.loads((folder/'summary.json').read_text())
    if summary['holdout_opened'] is not False:
        raise AssertionError('Holdout flag changed')
    binding = summary['binding']
    for key,name in [('protocol_sha256','PREREGISTRATION_E31.md'),
                     ('engine_sha256','e31_engine.py'),('study_sha256','e31_study.py')]:
        if digest(ROOT/name) != binding[key]:
            raise AssertionError('Code/protocol binding mismatch: '+name)
    expected_source='9883d1e66c87e6694144bea22ee8b5a09af70c5cf3e06884553d453e979665d5'
    if binding['source_sha256'] != expected_source:
        raise AssertionError('Unexpected registered source binding')
    cache = ROOT/'raw_bitcoinpricedata/e31_development_grid.npz'
    with np.load(cache,allow_pickle=False) as source:
        grid,bid,ask,ratio,fresh=(source[k] for k in ['grid','bid','ask','ratio','fresh'])
    np.testing.assert_array_equal(grid,np.arange(START,END,10,dtype=np.int64))
    if any(a.shape != grid.shape for a in [bid,ask,ratio,fresh]):
        raise AssertionError('Cache alignment mismatch')
    if not np.all(np.isfinite(bid[fresh]) & np.isfinite(ask[fresh]) &
                  np.isfinite(ratio[fresh]) & (bid[fresh]>0) &
                  (bid[fresh]<=ask[fresh]) & (np.abs(ratio[fresh])<=1)):
        raise AssertionError('Invalid eligible cache quote')
    rebuilt,cash,unresolved,expired,rejected=primary_events(grid,bid,ask,ratio,fresh)
    primary=next(c for c in summary['cells'] if c['name']=='d30_f20')
    original=json.loads((folder/'d30_f20_trades.json').read_text())
    if len(original)!=len(rebuilt):
        raise AssertionError('Primary trade-count mismatch')
    for left,right in zip(original,rebuilt):
        for key in ['signal_time','entry_time','exit_time']:
            if left[key]!=right[key]:
                raise AssertionError('Primary event-time mismatch')
        for key in ['entry_ask','exit_bid','buy_debit','sell_credit','pnl']:
            close(left[key],right[key])
    close(primary['cash'],cash)
    if bool(unresolved)!=primary['unresolved'] or expired!=primary['expired_entries'] or rejected!=primary['unaffordable_entries']:
        raise AssertionError('Primary terminal/skip state mismatch')
    with (folder/'daily.csv').open(newline='') as f:
        daily_rows=list(csv.DictReader(f))
    if len(daily_rows)!=NDAYS:
        raise AssertionError('Daily vector length mismatch')
    for day,row in enumerate(daily_rows):
        if row['date']!=datetime.fromtimestamp(START+day*86400,timezone.utc).date().isoformat():
            raise AssertionError('Daily date mismatch')
    generator=np.random.default_rng(3100)
    starts=generator.integers(0,NDAYS,size=(20000,26))
    indices=(np.repeat(starts,7,axis=1)+np.tile(np.arange(7),26))%NDAYS
    indices=indices[:,:NDAYS]
    quote_indices=[np.flatnonzero(fresh[d*8640:(d+1)*8640])+d*8640 for d in range(NDAYS)]
    evidence=[]
    for cell in summary['cells']:
        name=cell['name']
        trades=json.loads((folder/(name+'_trades.json')).read_text())
        cost=(cell['fee_bp']+cell['slip_bp'])/10000
        fee=cell['fee_bp']/10000
        daily=np.zeros(NDAYS); exposure=np.zeros(NDAYS); fees=0.0
        for t in trades:
            if not START<=t['signal_time']<CUTOFF or not START<=t['entry_time']<t['exit_time']<END:
                raise AssertionError('Trade outside registered boundaries')
            close(t['quantity'],Q)
            debit=Q*t['entry_ask']*(1+cost)
            credit=Q*t['exit_bid']*(1-cost)
            transaction_fee=Q*(t['entry_ask']+t['exit_bid'])*fee
            close(t['buy_debit'],debit);close(t['sell_credit'],credit)
            close(t['fees'],transaction_fee);close(t['pnl'],credit-debit)
            daily[(t['exit_time']-START)//86400]+=credit-debit
            allocate_exposure(exposure,t['entry_time'],t['exit_time'],Q)
            fees+=transaction_fee
        held=cell['unresolved_position']
        close(cell['cash'],10000+math.fsum(t['pnl'] for t in trades)-(held['buy_debit'] if held else 0))
        close(cell['cumulative_fees'],fees+(held['entry_fee'] if held else 0))
        baseline=np.zeros(NDAYS)
        for day,valid in enumerate(quote_indices):
            if len(valid):
                baseline[day]=exposure[day]/86400*(bid[valid[-1]]*(1-cost)-ask[valid[0]]*(1+cost))
        stored=np.array([float(r[name]) for r in daily_rows])
        stored_baseline=np.array([float(r[name+'_baseline']) for r in daily_rows])
        stored_exposure=np.array([float(r[name+'_exposure_btc_seconds']) for r in daily_rows])
        np.testing.assert_allclose(daily,stored,rtol=1e-10,atol=1e-9)
        np.testing.assert_allclose(baseline,stored_baseline,rtol=1e-10,atol=1e-9)
        np.testing.assert_allclose(exposure,stored_exposure,rtol=1e-10,atol=1e-8)
        close(cell['net_pnl_usd'],daily.sum())
        close(cell['baseline_pnl_usd'],baseline.sum())
        cash_means=daily[indices].mean(axis=1)
        contrast_means=(daily-baseline)[indices].mean(axis=1)
        lower_cash=float(np.quantile(cash_means,.05/30))
        lower_exposure=float(np.quantile(contrast_means,.05/30))
        close(cell['adjusted_lower_cash_usd'],lower_cash,tolerance=1e-10)
        close(cell['adjusted_lower_exposure_usd'],lower_exposure,tolerance=1e-10)
        np.testing.assert_allclose(cell['unadjusted_95_cash_usd'],np.quantile(cash_means,[.025,.975]),atol=1e-10)
        np.testing.assert_allclose(cell['unadjusted_95_exposure_usd'],np.quantile(contrast_means,[.025,.975]),atol=1e-10)
        evidence.append({'name':name,'trades_audited':len(trades),
                         'net_pnl_usd':float(daily.sum()),'adjusted_lower_cash_usd':lower_cash,
                         'adjusted_lower_exposure_usd':lower_exposure})
    result={'status':'PASS','completed_at':datetime.now(timezone.utc).isoformat(),
            'independent_source_sha256':digest(Path(__file__)),
            'development_cache_sha256':digest(cache),'summary_sha256':digest(folder/'summary.json'),
            'primary_event_algorithm':'eligible-index search; no engine import or grid-state loop',
            'primary_trades_reconstructed':len(rebuilt),'primary_cash_usd':cash,
            'all_cells_ledger_daily_exposure_baseline_and_bounds_verified':True,
            'bootstrap_resamples':20000,'contrasts':30,'cells':evidence,
            'holdout_prices_accessed':False,
            'limits':['Nonprimary signal decisions rely on saved main trades.',
                      'Cache causality relies on the separately reviewed loader; no independent raw-price parse.',
                      'No native fee, positive-size fill, exchange clock or present-day edge validation.']}
    output=folder/'independent.json'
    with output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    audit()
