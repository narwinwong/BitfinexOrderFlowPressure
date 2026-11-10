"""Pure E31 hypothetical grid ledger; accepts arrays, never reads market files."""
import math

import numpy as np

INITIAL_CASH = 10000.0
QUANTITY = 0.01
ENTRY_CUTOFF = 1435622400  # 2015-06-30 00:00 UTC
DAY = 86400


def simulate(grid, bid, ask, imbalance, fresh, delay, fee_bp,
             slip_bp=0, noise_seed=None):
    """Simulate the preregistered policy on already causal, aligned quote arrays.

    ``fresh`` must already encode validity and source age. No quote is filled
    from a future row. Unresolved holdings remain unpriced terminal inventory.
    Daily exposure includes open holdings; a separate completed-only vector
    implements the protocol's analytic baseline allocation.
    """
    grid = np.asarray(grid)
    if (grid.ndim != 1 or not len(grid) or grid.dtype.kind not in "iu"
            or np.any(grid % 10) or np.any(np.diff(grid) != 10)):
        raise ValueError("Expected a nonempty consecutive 10-second integer grid")
    grid = grid.astype(np.int64, copy=False)
    bid, ask, imbalance = [np.asarray(v, dtype=float) for v in (bid, ask, imbalance)]
    fresh = np.asarray(fresh)
    if fresh.dtype.kind != "b" or any(v.shape != grid.shape for v in (bid, ask, imbalance, fresh)):
        raise ValueError("Aligned quote arrays and a boolean freshness mask required")
    if np.any(fresh & (~np.isfinite(bid) | ~np.isfinite(ask)
                       | ~np.isfinite(imbalance) | (bid <= 0) | (ask < bid)
                       | (np.abs(imbalance) > 1))):
        raise ValueError("Fresh quotes must satisfy E31's price/imbalance gate")
    if type(delay) is not int or delay not in (10, 30, 60):
        raise ValueError("Registered delays are 10, 30 and 60 seconds")
    if (not math.isfinite(fee_bp) or not math.isfinite(slip_bp)
            or fee_bp < 0 or slip_bp < 0 or fee_bp + slip_bp >= 10000):
        raise ValueError("Nonnegative finite proportional costs below 100% required")
    if noise_seed is not None and type(noise_seed) is not int:
        raise ValueError("Noise seed must be an integer or None")

    f, s = fee_bp / 10000.0, slip_bp / 10000.0
    noise = (np.random.default_rng(noise_seed).normal(0, 0.05, len(grid))
             if noise_seed is not None else None)
    first_day = int(grid[0]) // DAY * DAY
    end = int(grid[-1]) + 10
    n_days = (end - 1 - first_day) // DAY + 1
    day_grid = first_day + np.arange(n_days, dtype=np.int64) * DAY
    realized = np.zeros(n_days)
    exposure = np.zeros(n_days)
    completed_exposure = np.zeros(n_days)

    def allocate_exposure(start, stop, target):
        while start < stop:
            day_index = (start - first_day) // DAY
            boundary = first_day + (day_index + 1) * DAY
            segment_end = min(stop, boundary)
            target[day_index] += QUANTITY * (segment_end - start)
            start = segment_end

    cash = INITIAL_CASH
    pending = None
    held = None
    cooldown_until = int(grid[0])
    trades = []
    expired_entries = unaffordable_entries = 0
    total_fees = total_slippage = 0.0

    for i, raw_t in enumerate(grid):
        t = int(raw_t)
        if held is not None:
            if t >= held["exit_target"] and fresh[i]:
                proceeds = QUANTITY * float(bid[i])
                exit_fee, exit_slip = proceeds * f, proceeds * s
                credit = proceeds - exit_fee - exit_slip
                cash += credit
                trade = {**held, "exit_time": t, "exit_bid": float(bid[i]),
                         "sell_credit": credit, "exit_fee": exit_fee,
                         "exit_slippage": exit_slip,
                         "fees": held["entry_fee"] + exit_fee,
                         "pnl": credit - held["buy_debit"],
                         "holding_seconds": t - held["entry_time"]}
                trades.append(trade)
                total_fees += exit_fee
                total_slippage += exit_slip
                realized[(t - first_day) // DAY] += trade["pnl"]
                allocate_exposure(held["entry_time"], t, exposure)
                allocate_exposure(held["entry_time"], t, completed_exposure)
                held = None
                cooldown_until = t + 300
            continue  # No same-grid entry after a sale.

        if pending is not None:
            if t > pending["target"] + 120:
                expired_entries += 1
                pending = None
            elif t >= pending["target"] and fresh[i]:
                notional = QUANTITY * float(ask[i])
                entry_fee, entry_slip = notional * f, notional * s
                debit = notional + entry_fee + entry_slip
                if debit > cash:
                    unaffordable_entries += 1
                else:
                    cash -= debit
                    total_fees += entry_fee
                    total_slippage += entry_slip
                    held = {"signal_time": pending["signal_time"],
                            "signal_imbalance": pending["signal_imbalance"],
                            "entry_time": t, "entry_ask": float(ask[i]),
                            "quantity": QUANTITY, "buy_debit": debit,
                            "entry_fee": entry_fee, "entry_slippage": entry_slip,
                            "exit_target": t + 60 + delay}
                pending = None
            continue  # No same-grid resubmission after expiry or cash rejection.

        if t >= ENTRY_CUTOFF or t < cooldown_until or not fresh[i]:
            continue
        signal = float(imbalance[i]) + (float(noise[i]) if noise is not None else 0.0)
        if signal >= 0.5:
            pending = {"signal_time": t, "signal_imbalance": signal,
                       "target": t + delay}

    if held is not None:
        allocate_exposure(held["entry_time"], end, exposure)
    realized_total = math.fsum(t["pnl"] for t in trades)
    remaining_debit = held["buy_debit"] if held is not None else 0.0
    expected_cash = INITIAL_CASH + realized_total - remaining_debit
    if not math.isclose(cash, expected_cash, rel_tol=1e-11, abs_tol=1e-7):
        raise ArithmeticError("Cash ledger does not reconcile")
    completed_holds = [t["holding_seconds"] for t in trades]
    all_holds = completed_holds + ([end - held["entry_time"]] if held else [])
    return {"trades": trades, "terminal_cash": cash, "cash": cash,
            "terminal_btc": QUANTITY if held is not None else 0.0,
            "terminal_cash_change": cash - INITIAL_CASH,
            "realized_pnl": realized_total,
            "unresolved_position": held, "pending_entry": pending,
            "unresolved": held is not None,
            "complete_ledger": held is None,
            "expired_entries": expired_entries,
            "unaffordable_entries": unaffordable_entries,
            "cumulative_fees": total_fees, "cumulative_slippage": total_slippage,
            "max_completed_holding_seconds": max(completed_holds, default=0),
            "max_holding_seconds": max(all_holds, default=0),
            "daily_start_times": day_grid, "realized_daily": realized,
            "exposure_daily": exposure,
            "completed_exposure_daily": completed_exposure}
