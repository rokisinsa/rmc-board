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


if __name__ == "__main__":
    unittest.main()
