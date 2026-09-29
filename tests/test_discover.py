import inspect, unittest
from rmc import discover as d


def form(res, score_w="2-0", score_l="0-2"):
    return [{"date": f"2026-09-{20 - i:02d}", "opp": f"X{i}", "res": r, "score": score_w if r == "W" else score_l if r == "L" else "1-1"}
            for i, r in enumerate(res)]


M = {"sport": "サッカー", "competition": "U21", "left": "A", "right": "B", "start_jst": "2026-09-30T03:00:00+09:00"}


class TestDiscover(unittest.TestCase):
    def test_no_odds_in_screening(self):
        for f in (d.indicators, d.screen, d.decide, d.run_screen):
            self.assertNotIn("odds", inspect.signature(f).parameters)

    def test_single_side_streak_triggers(self):
        fx = {"left": {"form": form("WWWWWDLWDW")}, "right": {"form": form("WLWDWLWDLW")}}
        hits, n = d.screen(M, d.indicators(M, fx, {}))
        keys = {h["key"] for h in hits}
        self.assertIn("streak_w5", keys)            # 5連勝だけで発火（相手の5連敗は不要）
        self.assertTrue(n >= 10)

    def test_rating_first(self):
        m = dict(M, sport="CS2")
        fx = {"left": {"form": form("WLWLW")}, "right": {"form": form("LWLWL")},
              "metrics": {"left": {"elo": 1500, "rank": 5}, "right": {"elo": 1450, "rank": 90}}}
        hits, _ = d.screen(m, d.indicators(m, fx, {}))
        self.assertNotIn("rank_diff", {h["key"] for h in hits})   # Elo が取れているので順位差は使わない

    def test_starter_unconfirmed(self):
        m = dict(M, sport="野球")
        fx = {"metrics": {"left": {"starter_fip": 2.5, "starter_confirmed": False}, "right": {"starter_fip": 5.0, "starter_confirmed": True}}}
        ind = d.indicators(m, fx, {})
        self.assertEqual(ind["fip_diff"]["unavailable"], "先発未確定")

    def test_cricket_format_separated(self):
        m = dict(M, sport="クリケット", competition="International / ODI's")
        fx = {"left": {"form": [dict(g, comp="T20I") for g in form("WWWWWWWW")]}, "right": {"form": form("LLLLLLLL")}}
        ind = d.indicators(m, fx, {})
        self.assertIn("unavailable", ind["last10_wr_diff"])       # T20I の成績を ODI に混ぜない

    def test_decide_grades(self):
        fx = {"left": {"form": form("WWWWWWWWLW")}, "right": {"form": form("LLLLLWLLDL")},
              "h2h": [{"winner": "left", "score": "3-0"}, {"winner": "left", "score": "2-0"}, {"winner": "left", "score": "4-1"}],
              "counter_evidence": {k: {"impact": "none", "finding": "確認：該当なし"} for k in d.COUNTER_KEYS}}
        ind = d.indicators(M, fx, {})
        hits, _ = d.screen(M, ind)
        r = d.decide(M, ind, hits, fx)
        self.assertEqual(r["grade"], "A")
        self.assertTrue(r["support"])
        fx["counter_evidence"]["主力欠場"] = {"impact": "minor", "finding": "主将欠場"}
        self.assertEqual(d.decide(M, ind, hits, fx)["grade"], "B")
        fx["counter_evidence"]["主力欠場"] = {"impact": "major", "finding": "主力5人欠場"}
        self.assertEqual(d.decide(M, ind, hits, fx)["status"], "反対材料で保留")

    def test_verify_does_not_change_grade(self):
        scr = {"rows": [dict(match_id="m1", status="格差候補確定", grade="A", side="L"),
                        dict(match_id="m2", status="該当なし")]}
        odds = [{"match_id": "m1", "taken_at": "t", "source": "s", "prices": {"L": 3.0, "R": 1.4}},
                {"match_id": "m2", "taken_at": "t", "source": "s", "prices": {"L": 1.05, "R": 9.0}}]
        d.verify(scr, odds)
        self.assertEqual(scr["rows"][0]["grade"], "A")
        self.assertFalse(scr["rows"][0]["market"]["agrees"])
        self.assertEqual(scr["rows"][1]["market_only"]["grade"], "C")

    def test_table_tennis_split(self):
        self.assertEqual(d.group_of({"sport": "卓球", "competition": "Ukraine / Setka Cup"}), "卓球（Setka Cup等の独立・下位大会）")
        self.assertEqual(d.group_of({"sport": "卓球", "competition": "WTT Champions"}), "卓球（国際/WTT）")


if __name__ == "__main__":
    unittest.main()
