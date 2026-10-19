"""Unit tests for pcb_checks.py, pcb_calc.py and merge_report.py (stdlib unittest).

Run:  python -m unittest discover -s tests -v
All fixtures are synthetic and generated in a temp folder.
"""
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", ".claude", "skills", "pcb-review", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))

import merge_report  # noqa: E402
import pcb_calc  # noqa: E402
import pcb_checks  # noqa: E402

GERBER_HDR = "%FSLAX25Y25*%\n%MOIN*%\nG01*\n%ADD10C,0.00500*%\n%ADD11R,0.02000X0.03000*%\n"


def gerber(body: str, func: str = "") -> str:
    ff = f"G04 #@! TF.FileFunction,{func}*\n" if func else ""
    return ff + GERBER_HDR + body + "M02*\n"


# 20 x 10 mm board outline, origin at (10 mm, 10 mm) absolute
OUTLINE = ("D10*\nX39370Y39370D02*\nX118110Y39370D01*\nX118110Y78740D01*\n"
           "X39370Y78740D01*\nX39370Y39370D01*\n")
TRACK = "D10*\nX50000Y50000D02*\nX60000Y50000D01*\nD11*\nX70000Y60000D03*\n"

DRILL = """M48
;FILE_FORMAT=2:5
INCH,LZ
;TYPE=PLATED
T01F00S00C0.01181
T02F00S00C0.08661
T03F00S00C0.05000
%
T01
X0050Y0050
X006Y0055
T02
X0100Y0070
M30
"""

BOM = """Item,Qty,Designator,Value,Manufacturer,Manufacturer Part Number,Populate
1,2,"C1, C2",100nF,Murata,GRM188R71H104KA93D,Yes
2,1,R1,10k,Yageo,RC0603FR-0710KL,Yes
3,1,TP1,TP,-,DNP,No
4,2,"R2-R3",1k,Yageo,RC0603FR-071KL,Yes
"""

CPL = """Designator,Mid X,Mid Y,Layer,Rotation
C1,2.0mm,2.0mm,Top,0
C2,4.0mm,2.0mm,Top,90
R1,6.0mm,3.0mm,Top,180
R2,8.0mm,3.0mm,Top,0
R3,9.0mm,3.0mm,Top,0
"""


def make_package(root, cpl=CPL, bom=BOM):
    os.makedirs(os.path.join(root, "fab"), exist_ok=True)
    os.makedirs(os.path.join(root, "asm"), exist_ok=True)
    with zipfile.ZipFile(os.path.join(root, "fab", "gerbers.zip"), "w") as z:
        z.writestr("b.GTL", gerber(TRACK, "Copper,L1,Top"))
        z.writestr("b.GBL", gerber(TRACK, "Copper,L2,Bot"))
        z.writestr("b.GTS", gerber("D11*\nX70000Y60000D03*\n"))
        z.writestr("b.GBS", gerber("D11*\nX70000Y60000D03*\n"))
        z.writestr("b.GTO", gerber(TRACK))
        z.writestr("b.GKO", gerber(OUTLINE))
        z.writestr("b.TXT", DRILL)
    with open(os.path.join(root, "asm", "bom.csv"), "w", encoding="utf-8") as fh:
        fh.write(bom)
    with open(os.path.join(root, "asm", "pick_place.csv"), "w", encoding="utf-8") as fh:
        fh.write(cpl)


def by_id(res, cid, title_part=""):
    return [c for c in res["checks"] if c["id"] == cid and title_part in c["title"]]


class TestParsers(unittest.TestCase):
    def test_gerber_units_bbox_and_min_draw(self):
        g = pcb_checks.parse_gerber(gerber(OUTLINE + TRACK))
        self.assertEqual(g.units, "inch")
        bb = g.bbox_mm()
        self.assertAlmostEqual(bb[0], 10.0, places=2)
        self.assertAlmostEqual(bb[2] - bb[0], 20.0, places=2)
        self.assertAlmostEqual(g.min_draw_mm, 0.127, places=3)
        self.assertEqual(g.flashes, 1)

    def test_excellon_lz_and_hits(self):
        d = pcb_checks.parse_excellon(DRILL)
        self.assertEqual(d.plating, "plated")
        self.assertAlmostEqual(d.tools[1], 0.3, places=3)
        self.assertEqual(d.hits[1], 2)
        self.assertEqual(d.hits[2], 1)
        self.assertEqual(d.hits[3], 0)
        # LZ 2:5: X0050 -> 0.50 inch
        self.assertAlmostEqual(d.bbox[0], 0.5 * 25.4, places=3)

    def test_designator_expansion(self):
        self.assertEqual(pcb_checks.expand_designators("R2-R4, C1"), ["R2", "R3", "R4", "C1"])
        self.assertEqual(pcb_checks.expand_designators("J1 J2"), ["J1", "J2"])

    def test_diffpair_table_is_not_a_bom(self):
        f = pcb_checks.SrcFile("dp.csv", "dp.csv", 0, 0,
                               loader=lambda: b"Pair,Nets,Layer,Reference,Width_mm\nUSB,P/N,L1,L2 GND,0.13\n")
        self.assertIsNone(pcb_checks.parse_bom(f))


class TestPackage(unittest.TestCase):
    def test_clean_package(self):
        with tempfile.TemporaryDirectory() as t:
            make_package(t)
            res = pcb_checks.run_package(t, {"min_drill_mm": 0.15, "min_trace_mm": 0.09}, [], 2)
            self.assertEqual(res["summary"]["FAIL"], 0, json.dumps([c for c in res["checks"] if c["status"] == "FAIL"], indent=1))
            self.assertEqual(by_id(res, "GBR-1")[0]["status"], "PASS")
            self.assertEqual(by_id(res, "XCHK-1")[0]["status"], "PASS")
            outline = by_id(res, "GBR-OUTLINE")[0]
            self.assertAlmostEqual(outline["data"]["w_mm"], 20.0, places=2)
            self.assertEqual(by_id(res, "CPL-BOUNDS")[0]["status"], "PASS")

    def test_missing_cpl_part_and_wrong_layer_count(self):
        with tempfile.TemporaryDirectory() as t:
            make_package(t, cpl=CPL.replace("R3,9.0mm,3.0mm,Top,0\n", ""))
            res = pcb_checks.run_package(t, {}, [], 4)
            self.assertEqual(by_id(res, "XCHK-1")[0]["status"], "FAIL")
            self.assertEqual(by_id(res, "GBR-1")[0]["status"], "FAIL")

    def test_qty_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            make_package(t, bom=BOM.replace("1,2,\"C1, C2\"", "1,3,\"C1, C2\""))
            res = pcb_checks.run_package(t, {}, [], None)
            self.assertEqual(by_id(res, "BOM-1")[0]["status"], "FAIL")

    def test_small_drill_fails_profile(self):
        with tempfile.TemporaryDirectory() as t:
            make_package(t)
            res = pcb_checks.run_package(t, {"min_drill_mm": 0.35}, [], None)
            self.assertEqual(by_id(res, "DRL-1")[0]["status"], "FAIL")

    def test_stale_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            make_package(t)
            cad = os.path.join(t, "cad")
            os.makedirs(cad)
            p = os.path.join(cad, "b.kicad_pcb")
            with open(p, "w") as fh:
                fh.write("(kicad_pcb)")
            future = time.time() + 3600
            os.utime(p, (future, future))
            res = pcb_checks.run_package(t, {}, [], None)
            self.assertEqual(by_id(res, "FRESH-1")[0]["status"], "WARN")


class TestCalc(unittest.TestCase):
    def test_diff_microstrip_close_to_90(self):
        r = pcb_calc.diff_microstrip(0.137, 0.127, 0.0994, 0.035, 4.1)
        self.assertTrue(85 < r["zdiff_ohm"] < 95, r)

    def test_ipc2221_current(self):
        r = pcb_calc.trace_current(0.254, 1, 10)
        self.assertAlmostEqual(r["current_a"], 0.88, delta=0.05)
        w = pcb_calc.trace_width(r["current_a"], 1, 10)
        self.assertAlmostEqual(w["width_mm"], 0.254, delta=0.003)

    def test_contacts(self):
        self.assertEqual(pcb_calc.contacts(1.2, 0.5, 0.7)["contacts_needed"], 4)

    def test_spacing_band(self):
        r = pcb_calc.spacing(70)
        self.assertEqual(r["band_max_v"], 100)
        self.assertEqual(r["min_spacing_mm"]["B4"], 0.13)


def write(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def finding(fid, sev, **kw):
    d = {"id": fid, "severity": sev, "title": f"t {fid}", "evidence": [{"type": "document", "source": "x", "detail": "y"}],
         "recommendation": "fix"}
    d.update(kw)
    return d


class TestMerge(unittest.TestCase):
    def test_gate_rules(self):
        with tempfile.TemporaryDirectory() as run:
            write(os.path.join(run, "findings", "pcb.json"),
                  {"discipline": "pcb", "findings": [finding("PCB-001", "CRITICAL"), finding("PCB-002", "MAJOR"),
                                                    finding("PCB-003", "MINOR")]})
            write(os.path.join(run, "verdicts", "pcb.json"),
                  {"discipline": "pcb", "verdicts": [
                      {"finding_id": "PCB-001", "verdict": "REFUTED", "rationale": "misread"},
                      {"finding_id": "PCB-002", "verdict": "CONFIRMED"},
                      {"finding_id": "PCB-003", "verdict": "UPGRADED", "final_severity": "MAJOR"}],
                   "added_findings": []})
            res = merge_report.merge(run)
            self.assertEqual(res["gate"], "CONDITIONAL")
            self.assertEqual(res["counts"]["refuted"], 1)
            self.assertEqual(res["counts"]["major"], 2)
            # waive both majors -> ready
            write(os.path.join(run, "waivers.json"),
                  [{"id": "PCB-002", "by": "designer", "reason": "accepted"},
                   {"id": "PCB-003", "by": "designer", "reason": "accepted"}])
            self.assertEqual(merge_report.merge(run)["gate"], "READY_FOR_SIGNOFF")

    def test_unverified_critical_blocks(self):
        with tempfile.TemporaryDirectory() as run:
            write(os.path.join(run, "findings", "power.json"), {"findings": [finding("PWR-001", "CRITICAL")]})
            write(os.path.join(run, "verdicts", "power.json"),
                  {"verdicts": [{"finding_id": "PWR-001", "verdict": "UNVERIFIED"}]})
            self.assertEqual(merge_report.merge(run)["gate"], "BLOCKED")

    def test_validation_catches_bad_input(self):
        with tempfile.TemporaryDirectory() as run:
            write(os.path.join(run, "findings", "x.json"), {"findings": [{"id": "X-1", "severity": "HUGE"}]})
            write(os.path.join(run, "verdicts", "x.json"), {"verdicts": [{"finding_id": "X-9", "verdict": "MAYBE"}]})
            _, _, problems = merge_report.validate(run)
            self.assertTrue(any("severity" in p for p in problems))
            self.assertTrue(any("unknown finding" in p for p in problems))
            self.assertTrue(any("MAYBE" in p for p in problems))

    def test_untriaged_auto_fail_is_conditional(self):
        with tempfile.TemporaryDirectory() as run:
            write(os.path.join(run, "findings", "manufacturing.json"), {"findings": []})
            write(os.path.join(run, "evidence", "auto_checks.json"),
                  {"checks": [{"id": "DRL-0", "title": "Drill files present", "status": "FAIL"}]})
            self.assertEqual(merge_report.merge(run)["gate"], "CONDITIONAL")
            write(os.path.join(run, "findings", "manufacturing.json"),
                  {"findings": [], "auto_check_triage": [{"check": "DRL-0", "disposition": "false_positive"}]})
            self.assertEqual(merge_report.merge(run)["gate"], "READY_FOR_SIGNOFF")


if __name__ == "__main__":
    unittest.main()
