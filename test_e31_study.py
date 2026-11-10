import gzip
from pathlib import Path
import tempfile
import unittest
import numpy as np
from e31_study import load_development,HEADER,START,END,plan_cells,daily_baseline

class StudyControls(unittest.TestCase):
    def test_sealed_rows_are_not_converted(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample.gz'
            with gzip.open(p,'wb') as f:
                f.write(HEADER+b'\n')
                f.write(f'{START-1},bad,bad,bad,bad\n'.encode())
                f.write(f'{START},bad,100,101,0.6\n'.encode())
                f.write(f'{END},NEVER,CONVERT,THIS,SUFFIX\n'.encode())
            grid,bid,ask,ratio,fresh,q=load_development(p,require_hash=False)
            self.assertEqual(q['development_rows'],1)
            self.assertTrue(fresh[0]);self.assertFalse(fresh[1])
            self.assertEqual(bid[0],100)
            self.assertFalse(q['confirmation_prices_accessed'])
    def test_variant_budget(self):
        cells=plan_cells()
        self.assertEqual(len(cells),15)
        self.assertEqual(len({c['name'] for c in cells}),15)
    def test_exposure_baseline_pays_spread_and_fees(self):
        grid=np.array([START,START+10]);fresh=np.ones(2,dtype=bool)
        exposure=np.zeros(181);exposure[0]=86400
        baseline,_=daily_baseline(grid,np.array([99.,109.]),np.array([100.,110.]),fresh,exposure,20,0)
        self.assertAlmostEqual(baseline[0],109*.998-100*1.002)

if __name__=='__main__':unittest.main()
