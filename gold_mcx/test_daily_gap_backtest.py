import tempfile
import unittest
from datetime import date, time
from pathlib import Path

import pandas as pd
from daily_gap_backtest import build_events, mcx_close_time, metrics


class TestDailyGapBacktest(unittest.TestCase):
    def test_dst_close_times(self):
        self.assertEqual(mcx_close_time(date(2026, 7, 10)), time(23, 30))
        self.assertEqual(mcx_close_time(date(2026, 1, 10)), time(23, 55))

    def test_metrics(self):
        m = metrics(pd.Series([1.0, -0.5, 1.0, -0.25]))
        self.assertEqual(m["trades"], 4)
        self.assertAlmostEqual(m["win_rate_pct"], 50.0)
        self.assertGreater(m["profit_factor"], 1.0)

    def test_event_build_uses_previous_session_volume_leader_and_same_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcx = pd.DataFrame([
                {"date": "2025-01-02", "instrument": "GOLD", "expiry": "DEC", "open": 100,
                 "high": 102, "low": 99, "close": 101, "prev_close": 99, "volume": 100},
                {"date": "2025-01-02", "instrument": "GOLD", "expiry": "JAN", "open": 110,
                 "high": 112, "low": 109, "close": 111, "prev_close": 109, "volume": 50},
                {"date": "2025-01-03", "instrument": "GOLD", "expiry": "DEC", "open": 102,
                 "high": 105, "low": 101, "close": 104, "prev_close": 101, "volume": 80},
                {"date": "2025-01-03", "instrument": "GOLD", "expiry": "JAN", "open": 105,
                 "high": 106, "low": 104, "close": 105, "prev_close": 111, "volume": 10},
            ])
            mcx_path = root / "mcx.csv"
            mcx.to_csv(mcx_path, index=False)
            stamps = pd.date_range("2025-01-02 15:00:00+00:00", "2025-01-03 03:00:00+00:00", freq="1h")
            glob = []
            for inst, base, end in (("GOLD_PROXY", 2000.0, 2020.0), ("USDINR", 85.0, 85.2)):
                for i, ts in enumerate(stamps):
                    px = base + (end - base) * i / max(1, len(stamps) - 1)
                    glob.append({"timestamp": ts.isoformat(), "instrument": inst,
                                 "open": px, "high": px, "low": px, "close": px})
            glob_path = root / "global.csv"
            pd.DataFrame(glob).to_csv(glob_path, index=False)
            events = build_events(str(mcx_path), str(glob_path), max_stale_min=120)
            self.assertEqual(len(events), 1)
            row = events.iloc[0]
            self.assertEqual(row["expiry"], "DEC")
            self.assertAlmostEqual(row["open_gap_pct"], (102 / 101 - 1) * 100)
            self.assertAlmostEqual(row["open_to_close_pct"], (104 / 102 - 1) * 100)


if __name__ == "__main__":
    unittest.main()
