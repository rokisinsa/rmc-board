import copy, os, shutil, tempfile, unittest
from rmc import core, validate, build

M = {"m1": dict(sport="サッカー", competition="X", start_jst="2026-10-01T20:00:00+09:00", left="A", right="B",
                status="final", result=dict(winner="L", score="2-0", source_rank="league_official",
                                            source_url="https://example.org/r", identity_checked=True))}
E1 = dict(entry_id="r1-1", match_id="m1", market="1X2", selection="A", selection_key="L", stake=100.0,
          odds_taken=1.30, locked_at="2026-10-01T12:00:00+09:00", odds_source="BET CHANNEL", prior_prob=0.82)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = core.DATA
        core.DATA = self.tmp
        core.save("matches.json", copy.deepcopy(M))
        core.save("odds_snapshots.json", [])
        rows = [dict(match_id="m1", status="rejected", reason="格差不足", deep_dive=False)]
        for lg, st in zip(core.LOGICS, ("rejected", "excluded", "excluded", "rejected")):
            core.save(f"analysis/{lg}.json", dict(rows=[dict(rows[0], status=st)]))
            core.save(f"ledger/{lg}.json", [])
        core.save("ledger/experience.json", [])
        core.save("automation-runs.json", [dict(run_id="r", started_at="x", start_sha="abc", status="partial",
                                                blockers=["テスト"], coverage={}, inventory_match_ids=["m1"],
                                                sources=dict(betchannel="ok", kajitabi="確認不能", bet365="確認不能", yuugado="確認不能"))])

    def tearDown(self):
        core.DATA = self.old
        shutil.rmtree(self.tmp)

    def codes(self):
        build.build()
        return {e.split("]")[0][1:] for e in validate.run().errors}


class TestSettlement(Base):
    def test_win_payout(self):
        r = core.settle_entry(E1, M["m1"])
        self.assertEqual(r, dict(outcome="win", payout=130.0, profit=30.0))

    def test_missing_odds_not_zero_or_loss(self):
        e = dict(E1, odds_taken=None, legacy_migrated=True)
        r = core.settle_entry(e, M["m1"])
        self.assertTrue(r["amount_missing"])
        self.assertIsNone(r["payout"])

    def test_compound_reset(self):
        m = {f"m{i}": dict(start_jst=f"2026-10-0{i}T20:00:00+09:00", status="final") for i in range(1, 5)}
        def e(i, o, out):
            return dict(entry_id=str(i), match_id=f"m{i}", stake=100.0, odds_taken=o, locked_at="x", prior_prob=None,
                        result=dict(outcome=out, payout=round(100*o, 2) if out == "win" else 0.0,
                                    profit=round(100*o-100, 2) if out == "win" else -100.0))
        s = core.summarize([e(1, 1.5, "win"), e(2, 1.5, "win"), e(3, 1.2, "win"), e(4, 2.0, "loss")], m)
        c = s["compound"]
        # 100→150→225(倍額到達: ストック125, 100に戻す)→120→負けで失敗、100から再開
        self.assertEqual((c["stock"], c["secured"], c["busted"], c["bankroll"], c["principal"]), (125.0, 1, 1, 100.0, 200.0))
        self.assertEqual(c["net"], 25.0)
        self.assertEqual(s["simple"]["net"], s["net"])

    def test_summary_and_kelly(self):
        e = dict(E1, result=core.settle_entry(E1, M["m1"]))
        s = core.summarize([e], M)
        self.assertEqual((s["win"], s["net"], s["roi"]), (1, 30.0, 30.0))
        self.assertEqual(s["kelly_quarter"]["bets"], 1)
        self.assertGreater(s["kelly_quarter"]["bankroll"], 100)


class TestValidate(Base):
    def test_clean(self):
        self.assertEqual(self.codes(), set())

    def test_result_propagation(self):
        core.save("ledger/r1.json", [E1])
        self.assertIn("RESULT_PROPAGATION", self.codes())

    def test_exact_odds_required(self):
        core.save("ledger/r2.json", [dict(E1, odds_taken=None, odds_range="1.03〜1.06")])
        self.assertIn("EXACT_ODDS", self.codes())

    def test_lock_after_start(self):
        core.save("ledger/r1.json", [dict(E1, locked_at="2026-10-01T20:05:00+09:00",
                                          result=core.settle_entry(E1, M["m1"]))])
        self.assertIn("LOCK_AFTER_START", self.codes())

    def test_settlement_mismatch(self):
        core.save("ledger/r1.json", [dict(E1, result=dict(outcome="win", payout=140.0, profit=40.0))])
        self.assertIn("SETTLEMENT", self.codes())

    def test_screen_incomplete(self):
        core.save("analysis/r3.json", dict(rows=[]))
        self.assertIn("SCREEN_INCOMPLETE", self.codes())

    def test_banned_reason(self):
        core.save("analysis/r2.json", dict(rows=[dict(match_id="m1", status="excluded", reason="no_deep_dive_signal")]))
        self.assertIn("REASON_QUALITY", self.codes())

    def test_formal_needs_deep_dive(self):
        core.save("analysis/r4.json", dict(rows=[dict(match_id="m1", status="accepted", reason="EDGE", deep_dive=False)]))
        self.assertIn("FORMAL_NO_DEEP", self.codes())

    def test_complete_requires_checklist(self):
        runs = core.load("automation-runs.json")
        runs[-1]["status"] = "complete"
        core.save("automation-runs.json", runs)
        self.assertIn("CHECKLIST", self.codes())

    def test_result_source_rank(self):
        m = copy.deepcopy(M); m["m1"]["result"]["source_rank"] = "prediction_site"
        core.save("matches.json", m)
        self.assertIn("RESULT_SOURCE", self.codes())

    def test_profit_audit(self):
        build.build()
        s = core.load("summary.json"); s["logics"]["r1"]["net"] = 999
        core.save("summary.json", s)
        self.assertIn("PROFIT_AUDIT", {e.split("]")[0][1:] for e in validate.run().errors})

    def test_coverage_screen_zero(self):
        runs = core.load("automation-runs.json")
        runs[-1]["coverage"] = {"CS2": dict(event_count=3, priced_upcoming_count=3, r1=dict(screened=0))}
        core.save("automation-runs.json", runs)
        self.assertIn("COVERAGE_SCREEN", self.codes())

    def test_sport_disappeared(self):
        runs = core.load("automation-runs.json")
        prev = dict(runs[-1], coverage={"VALORANT": {}})
        core.save("automation-runs.json", [prev, runs[-1]])
        self.assertIn("SPORT_DISAPPEARED", self.codes())



class TestFacts(unittest.TestCase):
    def test_calc(self):
        from rmc.facts import enrich
        x = enrich({"left": {"name": "A", "form": [
                        {"date": "2026-09-20", "opp": "C", "res": "W", "ha": "H", "units_won": 2, "units_lost": 0},
                        {"opp": "D", "res": "W", "ha": "A", "units_won": 2, "units_lost": 1},
                        {"opp": "E", "res": "L", "ha": "H", "units_won": 1, "units_lost": 2}]},
                    "right": {"name": "B", "form": [{"date": "2026-09-01", "opp": "C", "res": "L"}, {"date": "2025-01-01", "opp": "D", "res": "W"}, {"opp": "E", "res": "W"}]},
                    "h2h": [{"winner": "left", "score": "2-1", "units_left": 2, "units_right": 1, "detail": "6-4 3-6 7-6(5)"}, {"winner": "right", "score": "20-27"}, {"winner": "left", "score": "30-10"}]}, "2026-10-01T20:00:00+09:00")
        c = x["calc"]
        self.assertEqual((c["left"]["W"], c["left"]["L"], c["left"]["units_won"], c["left"]["units_lost"]), (2, 1, 5, 3))
        self.assertEqual(c["left"]["streak"], "2連勝")
        self.assertEqual((c["h2h"]["left"], c["h2h"]["right"]), (2, 1))
        self.assertEqual((c["h2h"]["points_left"], c["h2h"]["points_right"]), (52, 38))
        self.assertEqual((c["h2h"]["units_left"], c["h2h"]["units_right"]), (2, 1))
        self.assertEqual((c["h2h"]["inner_left"], c["h2h"]["inner_right"]), (16, 16))
        self.assertEqual([r["opp"] for r in c["common"]], ["C"])  # D は50日より前、E は日付なしで除外
        self.assertEqual(c["common"][0]["edge"], "left")

    def test_common_history_180(self):
        from rmc.facts import enrich
        x = enrich({"left": {"name": "A", "form": [{"date": "2026-09-20", "opp": "C", "res": "W"}],
                             "history": [{"date": "2026-09-20", "opp": "C", "res": "W"}, {"date": "2026-05-01", "opp": "C", "res": "L"},
                                         {"date": "2026-03-01", "opp": "C", "res": "W"}]},
                    "right": {"name": "B", "form": [{"date": "2026-06-01", "opp": "C", "res": "W"}]}, "h2h": []},
                   "2026-10-01T20:00:00+09:00")
        r = x["calc"]["common"][0]
        # 9/20は form と history の重複で1試合、3/1 は180日より前で除外 → A は2試合1勝1敗
        self.assertEqual((len(r["left"]), r["left_rec"], r["right_rec"], r["edge"]), (2, "1勝1敗", "1勝0敗", "right"))
        self.assertEqual(r["left"][0]["iso"], "2026-09-20")


if __name__ == "__main__":
    unittest.main()
