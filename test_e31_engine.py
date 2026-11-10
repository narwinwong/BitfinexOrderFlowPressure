"""Fabricated array controls only; no historical source reads."""
import unittest

import numpy as np

from e31_engine import ENTRY_CUTOFF, INITIAL_CASH, QUANTITY, simulate

START = 1420070400


def arrays(seconds=1000, start=START):
    grid = np.arange(start, start + seconds, 10, dtype=np.int64)
    return (grid, np.full(len(grid), 99.0), np.full(len(grid), 101.0),
            np.zeros(len(grid)), np.ones(len(grid), dtype=bool))


class E31EngineControls(unittest.TestCase):
    def test_entry_delay_no_signal_recheck_and_exit_delay(self):
        g, b, a, im, fresh = arrays(200)
        im[0] = .8
        a[0] = 1.0  # The signal quote cannot supply the delayed fill.
        b[0] = .9
        a[3] = 102.0
        b[12] = 105.0
        a[12] = 106.0
        out = simulate(g, b, a, im, fresh, 30, 0)
        trade = out["trades"][0]
        self.assertEqual(trade["entry_time"], START + 30)
        self.assertEqual(trade["entry_ask"], 102)
        self.assertEqual(trade["exit_time"], START + 120)
        self.assertAlmostEqual(trade["pnl"], .03)

    def test_spread_two_sided_fees_and_slippage_cash_reconcile(self):
        g, b, a, im, fresh = arrays(200)
        im[0] = 1
        out = simulate(g, b, a, im, fresh, 10, 20, 5)
        self.assertEqual(len(out["trades"]), 1)
        expected = .01 * (99 * .9975 - 101 * 1.0025)
        self.assertAlmostEqual(out["realized_pnl"], expected)
        self.assertAlmostEqual(out["terminal_cash"], INITIAL_CASH + expected)
        self.assertAlmostEqual(out["cumulative_fees"], .01 * 200 * .002)
        self.assertAlmostEqual(out["cumulative_slippage"], .01 * 200 * .0005)
        self.assertEqual(out["terminal_btc"], 0)

    def test_entry_expires_without_using_late_quote(self):
        g, b, a, im, fresh = arrays(300)
        im[0] = 1
        fresh[1:15] = False
        out = simulate(g, b, a, im, fresh, 10, 20)
        self.assertEqual(out["expired_entries"], 1)
        self.assertEqual(out["trades"], [])
        self.assertEqual(out["terminal_cash"], INITIAL_CASH)

    def test_exact_expiry_boundary_can_fill(self):
        g, b, a, im, fresh = arrays(300)
        im[0] = 1
        fresh[1:13] = False
        out = simulate(g, b, a, im, fresh, 10, 0)
        self.assertEqual(out["trades"][0]["entry_time"], START + 130)
        self.assertEqual(out["expired_entries"], 0)

    def test_exit_gap_retains_inventory_and_cross_day_exposure(self):
        g, b, a, im, fresh = arrays(300, START + 86300)
        im[0] = 1
        fresh[8:16] = False
        out = simulate(g, b, a, im, fresh, 10, 0)
        self.assertEqual(out["trades"][0]["exit_time"], int(g[16]))
        self.assertEqual(out["max_holding_seconds"], 150)
        np.testing.assert_allclose(out["exposure_daily"], [.9, .6])
        np.testing.assert_allclose(out["completed_exposure_daily"], [.9, .6])
        self.assertEqual(out["realized_daily"][0], 0)
        self.assertAlmostEqual(out["realized_daily"][1], -.02)

    def test_unresolved_inventory_not_discarded_or_marked_as_cash_profit(self):
        g, b, a, im, fresh = arrays(100)
        im[0] = 1
        fresh[8:] = False
        out = simulate(g, b, a, im, fresh, 10, 20)
        self.assertFalse(out["complete_ledger"])
        self.assertEqual(out["terminal_btc"], QUANTITY)
        self.assertEqual(out["realized_pnl"], 0)
        self.assertAlmostEqual(out["terminal_cash"], INITIAL_CASH - 1.01202)
        self.assertAlmostEqual(sum(out["exposure_daily"]), .9)
        self.assertEqual(sum(out["completed_exposure_daily"]), 0)

    def test_cooldown_blocks_immediate_reentry(self):
        g, b, a, im, fresh = arrays(600)
        im[:] = 1
        out = simulate(g, b, a, im, fresh, 10, 0)
        self.assertEqual(out["trades"][0]["exit_time"], START + 80)
        self.assertEqual(out["trades"][1]["signal_time"], START + 380)

    def test_june30_no_new_signals_but_existing_position_closes(self):
        g, b, a, im, fresh = arrays(300, ENTRY_CUTOFF - 20)
        im[:] = 1
        out = simulate(g, b, a, im, fresh, 10, 0)
        self.assertEqual(len(out["trades"]), 1)
        self.assertGreater(out["trades"][0]["exit_time"], ENTRY_CUTOFF)
        self.assertIsNone(out["pending_entry"])

    def test_insufficient_cash_rejects_without_replenishment(self):
        g, b, a, im, fresh = arrays(200)
        im[0] = 1
        a[1] = 2_000_000
        out = simulate(g, b, a, im, fresh, 10, 20)
        self.assertEqual(out["unaffordable_entries"], 1)
        self.assertEqual(out["terminal_cash"], INITIAL_CASH)
        self.assertEqual(out["trades"], [])

    def test_noise_is_per_grid_reproducible_and_not_clipped(self):
        g, b, a, im, fresh = arrays(5000)
        im[:] = .49
        first = simulate(g, b, a, im, fresh, 30, 20, noise_seed=3101)
        second = simulate(g, b, a, im, fresh, 30, 20, noise_seed=3101)
        other = simulate(g, b, a, im, fresh, 30, 20, noise_seed=3102)
        self.assertEqual(first["trades"], second["trades"])
        self.assertNotEqual(first["trades"], other["trades"])
        self.assertTrue(first["trades"])

    def test_invalid_fresh_input_cannot_supply_fill(self):
        g, b, a, im, fresh = arrays(100)
        a[1] = np.nan
        with self.assertRaises(ValueError):
            simulate(g, b, a, im, fresh, 10, 20)
        fresh[1] = False
        simulate(g, b, a, im, fresh, 10, 20)


if __name__ == "__main__":
    unittest.main()
