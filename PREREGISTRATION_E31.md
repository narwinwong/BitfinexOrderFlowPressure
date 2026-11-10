# E31: conditional Bitfinex order-flow falsification

## Scope and exposure

Allocate one additional empirical family after the 27-allocation E30 snapshot. Preserve the exhausted original fourteen-family registry, all supplemental allocations and the failed cross-venue clock design. This single-venue test is a distinct hypothesis. No live venue requests or trading.

Use only the previously acquired BitcoinPriceData v1.0 bayesdata_bitfinex.csv.gz: 72,591,413 bytes; SHA256 9883d1e66c87e6694144bea22ee8b5a09af70c5cf3e06884553d453e979665d5. Timestamps and published flash-crash examples are exposed. No raw price or imbalance has been interpreted. Registration precedes strategy outcomes, not acquisition or public literature.

Development is January 1 through June 30, 2015 UTC. July through September prices remain sealed. Skip other dates before converting any non-timestamp field; break before converting the first July row. One financial evaluation invocation after code review and commit; independent offline reconstruction allowed. No new payload or parameter search.

## Mechanism and limitations

Buy-side displayed inventory may precede upward price adjustment as selling liquidity depletes. Gould and Bonart investigate next-tick prediction from best-queue imbalance on Nasdaq, not this archive's top-60-level BTC measure or fixed holding period. This is a related falsification, not replication or an established edge. Source: https://arxiv.org/abs/1512.03492 .

Bitfinex's August 5, 2015 announcement lists a base 20bp taker fee effective August 17. It does not verify January-June fees. The primary 20bp fee is an assumption. Source: https://blog.bitfinex.com/announcements/new-commission-structure/ .

Collector clocks, unknown exchange quote age, missing top sizes, fee currency/rounding, custody and service eligibility prevent executable-edge qualification. Zero imbalance is neutral because genuine balance and fetch failure are indistinguishable. No maker fill, rebate, borrowing or prop-firm claim. Historical archive research does not authorize restricted current venue use.

## Quality gate

Require unchanged source hash and the completed timestamp pilot's exact record count and endpoints. Inside development, require finite positive bid/ask with bid<=ask and finite imbalance in [-1,1]. Count and skip invalid rows without clipping or repair. If invalid fraction exceeds 0.001, stop before policy scoring. Do not discard adverse trades. Prices are already USD per BTC. No confirmation conversion.

## Fixed policy and cash accounting

On a 10-second UTC grid use the latest prior valid row aged at most 5 seconds. While flat without a pending order, signal long when imbalance>=0.5. No short or regime filter. Stop new signals on June 30, reserving the last day for liquidation.

Entry delay d is 10, 30 or 60 seconds; primary 30. Fill at the first eligible grid at or after signal+d. Cancel an entry unfilled more than 120 seconds beyond its target. Do not recheck the signal at execution. Buy 0.01 BTC at ask. Schedule sale 60 seconds after actual entry plus d; use the first eligible bid. Exit never expires: retain delayed exposure through gaps. One position/order maximum; 300-second cooldown after actual exit. A remaining position at July 1 fails completeness; never close using confirmation data or drop it.

Start USD 10,000 cash and no BTC. Buy debit=q*ask*(1+f+s); sale credit=q*bid*(1-f-s). This assumes proportional quote-currency fees and adverse slippage; actual native fee accounting is unverified. Reject unaffordable entries; never replenish cash. No interest or financing. Report cash, inventory, net PnL, capital return, cumulative fees, trades, skipped orders, longest holding period and daily realized PnL attributed to exit day.

## Variant and comparison budget

Twelve cells: delays [10,30,60] seconds and per-leg fees [0,10,20,30]bp, slippage zero. Primary is delay30/fee20. Add one primary cell with 5bp adverse slippage per leg and two primary cells with normal signal noise sd0.05, seeds3101/3102. No clipping noisy signals, price perturbation or winner selection. Total15 cells. Zero fee still pays the spread.

Cash control is zero. Analytic exposure-matched baseline: allocate every completed trade's BTC-seconds over UTC days; qbar=held BTC-seconds/86400. Daily baseline=qbar*(last valid bid-first valid ask), less that cell's fee/slippage on both notionals. This matches daily average inventory, not exact timing, fill size or minimum order. A day without quotes has zero baseline and must be reported. Compare both net PnL and strategy-minus-baseline.

## Statistics and decision

All181 daily values, including zero-trade days. Circular moving-block bootstrap, length7 days, 20,000 resamples, seed3100. Preserve paired strategy/baseline daily values. One-sided lower quantile at 0.05/30 accounts for15 cells times two contrasts. Also report unadjusted95% intervals, active days and daily profit concentration. No IID trade bootstrap or sparse annualized Sharpe.

Development passes only with complete ledger, at least100 trades on60 exit dates, both primary adjusted lower bounds positive, all positive-cost non-noise cells positive in net point PnL and both noisy cells positive. Otherwise stop without retuning, reversal or opening confirmation. Even a conditional pass requires a separately reviewed resolution of execution/fee/size limitations before confirmation. No present-day edge conclusion from2015 quotes.

## Deliverables

Commit protocol, supplemental allocation and independently reviewed implementation before scoring. Meaningful synthetic controls cover causality, order delay/expiry, spread/fees, gaps, sealed dates, cash and reproducible noise. Save aggregate JSON, daily CSV, Python figures, independent ledger reconstruction and original offline replay. Update durable checkpoints and later prepare a privacy-reviewed standalone strategy report repository. No AQRE, protected simulator, Quantower, account or default-branch changes.
