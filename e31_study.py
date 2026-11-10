"""E31 registered conditional screen. No network or confirmation price access."""
from array import array
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
START, END, STEP = 1420070400, 1435708800, 10
DAYS = (END-START)//86400
SOURCE_HASH = '9883d1e66c87e6694144bea22ee8b5a09af70c5cf3e06884553d453e979665d5'
HEADER = b'dateline,last_trade,current_bid,current_ask,book_ratio'


def source_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def load_development(path, require_hash=True):
    if require_hash and source_digest(path) != SOURCE_HASH:
        raise ValueError('Source hash mismatch')
    values = [array('q'), array('d'), array('d'), array('d')]
    seen, invalid, uncompressed = 0, 0, 0
    with gzip.open(path, 'rb') as source:
        if source.readline(4097).rstrip(b'\r\n') != HEADER:
            raise ValueError('Unexpected header')
        while True:
            line = source.readline(4097)
            if not line:
                break
            uncompressed += len(line)
            if len(line)>4096 or uncompressed>2000000000:
                raise ValueError('Registered stream cap exceeded')
            stamp, separator, suffix = line.partition(b',')
            if not separator or not stamp.isdigit():
                raise ValueError('Malformed timestamp')
            t = int(stamp)
            if t < START:
                continue
            if t >= END:
                break  # Never decode this row's price or imbalance suffix.
            seen += 1
            if seen>15000000:
                raise ValueError('Registered row cap exceeded')
            try:
                fields = suffix.rstrip(b'\r\n').split(b',')
                if len(fields)!=4:
                    raise ValueError('Unexpected column count')
                # The first suffix field is last_trade and remains uninterpreted.
                bid, ask, ratio = map(float, fields[1:])
                if not (np.isfinite(bid) and np.isfinite(ask) and np.isfinite(ratio)
                        and 0 < bid <= ask and -1 <= ratio <= 1):
                    raise ValueError('Invalid quote or imbalance')
            except (ValueError, OverflowError):
                invalid += 1
                continue
            for target, value in zip(values, (t,bid,ask,ratio)):
                target.append(value)
    ts, bid, ask, ratio = (np.asarray(a) for a in values)
    if len(ts)==0 or np.any(np.diff(ts)<=0):
        raise ValueError('No usable rows or invalid chronological ordering')
    grid = np.arange(START, END, STEP, dtype=np.int64)
    index = np.searchsorted(ts,grid,side='right')-1
    safe = np.maximum(index,0)
    fresh = (index>=0)&(grid-ts[safe]<=5)
    sampled = [a[safe].copy() for a in (bid,ask,ratio)]
    for a in sampled:
        a[~fresh] = np.nan
    quality = {'development_rows':seen,'invalid_rows':invalid,
               'invalid_fraction':invalid/seen if seen else None,
               'price_quality_gate_passed':bool(seen and invalid/seen<=0.001),
               'valid_rows':len(ts),'first_valid_timestamp':int(ts[0]),
               'last_valid_timestamp':int(ts[-1]),'fresh_grid_points':int(fresh.sum()),
               'confirmation_prices_accessed':False}
    return grid, *sampled, fresh, quality


def daily_baseline(grid,bid,ask,fresh,exposure_seconds,fee_bp,slip_bp):
    result = np.zeros(DAYS)
    no_quote = []
    for day in range(DAYS):
        begin,end = day*8640,(day+1)*8640
        indices = np.flatnonzero(fresh[begin:end])+begin
        if not len(indices):
            no_quote.append(day)
            continue
        qbar = exposure_seconds[day]/86400
        first,last = indices[0],indices[-1]
        cost = (fee_bp+slip_bp)/10000
        result[day]=qbar*(bid[last]*(1-cost)-ask[first]*(1+cost))
    return result,no_quote


def summarize_daily(daily,baseline,resample_indices):
    contrast = daily-baseline
    means = daily[resample_indices].mean(axis=1)
    contrasts = contrast[resample_indices].mean(axis=1)
    alpha = 0.05/30
    return {'mean_daily_pnl_usd':float(daily.mean()),
            'mean_daily_exposure_contrast_usd':float(contrast.mean()),
            'adjusted_lower_cash_usd':float(np.quantile(means,alpha)),
            'adjusted_lower_exposure_usd':float(np.quantile(contrasts,alpha)),
            'unadjusted_95_cash_usd':np.quantile(means,[.025,.975]).tolist(),
            'unadjusted_95_exposure_usd':np.quantile(contrasts,[.025,.975]).tolist(),
            'largest_absolute_day_fraction':float(np.max(np.abs(daily))/np.sum(np.abs(daily))) if np.any(daily) else None}


def plan_cells():
    cells=[{'name':f'd{d}_f{f}','delay':d,'fee_bp':f,'slip_bp':0,'noise_seed':None}
           for d in [10,30,60] for f in [0,10,20,30]]
    cells.append({'name':'d30_f20_slip5','delay':30,'fee_bp':20,'slip_bp':5,'noise_seed':None})
    for seed in [3101,3102]:
        cells.append({'name':f'd30_f20_noise{seed}','delay':30,'fee_bp':20,'slip_bp':0,'noise_seed':seed})
    return cells


def run():
    from e31_engine import simulate
    out=ROOT/'evidence/e31'
    out.mkdir(exist_ok=True)
    with (out/'run_claim.json').open('x',encoding='utf-8') as f:
        json.dump({'started_at':datetime.now(timezone.utc).isoformat()},f)
    binding={'protocol_sha256':source_digest(ROOT/'PREREGISTRATION_E31.md'),
             'engine_sha256':source_digest(ROOT/'e31_engine.py'),
             'study_sha256':source_digest(Path(__file__)),
             'source_sha256':SOURCE_HASH}
    (out/'code_binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    grid,bid,ask,ratio,fresh,quality=load_development(ROOT/'raw_bitcoinpricedata/bayesdata_bitfinex.csv.gz')
    result={'id':'E31','kind':'conditional quote-reference development study',
            'quality':quality,'binding':binding,'cells':[],
            'holdout_opened':False,'verified_edge':False}
    if not quality['price_quality_gate_passed']:
        result['status']='SOURCE_GATE_FAILED_NO_POLICY_SCORING'
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'run_claim.json').write_text(json.dumps({'status':'COMPLETE',
            'finished_at':datetime.now(timezone.utc).isoformat(),'study_status':result['status']})+'\n')
        print(json.dumps(result,indent=2));return
    np.savez_compressed(ROOT/'raw_bitcoinpricedata/e31_development_grid.npz',
                        grid=grid,bid=bid,ask=ask,ratio=ratio,fresh=fresh)
    rng=np.random.default_rng(3100)
    starts=rng.integers(0,DAYS,size=(20000,(DAYS+6)//7))
    indices=((starts[:,:,None]+np.arange(7))%DAYS).reshape(20000,-1)[:,:DAYS]
    daily_columns={}
    for cell in plan_cells():
        sim=simulate(grid,bid,ask,ratio,fresh,delay=cell['delay'],fee_bp=cell['fee_bp'],
                     slip_bp=cell['slip_bp'],noise_seed=cell['noise_seed'])
        daily=np.asarray(sim.pop('realized_daily'),dtype=float)
        total_exposure=np.asarray(sim.pop('exposure_daily'),dtype=float)
        exposure=np.asarray(sim.pop('completed_exposure_daily'),dtype=float)
        days=np.asarray(sim.pop('daily_start_times'))
        if not np.array_equal(days,START+np.arange(DAYS)*86400):
            raise ValueError('Engine daily alignment disagrees with registered window')
        sim['total_exposure_btc_seconds']=float(total_exposure.sum())
        baseline,no_quote=daily_baseline(grid,bid,ask,fresh,exposure,cell['fee_bp'],cell['slip_bp'])
        trades=sim.pop('trades')
        name=cell['name']
        (out/(name+'_trades.json')).write_text(json.dumps(trades)+'\n')
        metrics=summarize_daily(daily,baseline,indices)
        metrics.update({'net_pnl_usd':float(daily.sum()),'capital_return':float(daily.sum()/10000),
                        'completed_trades':len(trades),
                        'exit_dates':len({(t['exit_time']-START)//86400 for t in trades}),
                        'no_quote_baseline_days':no_quote,
                        'baseline_pnl_usd':float(baseline.sum())})
        result['cells'].append({**cell,**sim,**metrics})
        daily_columns[name]=daily;daily_columns[name+'_baseline']=baseline
        daily_columns[name+'_exposure_btc_seconds']=exposure
        print(name,metrics['completed_trades'],metrics['net_pnl_usd'],flush=True)
    primary=next(c for c in result['cells'] if c['name']=='d30_f20')
    positive=[c for c in result['cells'] if c['fee_bp']>0]
    complete=all(not c['unresolved'] and c['cash']>=0 for c in result['cells'])
    passed=bool(complete and primary['completed_trades']>=100 and primary['exit_dates']>=60
                and primary['adjusted_lower_cash_usd']>0 and primary['adjusted_lower_exposure_usd']>0
                and all(c['net_pnl_usd']>0 for c in positive))
    result.update({'status':'CONDITIONAL_DEVELOPMENT_PASS' if passed else 'DEVELOPMENT_FAILED',
                   'development_passed':passed,'ledger_complete':complete,
                   'bootstrap_resamples':20000,'block_days':7,'multiplicity_contrasts':30})
    with (out/'daily.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['date']+list(daily_columns))
        for day in range(DAYS):
            label=datetime.fromtimestamp(START+day*86400,timezone.utc).date().isoformat()
            writer.writerow([label]+[a[day] for a in daily_columns.values()])
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'run_claim.json').write_text(json.dumps({'status':'COMPLETE',
        'finished_at':datetime.now(timezone.utc).isoformat(),'study_status':result['status']})+'\n')
    print(result['status'])


if __name__=='__main__':
    run()
