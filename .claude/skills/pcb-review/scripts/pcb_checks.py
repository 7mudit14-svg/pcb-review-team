#!/usr/bin/env python3
"""pcb_checks.py - deterministic screening checks for a PCB release package.

Standard library only. Reads Gerber (RS-274X / X2), Excellon drill, BOM and
pick-and-place (CPL) files from a package folder, as loose files or inside
.zip archives, and writes auto_checks.json and auto_checks.md.

These are screening checks, not a DRC. They catch missing, empty or stale
files, BOM/CPL mismatches and gross fab-capability problems. Copper geometry
(clearance, impedance, return paths) still needs the EDA tool's DRC and the
human or agent reviewers.

Usage:
  python pcb_checks.py package --package DIR --out DIR
         [--profile FILE.json] [--cad DIR ...] [--layers N] [--strict]
  python pcb_checks.py text PDF [PDF ...] --out DIR      (needs pypdf)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, field

MM_PER_INCH = 25.4

# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

STATUS_ORDER = {"FAIL": 0, "WARN": 1, "INFO": 2, "PASS": 3, "SKIP": 4}


@dataclass
class Check:
    id: str
    title: str
    status: str  # PASS / WARN / FAIL / INFO / SKIP
    detail: str = ""
    data: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Package walking
# --------------------------------------------------------------------------

@dataclass
class SrcFile:
    name: str          # display path, e.g. "fab/gerbers.zip!board.GTL"
    base: str          # base file name
    mtime: float
    size: int
    loader: object = field(repr=False, default=None)

    def text(self) -> str:
        raw = self.loader()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", errors="replace")

    def bytes(self) -> bytes:
        return self.loader()


SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "History", "__Previews"}
OUTPUT_DIR_RE = re.compile(r"(project outputs|^outputs?$|_archive|backup|^history$)", re.I)


def walk_package(root: str) -> list[SrcFile]:
    out: list[SrcFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            st = os.stat(full)
            if fn.lower().endswith(".zip"):
                try:
                    zf = zipfile.ZipFile(full)
                except zipfile.BadZipFile:
                    continue
                for zi in zf.infolist():
                    if zi.is_dir():
                        continue
                    mt = time.mktime(zi.date_time + (0, 0, -1))
                    out.append(SrcFile(
                        name=f"{rel}!{zi.filename}", base=os.path.basename(zi.filename),
                        mtime=mt, size=zi.file_size,
                        loader=(lambda z=zf, n=zi.filename: z.read(n))))
            else:
                out.append(SrcFile(name=rel, base=fn, mtime=st.st_mtime, size=st.st_size,
                                   loader=(lambda p=full: open(p, "rb").read())))
    return out


# --------------------------------------------------------------------------
# Gerber
# --------------------------------------------------------------------------

# Extension -> (function, side). Altium/Protel names first, then KiCad suffixes.
PROTEL_EXT = {
    "gtl": ("copper", "top"), "gbl": ("copper", "bottom"),
    "gto": ("silk", "top"), "gbo": ("silk", "bottom"),
    "gts": ("mask", "top"), "gbs": ("mask", "bottom"),
    "gtp": ("paste", "top"), "gbp": ("paste", "bottom"),
    "gko": ("keepout", ""), "gml": ("outline", ""),
    "gpt": ("padmaster", "top"), "gpb": ("padmaster", "bottom"),
}
KICAD_SUFFIX = [
    (r"[-_]F[._]Cu$", ("copper", "top")), (r"[-_]B[._]Cu$", ("copper", "bottom")),
    (r"[-_]In(\d+)[._]Cu$", ("copper", "inner")),
    (r"[-_]F[._]Mask$", ("mask", "top")), (r"[-_]B[._]Mask$", ("mask", "bottom")),
    (r"[-_]F[._]Silk(S|screen)$", ("silk", "top")), (r"[-_]B[._]Silk(S|screen)$", ("silk", "bottom")),
    (r"[-_]F[._]Paste$", ("paste", "top")), (r"[-_]B[._]Paste$", ("paste", "bottom")),
    (r"[-_]Edge[._]Cuts$", ("outline", "")),
]
GERBER_EXTS = {"gbr", "ger", "pho", "art"} | set(PROTEL_EXT)
DRILL_EXTS = {"drl", "xln", "exc", "nc", "txt", "tap", "drd"}
CAD_EXTS = (".pcbdoc", ".schdoc", ".kicad_pcb", ".kicad_sch", ".brd", ".sch", ".prjpcb", ".kicad_pro")


def classify_gerber(f: SrcFile, text_head: str) -> tuple[str, str]:
    """Return (function, side) for a Gerber file, or ("", "") if unknown."""
    m = re.search(r"TF\.FileFunction,([^*%]+)", text_head)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        fn = parts[0].lower()
        if fn == "copper":
            side = parts[2].lower() if len(parts) > 2 else ""
            side = {"top": "top", "bot": "bottom", "inr": "inner"}.get(side, side)
            return "copper", side
        if fn in ("soldermask", "solder mask"):
            return "mask", "top" if "top" in m.group(1).lower() else "bottom"
        if fn == "legend":
            return "silk", "top" if "top" in m.group(1).lower() else "bottom"
        if fn == "paste":
            return "paste", "top" if "top" in m.group(1).lower() else "bottom"
        if fn == "profile":
            return "outline", ""
        return fn, ""
    stem, ext = os.path.splitext(f.base)
    ext = ext[1:].lower()
    if ext in PROTEL_EXT:
        return PROTEL_EXT[ext]
    if re.fullmatch(r"g\d+", ext) or re.fullmatch(r"gp\d+", ext):
        return "copper", "inner"
    if re.fullmatch(r"gm\d+", ext):
        return "mechanical", ext.upper()
    if re.fullmatch(r"g[dg]\d+", ext):
        return "drilldrawing", ""
    for pat, res in KICAD_SUFFIX:
        if re.search(pat, stem, re.I):
            return res
    return "", ""


@dataclass
class GerberInfo:
    units: str = "?"
    fmt: tuple = (2, 4)
    zero: str = "L"
    draws: int = 0
    flashes: int = 0
    regions: int = 0
    arcs: int = 0
    bbox: list = field(default_factory=lambda: [math.inf, math.inf, -math.inf, -math.inf])
    min_draw_mm: float = math.inf
    apertures: int = 0
    file_function: str = ""
    errors: list = field(default_factory=list)

    def bbox_mm(self):
        if self.bbox[0] == math.inf:
            return None
        return [round(v, 4) for v in self.bbox]


def _gnum(s: str, fmt: tuple, zero: str) -> float:
    if "." in s:
        return float(s)
    neg = s.startswith("-")
    s = s.lstrip("+-")
    ints, decs = fmt
    if zero == "T":  # trailing zeros kept -> left aligned
        s = s.ljust(ints + decs, "0")
    v = int(s) / (10 ** decs) if s else 0.0
    return -v if neg else v


def parse_gerber(text: str) -> GerberInfo:
    g = GerberInfo()
    ff = re.search(r"TF\.FileFunction,([^*%]+)", text)
    if ff:
        g.file_function = ff.group(1)
    # extended commands
    ext_blocks = re.findall(r"%([^%]*)%", text, re.S)
    ap_size: dict[int, float] = {}
    for blk in ext_blocks:
        blk = blk.replace("\r", "").replace("\n", "")
        for cmd in blk.split("*"):
            if cmd.startswith("FS"):
                m = re.match(r"FS([LTD])?A?X(\d)(\d)Y(\d)(\d)", cmd)
                if m:
                    g.zero = m.group(1) or "L"
                    g.fmt = (int(m.group(2)), int(m.group(3)))
            elif cmd.startswith("MO"):
                g.units = "mm" if "MM" in cmd else "inch"
            elif cmd.startswith("AD"):
                m = re.match(r"ADD(\d+)([A-Za-z_][\w.$]*)(?:,([\d.Xx]+))?", cmd)
                if m:
                    g.apertures += 1
                    code, shape, params = int(m.group(1)), m.group(2), m.group(3)
                    size = math.inf
                    if params:
                        vals = [float(v) for v in re.split(r"[Xx]", params) if v]
                        if shape == "C" and vals:
                            size = vals[0]
                        elif shape in ("R", "O") and len(vals) >= 2:
                            size = min(vals[0], vals[1])
                    ap_size[code] = size
    body = re.sub(r"%[^%]*%", "", text, flags=re.S)
    if g.units == "?":
        if re.search(r"G71", body):
            g.units = "mm"
        elif re.search(r"G70", body):
            g.units = "inch"
    scale = MM_PER_INCH if g.units == "inch" else 1.0
    x = y = 0.0
    cur_ap = None
    last_op = 2
    in_region = False
    for raw in body.replace("\r", "").replace("\n", "").split("*"):
        cmd = raw.strip()
        if not cmd or cmd.startswith("G04"):
            continue
        if "G36" in cmd:
            in_region = True
            g.regions += 1
        if "G37" in cmd:
            in_region = False
        if cmd in ("M02", "M00"):
            break
        m_ap = re.fullmatch(r"(?:G54)?D(\d+)", cmd)
        if m_ap and int(m_ap.group(1)) >= 10:
            cur_ap = int(m_ap.group(1))
            continue
        coords = re.findall(r"([XYIJ])([+-]?[\d.]+)", cmd)
        dm = re.search(r"D0?([123])$", cmd)
        op = int(dm.group(1)) if dm else (last_op if coords else None)
        if "G02" in cmd or "G03" in cmd:
            g.arcs += 1
        if not coords and op is None:
            continue
        for k, v in coords:
            try:
                val = _gnum(v, g.fmt, g.zero) * scale
            except ValueError:
                g.errors.append(f"bad number {v}")
                continue
            if k == "X":
                x = val
            elif k == "Y":
                y = val
        if op is None:
            continue
        last_op = op
        if op in (1, 3) or (op == 2 and in_region):
            bb = g.bbox
            bb[0], bb[1] = min(bb[0], x), min(bb[1], y)
            bb[2], bb[3] = max(bb[2], x), max(bb[3], y)
        if op == 1 and not in_region:
            g.draws += 1
            if cur_ap is not None:
                s = ap_size.get(cur_ap, math.inf)
                if s > 0:
                    g.min_draw_mm = min(g.min_draw_mm, s * scale)
        elif op == 3:
            g.flashes += 1
    return g


# --------------------------------------------------------------------------
# Excellon
# --------------------------------------------------------------------------

@dataclass
class DrillInfo:
    units: str = "inch"
    fmt: tuple = (2, 4)
    zeros: str = "LZ"
    plating: str = "unknown"
    tools: dict = field(default_factory=dict)      # tool -> diameter mm
    hits: dict = field(default_factory=dict)       # tool -> count
    slots: int = 0
    bbox: list = field(default_factory=lambda: [math.inf, math.inf, -math.inf, -math.inf])


def _xnum(s: str, fmt: tuple, zeros: str) -> float:
    if "." in s:
        return float(s)
    neg = s.startswith("-")
    s = s.lstrip("+-")
    ints, decs = fmt
    if zeros == "LZ":   # leading zeros kept, trailing suppressed -> left aligned
        v = int(s) / (10 ** (len(s) - ints)) if s else 0.0
    else:               # TZ: trailing kept, leading suppressed -> right aligned
        v = int(s) / (10 ** decs) if s else 0.0
    return -v if neg else v


def parse_excellon(text: str, name: str = "") -> DrillInfo:
    d = DrillInfo()
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    m = re.search(r"FILE_FORMAT\s*=\s*(\d):(\d)", text)
    explicit_fmt = bool(m)
    if m:
        d.fmt = (int(m.group(1)), int(m.group(2)))
    if re.search(r"TYPE\s*=\s*NON[_ ]?PLATED", text, re.I) or re.search(r"NPTH|non[-_ ]?plated", name, re.I):
        d.plating = "non-plated"
    elif re.search(r"TYPE\s*=\s*PLATED", text, re.I) or re.search(r"(^|[-_])PTH", name, re.I):
        d.plating = "plated"
    in_header = True
    cur = None
    x = y = 0.0
    for ln in lines:
        if not ln or ln.startswith(";"):
            continue
        u = ln.upper()
        if in_header:
            if u.startswith("METRIC") or u.startswith("INCH"):
                d.units = "mm" if u.startswith("METRIC") else "inch"
                if ",TZ" in u:
                    d.zeros = "TZ"
                elif ",LZ" in u:
                    d.zeros = "LZ"
                if not explicit_fmt:
                    d.fmt = (3, 3) if d.units == "mm" else (2, 4)
            elif u in ("M71",):
                d.units = "mm"
            elif u in ("M72",):
                d.units = "inch"
            tm = re.match(r"T(\d+)(?:F\d+)?(?:S\d+)?C([\d.]+)", u)
            if tm:
                dia = float(tm.group(2)) * (MM_PER_INCH if d.units == "inch" else 1.0)
                d.tools[int(tm.group(1))] = round(dia, 4)
                d.hits.setdefault(int(tm.group(1)), 0)
                continue
            if u in ("%", "M95"):
                in_header = False
            continue
        tm = re.fullmatch(r"T(\d+)", u)
        if tm:
            cur = int(tm.group(1))
            continue
        if u.startswith("M30"):
            break
        if "G85" in u:
            d.slots += 1
        cm = re.findall(r"([XY])([+-]?[\d.]+)", u)
        if cm and cur is not None:
            for k, v in cm:
                val = _xnum(v, d.fmt, d.zeros) * (MM_PER_INCH if d.units == "inch" else 1.0)
                if k == "X":
                    x = val
                else:
                    y = val
            d.hits[cur] = d.hits.get(cur, 0) + 1
            bb = d.bbox
            bb[0], bb[1], bb[2], bb[3] = min(bb[0], x), min(bb[1], y), max(bb[2], x), max(bb[3], y)
    return d


# --------------------------------------------------------------------------
# CSV helpers (BOM / CPL)
# --------------------------------------------------------------------------

def read_rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]


DESIG_RE = re.compile(r"^(designators?|references?|refdes|ref\.? ?des(ignator)?s?|part ?references?|ref)$", re.I)


def find_header(rows: list[list[str]], must: list[re.Pattern]) -> int:
    for i, r in enumerate(rows[:40]):
        cells = [c.strip().strip('"') for c in r]
        if all(any(p.search(c) for c in cells) for p in must):
            return i
    return -1


def col(header: list[str], pat: str) -> int:
    rx = re.compile(pat, re.I)
    for i, h in enumerate(header):
        if rx.search(h.strip().strip('"')):
            return i
    return -1


def expand_designators(s: str) -> list[str]:
    out = []
    for tok in re.split(r"[,;\s]+", s.strip().strip('"')):
        if not tok:
            continue
        m = re.fullmatch(r"([A-Za-z_]+)(\d+)\s*-\s*(?:[A-Za-z_]+)?(\d+)", tok)
        if m and int(m.group(3)) >= int(m.group(2)) and int(m.group(3)) - int(m.group(2)) < 500:
            out += [f"{m.group(1)}{n}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            out.append(tok)
    return out


DNP_RE = re.compile(r"^(no|n|false|0|dnp|dni|dnf|nf|not ?fitted|not ?placed|do not (place|populate|fit))$", re.I)


@dataclass
class Bom:
    name: str
    rows: int = 0
    populated: dict = field(default_factory=dict)   # designator -> row number
    dnp: set = field(default_factory=set)
    qty_mismatch: list = field(default_factory=list)
    dup: list = field(default_factory=list)
    missing_mpn: list = field(default_factory=list)
    has_mpn_col: bool = False
    has_qty_col: bool = False


def parse_bom(f: SrcFile) -> Bom | None:
    rows = read_rows(f.text())
    hi = find_header(rows, [DESIG_RE])
    if hi < 0:
        return None
    hdr = rows[hi]
    c_des = next(i for i, h in enumerate(hdr) if DESIG_RE.search(h.strip().strip('"')))
    c_qty = col(hdr, r"^(qty|quantity|qnty)$")
    c_mpn = col(hdr, r"(manufacturer ?part|mfr\.? ?(part|p/?n)|^mpn$|part ?number|^lcsc|supplier ?part)")
    c_pop = col(hdr, r"(populate|fitted|dnp|dni|assemble|^mount|install)")
    c_val = col(hdr, r"^(value|comment|val)$")
    c_fp = col(hdr, r"(footprint|package|pattern)")
    if max(c_qty, c_mpn, c_val, c_fp, col(hdr, r"^(manufacturer|mfr|mfg)")) < 0:
        return None  # a designator-like column alone is not a BOM (e.g. a diff-pair table)
    b = Bom(name=f.name, has_mpn_col=c_mpn >= 0, has_qty_col=c_qty >= 0)
    seen: dict[str, int] = {}
    for rn, r in enumerate(rows[hi + 1:], start=hi + 2):
        if len(r) <= c_des or not r[c_des].strip():
            continue
        des = expand_designators(r[c_des])
        if not des:
            continue
        b.rows += 1
        pop_cell = r[c_pop] if 0 <= c_pop < len(r) else ""
        val_cell = r[c_val] if 0 <= c_val < len(r) else ""
        mpn_cell = r[c_mpn] if 0 <= c_mpn < len(r) else ""
        is_dnp = bool(DNP_RE.match(pop_cell.strip())) or bool(re.search(r"\bDNP\b|\bDNF\b|\bDNI\b", val_cell + " " + mpn_cell))
        if c_qty >= 0 and c_qty < len(r):
            try:
                q = float(r[c_qty])
                if abs(q - len(des)) > 1e-6:
                    b.qty_mismatch.append({"row": rn, "qty": q, "designators": len(des)})
            except ValueError:
                pass
        for d in des:
            if d in seen:
                b.dup.append({"designator": d, "rows": [seen[d], rn]})
            seen[d] = rn
            if is_dnp:
                b.dnp.add(d)
            else:
                b.populated[d] = rn
        if not is_dnp and c_mpn >= 0 and not mpn_cell.strip():
            b.missing_mpn.append({"row": rn, "designators": des})
    return b


@dataclass
class Cpl:
    name: str
    units: str = "mm"
    parts: dict = field(default_factory=dict)   # designator -> (x_mm, y_mm, rot, layer)
    dup: list = field(default_factory=list)
    bad_rows: list = field(default_factory=list)


X_RE = re.compile(r"^(mid ?x|center-?x|centre-?x|pos ?x|ref ?x|x|x ?pos(ition)?|location ?x)(\s*\(.*\))?$", re.I)
Y_RE = re.compile(r"^(mid ?y|center-?y|centre-?y|pos ?y|ref ?y|y|y ?pos(ition)?|location ?y)(\s*\(.*\))?$", re.I)


def _len_mm(cell: str, default_units: str) -> float:
    c = cell.strip().strip('"').lower()
    unit = default_units
    if c.endswith("mm"):
        c, unit = c[:-2], "mm"
    elif c.endswith("mil"):
        c, unit = c[:-3], "mil"
    elif c.endswith("in"):
        c, unit = c[:-2], "inch"
    v = float(c)
    return v if unit == "mm" else v * 0.0254 if unit == "mil" else v * MM_PER_INCH


def parse_cpl(f: SrcFile) -> Cpl | None:
    text = f.text()
    rows = read_rows(text)
    hi = find_header(rows, [DESIG_RE, X_RE, Y_RE])
    if hi < 0:
        return None
    hdr = [h.strip().strip('"') for h in rows[hi]]
    c_des = next(i for i, h in enumerate(hdr) if DESIG_RE.search(h))
    c_x = next(i for i, h in enumerate(hdr) if X_RE.search(h))
    c_y = next(i for i, h in enumerate(hdr) if Y_RE.search(h))
    c_rot = col(hdr, r"^(rotation|rot|angle)")
    c_lay = col(hdr, r"^(layer|side|tb|mount ?side)$")
    units = "mm"
    hx = hdr[c_x].lower()
    if "mil" in hx:
        units = "mil"
    elif "(in" in hx:
        units = "inch"
    m = re.search(r"Units used:\s*(mm|mil|inch)", text, re.I)
    if m and "(" not in hx:
        units = m.group(1).lower()
    c = Cpl(name=f.name, units=units)
    for rn, r in enumerate(rows[hi + 1:], start=hi + 2):
        if len(r) <= max(c_des, c_x, c_y) or not r[c_des].strip():
            continue
        try:
            x = _len_mm(r[c_x], units)
            y = _len_mm(r[c_y], units)
        except ValueError:
            c.bad_rows.append(rn)
            continue
        rot = r[c_rot] if 0 <= c_rot < len(r) else ""
        lay = r[c_lay] if 0 <= c_lay < len(r) else ""
        d = r[c_des].strip().strip('"')
        if d in c.parts:
            c.dup.append(d)
        c.parts[d] = (round(x, 4), round(y, 4), rot, lay)
    return c


# --------------------------------------------------------------------------
# Reports from EDA tools
# --------------------------------------------------------------------------

def parse_altium_drc_html(text: str) -> dict:
    """Total violation count plus the per-rule summary table of an Altium DRC report."""
    def clean(c):
        return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
    flat = clean(text)
    m = re.search(r"Rule Violations\s*:?\s*(\d+)", flat)
    total = int(m.group(1)) if m else None
    rules = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = [clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if len(cells) >= 2 and cells[-1].isdigit() and not cells[0].lower().startswith("total")                 and re.search(r"constraint|rule|clearance|width|hole|silk|mask|antenna|height|short|routed|"
                              r"polygon|plane|differential|length", cells[0], re.I):
            rules.append({"rule": cells[0][:200], "count": int(cells[-1])})
        if len(rules) >= 80:
            break
    return {"total_violations": total, "rules": rules,
            "violating_rules": [r for r in rules if r["count"] > 0]}


def parse_kicad_drc(text: str) -> dict:
    m = re.search(r"Found (\d+) DRC violations", text)
    u = re.search(r"Found (\d+) unconnected", text)
    if text.lstrip().startswith("{"):
        try:
            j = json.loads(text)
            return {"total_violations": len(j.get("violations", [])),
                    "unconnected": len(j.get("unconnected_items", []))}
        except json.JSONDecodeError:
            pass
    return {"total_violations": int(m.group(1)) if m else None,
            "unconnected": int(u.group(1)) if u else None}


# --------------------------------------------------------------------------
# Main package check
# --------------------------------------------------------------------------

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def fmt_mm(v):
    return "n/a" if v in (None, math.inf) else f"{v:.3f} mm"


def run_package(pkg: str, profile: dict, cad_dirs: list[str], expect_layers: int | None) -> dict:
    checks: list[Check] = []
    files = walk_package(pkg)
    inv = {"gerber": [], "drill": [], "bom": [], "cpl": [], "drc": [], "cad": [], "docs": [], "other": []}
    gerbers: dict[str, tuple[SrcFile, GerberInfo, str, str]] = {}
    drills: list[tuple[SrcFile, DrillInfo]] = []
    boms: list[Bom] = []
    cpls: list[Cpl] = []
    drc_reports = []

    for f in files:
        low = f.base.lower()
        ext = os.path.splitext(low)[1][1:]
        if low.endswith(CAD_EXTS):
            inv["cad"].append(f.name)
            continue
        if ext in ("htm", "html") and ("drc" in low or "design rule check" in low):
            try:
                drc_reports.append((f, parse_altium_drc_html(f.text())))
                inv["drc"].append(f.name)
            except Exception as e:  # noqa: BLE001
                checks.append(Check("DRC-PARSE", f"Could not parse {f.name}", "INFO", str(e)))
            continue
        if ext in ("rpt", "json") and "drc" in low:
            drc_reports.append((f, parse_kicad_drc(f.text())))
            inv["drc"].append(f.name)
            continue
        if ext in ("csv", "tsv"):
            b = None
            c = parse_cpl(f)
            if c and c.parts:
                cpls.append(c)
                inv["cpl"].append(f.name)
                continue
            b = parse_bom(f)
            if b and b.rows:
                boms.append(b)
                inv["bom"].append(f.name)
                continue
            inv["other"].append(f.name)
            continue
        if ext in ("xlsx", "xls"):
            inv["other"].append(f.name)
            checks.append(Check("BOM-XLSX", f"Spreadsheet not parsed: {f.name}", "INFO",
                                "Export BOM/CPL as CSV for automatic cross-checks."))
            continue
        if ext in GERBER_EXTS or re.fullmatch(r"g\d+|gp\d+|gm\d+|g[dg]\d+", ext or "-"):
            txt = f.text()
            if not txt.lstrip().startswith("M48"):
                fn, side = classify_gerber(f, txt[:6000])
                gi = parse_gerber(txt)
                gerbers[f.name] = (f, gi, fn, side)
                inv["gerber"].append(f.name)
                continue
        if ext in DRILL_EXTS:
            txt = f.text()
            if txt.lstrip().startswith("M48") or re.search(r"^T\d+C[\d.]+", txt, re.M):
                drills.append((f, parse_excellon(txt, f.base)))
                inv["drill"].append(f.name)
                continue
        if ext in ("pdf", "md", "docx", "html", "htm", "png", "jpg", "svg", "step", "stp"):
            inv["docs"].append(f.name)
        else:
            inv["other"].append(f.name)

    checks.append(Check("INV-1", "Package inventory", "INFO",
                        ", ".join(f"{k}: {len(v)}" for k, v in inv.items()), {"inventory": inv}))

    # ---------------- Gerbers ----------------
    if not gerbers:
        checks.append(Check("GBR-0", "Gerber files present", "FAIL", "No Gerber files found in the package."))
    else:
        by_fn: dict[str, list] = {}
        for name, (f, gi, fn, side) in gerbers.items():
            by_fn.setdefault(fn or "unknown", []).append((name, side, gi))
        copper = by_fn.get("copper", [])
        sides = [s for _, s, _ in copper]
        n_cu = len(copper)
        detail = f"{n_cu} copper layer(s): " + ", ".join(sorted(f"{os.path.basename(n)}({s})" for n, s, _ in copper))
        st = "PASS"
        if "top" not in sides or "bottom" not in sides:
            st = "FAIL"
            detail += " - top or bottom copper missing"
        if expect_layers and n_cu != expect_layers:
            st = "FAIL"
            detail += f" - expected {expect_layers}"
        if profile.get("max_layers") and n_cu > profile["max_layers"]:
            st = "FAIL"
            detail += f" - profile allows {profile['max_layers']}"
        checks.append(Check("GBR-1", "Copper layer set", st, detail, {"copper_layers": n_cu}))

        for fn_req, label in (("mask", "Solder mask"), ("silk", "Silkscreen"), ("paste", "Paste")):
            got = sorted(s for _, s, _ in by_fn.get(fn_req, []))
            checks.append(Check(f"GBR-{fn_req.upper()}", f"{label} layers", "PASS" if got else "WARN",
                                ", ".join(got) if got else f"No {label.lower()} Gerber found."))

        outline = by_fn.get("outline", []) + by_fn.get("keepout", [])
        if not outline:
            outline = [o for o in by_fn.get("mechanical", []) if o[1] in ("GM1", "GM2")]
        board_bbox = None
        if outline:
            # choose outline with the largest bbox
            cand = [(n, gi.bbox_mm()) for n, _, gi in outline if gi.bbox_mm()]
            if cand:
                n, bb = max(cand, key=lambda c: (c[1][2] - c[1][0]) * (c[1][3] - c[1][1]))
                board_bbox = bb
                w, h = bb[2] - bb[0], bb[3] - bb[1]
                st = "INFO"
                det = f"{os.path.basename(n)}: {w:.2f} x {h:.2f} mm (bbox of outline vertices)"
                mx = profile.get("max_board_mm")
                mn = profile.get("min_board_mm")
                if mx and (max(w, h) > max(mx) or min(w, h) > min(mx)):
                    st, det = "FAIL", det + f" - exceeds profile max {mx}"
                if mn and (w < mn[0] or h < mn[1]):
                    st, det = "WARN", det + f" - below profile min {mn} (may need panelization)"
                checks.append(Check("GBR-OUTLINE", "Board outline", st, det,
                                    {"outline_file": n, "bbox_mm": bb, "w_mm": round(w, 3), "h_mm": round(h, 3)}))
        else:
            checks.append(Check("GBR-OUTLINE", "Board outline", "FAIL",
                                "No outline / profile Gerber found (Edge.Cuts, GKO, GM1 or TF.FileFunction,Profile)."))

        empties = [os.path.basename(n) for n, (f, gi, fn, s) in gerbers.items()
                   if gi.draws + gi.flashes + gi.regions == 0 and fn in ("copper", "mask", "outline", "keepout")]
        checks.append(Check("GBR-EMPTY", "No empty copper/mask/outline files", "WARN" if empties else "PASS",
                            ", ".join(empties) if empties else "All have content."))

        units = sorted({gi.units for _, (f, gi, fn, s) in gerbers.items()})
        fmts = sorted({f"{gi.fmt[0]}:{gi.fmt[1]}" for _, (f, gi, fn, s) in gerbers.items()})
        checks.append(Check("GBR-FMT", "Gerber units/format consistent",
                            "PASS" if len(units) == 1 and len(fmts) == 1 else "WARN",
                            f"units {units}, format {fmts}"))

        min_tr = min((gi.min_draw_mm for _, s, gi in copper), default=math.inf)
        lim = profile.get("min_trace_mm")
        st = "INFO"
        det = f"Smallest round/rect aperture used for copper draws: {fmt_mm(min_tr)}"
        if lim and min_tr != math.inf:
            if min_tr < lim - 0.002:
                st, det = "WARN", det + f" - below profile min trace {lim} mm (check if it is a track or a pad/region artefact)"
            elif min_tr < lim + 0.01:
                det += f" - at the profile minimum ({lim} mm); expect fab yield/cost remarks"
        checks.append(Check("GBR-MINTRACE", "Minimum copper draw width (screening)", st, det,
                            {"min_draw_mm": None if min_tr == math.inf else round(min_tr, 4)}))
        per_layer = {os.path.basename(n): {"function": fn, "side": s, "units": gi.units, "draws": gi.draws,
                                           "flashes": gi.flashes, "regions": gi.regions,
                                           "min_draw_mm": None if gi.min_draw_mm == math.inf else round(gi.min_draw_mm, 4),
                                           "bbox_mm": gi.bbox_mm()}
                     for n, (f, gi, fn, s) in gerbers.items()}
        checks.append(Check("GBR-LAYERS", "Per-layer Gerber statistics", "INFO", f"{len(per_layer)} files", per_layer))
    # ---------------- Drill ----------------
    board_bbox = next((c.data["bbox_mm"] for c in checks if c.id == "GBR-OUTLINE" and c.data.get("bbox_mm")), None)
    if not drills:
        checks.append(Check("DRL-0", "Drill files present", "FAIL", "No Excellon drill file found."))
    else:
        all_tools = []
        for f, di in drills:
            for t, dia in di.tools.items():
                all_tools.append({"file": os.path.basename(f.name), "tool": t, "dia_mm": dia,
                                  "hits": di.hits.get(t, 0), "plating": di.plating})
        total_hits = sum(t["hits"] for t in all_tools)
        used = [t for t in all_tools if t["hits"] > 0]
        min_d = min((t["dia_mm"] for t in used), default=None)
        lim = profile.get("min_drill_mm")
        st = "PASS"
        det = f"{total_hits} hits, {len(used)} tool size(s): " + ", ".join(
            f"{t['dia_mm']:.3f} mm x{t['hits']} ({t['plating']})" for t in sorted(used, key=lambda t: t["dia_mm"]))
        if lim and min_d is not None and min_d + 1e-6 < lim:
            st, det = "FAIL", det + f" - smallest {min_d:.3f} mm below profile min {lim} mm"
        checks.append(Check("DRL-1", "Drill table", st, det, {"tools": all_tools, "min_drill_mm": min_d}))
        unused = [t for t in all_tools if t["hits"] == 0]
        if unused:
            checks.append(Check("DRL-UNUSED", "Unused drill tools", "INFO",
                                ", ".join(f"T{t['tool']} {t['dia_mm']} mm" for t in unused)))
        if board_bbox:
            out = []
            for f, di in drills:
                if di.bbox[0] != math.inf:
                    bb = di.bbox
                    if bb[0] < board_bbox[0] - 0.05 or bb[1] < board_bbox[1] - 0.05 or \
                       bb[2] > board_bbox[2] + 0.05 or bb[3] > board_bbox[3] + 0.05:
                        out.append(os.path.basename(f.name))
            checks.append(Check("DRL-BOUNDS", "Drill hits inside board outline (bbox)", "FAIL" if out else "PASS",
                                ("Outside: " + ", ".join(out)) if out else "All drill hits within the outline bounding box. "
                                "(Bounding-box test only; notches/cut-outs are not checked.)"))
        if all(di.plating == "unknown" for _, di in drills):
            checks.append(Check("DRL-PLATING", "Plated / non-plated identified", "WARN",
                                "Drill files do not state plating (;TYPE=PLATED / NON_PLATED or PTH/NPTH file names)."))
    # ---------------- BOM / CPL ----------------
    if not boms:
        checks.append(Check("BOM-0", "BOM present", "FAIL", "No BOM CSV with a designator column found."))
    for b in boms:
        st = "PASS"
        notes = [f"{b.rows} lines, {len(b.populated)} placed, {len(b.dnp)} DNP"]
        if b.dup:
            st = "FAIL"
            notes.append("duplicate designators: " + ", ".join(sorted({d['designator'] for d in b.dup})))
        if b.qty_mismatch:
            st = "FAIL" if st != "FAIL" else st
            notes.append("qty != designator count on rows " + ", ".join(str(q["row"]) for q in b.qty_mismatch))
        if b.has_mpn_col and b.missing_mpn:
            st = "WARN" if st == "PASS" else st
            notes.append("populated lines without part number: " +
                         "; ".join(",".join(m["designators"]) for m in b.missing_mpn))
        if not b.has_mpn_col:
            st = "WARN" if st == "PASS" else st
            notes.append("no manufacturer/supplier part-number column")
        checks.append(Check("BOM-1", f"BOM integrity: {os.path.basename(b.name)}", st, "; ".join(notes),
                            {"populated": sorted(b.populated), "dnp": sorted(b.dnp)}))
    if len(boms) > 1:
        base = boms[0]
        for other in boms[1:]:
            a, o = set(base.populated), set(other.populated)
            if a != o:
                checks.append(Check("BOM-X", f"BOMs agree: {os.path.basename(base.name)} vs {os.path.basename(other.name)}",
                                    "WARN", f"only in first: {sorted(a - o)}; only in second: {sorted(o - a)}"))
            else:
                checks.append(Check("BOM-X", f"BOMs agree: {os.path.basename(base.name)} vs {os.path.basename(other.name)}",
                                    "PASS", f"{len(a)} placed designators match"))
    if not cpls:
        checks.append(Check("CPL-0", "Pick-and-place present", "WARN", "No pick-and-place / centroid CSV found."))
    for c in cpls:
        st = "PASS"
        notes = [f"{len(c.parts)} parts, units {c.units}"]
        if c.dup:
            st = "FAIL"
            notes.append("duplicate designators: " + ", ".join(sorted(set(c.dup))))
        if c.bad_rows:
            st = "WARN"
            notes.append(f"unparsable rows: {c.bad_rows[:10]}")
        layers = sorted({(v[3] or "?").strip() for v in c.parts.values()})
        notes.append("layers: " + ", ".join(layers))
        checks.append(Check("CPL-1", f"CPL integrity: {os.path.basename(c.name)}", st, "; ".join(notes)))
        if board_bbox:
            w = board_bbox[2] - board_bbox[0]
            h = board_bbox[3] - board_bbox[1]
            pts = list(c.parts.items())
            in_abs = [d for d, v in pts if board_bbox[0] - 0.1 <= v[0] <= board_bbox[2] + 0.1
                      and board_bbox[1] - 0.1 <= v[1] <= board_bbox[3] + 0.1]
            in_rel = [d for d, v in pts if -0.1 <= v[0] <= w + 0.1 and -0.1 <= v[1] <= h + 0.1]
            best, frame = (in_abs, "Gerber absolute origin") if len(in_abs) >= len(in_rel) else (in_rel, "board lower-left corner")
            outside = sorted(set(c.parts) - set(best))
            checks.append(Check("CPL-BOUNDS", f"CPL coordinates inside board ({os.path.basename(c.name)})",
                                "FAIL" if outside else "PASS",
                                f"origin interpreted as {frame}; outside: {outside}" if outside else
                                f"all parts inside the outline bbox (origin = {frame})", {"origin": frame}))
    for b in boms:
        for c in cpls:
            pop, plc = set(b.populated), set(c.parts)
            missing = sorted(pop - plc)
            extra = sorted(plc - pop)
            dnp_placed = sorted(plc & b.dnp)
            st = "PASS"
            det = []
            if missing:
                st = "FAIL"
                det.append(f"in BOM but not in CPL: {missing}")
            if dnp_placed:
                st = "WARN" if st == "PASS" else st
                det.append(f"DNP but listed in CPL (assembler may place): {dnp_placed}")
            if extra and set(extra) - b.dnp:
                st = "WARN" if st == "PASS" else st
                det.append(f"in CPL but not in BOM: {sorted(set(extra) - b.dnp)}")
            checks.append(Check("XCHK-1", f"BOM <-> CPL: {os.path.basename(b.name)} / {os.path.basename(c.name)}", st,
                                "; ".join(det) if det else f"{len(pop)} placed designators match"))
    # ---------------- DRC reports ----------------
    for f, r in drc_reports:
        tot = r.get("total_violations")
        st = "PASS" if tot == 0 else ("WARN" if tot else "INFO")
        checks.append(Check("DRC-REPORT", f"DRC report: {os.path.basename(f.name)}", st,
                            f"violations: {tot}" + (f"; unconnected: {r['unconnected']}" if r.get("unconnected") is not None else ""),
                            r))
    # ---------------- Freshness ----------------
    cad_files = []
    for d in [pkg] + cad_dirs:
        for dp, dn, fns in os.walk(d):
            dn[:] = [x for x in dn if x not in SKIP_DIRS and not OUTPUT_DIR_RE.search(x)]
            for fn in fns:
                if fn.lower().endswith((".pcbdoc", ".schdoc", ".kicad_pcb", ".kicad_sch", ".brd", ".sch")):
                    p = os.path.join(dp, fn)
                    cad_files.append((p, os.path.getmtime(p)))
    if cad_files:
        newest = max(cad_files, key=lambda t: t[1])
        outputs = [f for f in files if f.name in inv["gerber"] or f.name in inv["drill"]
                   or f.name in inv["bom"] or f.name in inv["cpl"] or f.name in inv["drc"]]
        stale = [f.name for f in outputs if f.mtime + 120 < newest[1]]
        checks.append(Check("FRESH-1", "Outputs newer than the CAD sources", "WARN" if stale else "PASS",
                            (f"newest CAD file {os.path.relpath(newest[0], pkg) if newest[0].startswith(pkg) else newest[0]} "
                             f"({time.strftime('%Y-%m-%d %H:%M', time.localtime(newest[1]))}) is newer than: "
                             + ", ".join(stale[:15])) if stale else
                            f"all outputs are newer than the newest CAD file ({os.path.basename(newest[0])})",
                            {"newest_cad": newest[0], "stale": stale}))
        if cad_dirs:
            by_name: dict[str, list] = {}
            for p, _ in cad_files:
                by_name.setdefault(os.path.basename(p).lower(), []).append(p)
            diffs = []
            for n, paths in by_name.items():
                if len(paths) > 1:
                    hashes = {p: sha256(open(p, "rb").read()) for p in paths}
                    if len(set(hashes.values())) > 1:
                        diffs.append({"file": n, "copies": {p: (h, time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p))))
                                                            for p, h in hashes.items()}})
            checks.append(Check("FRESH-2", "Package CAD copies match the master project", "WARN" if diffs else "PASS",
                                "; ".join(f"{d['file']} differs between copies" for d in diffs) if diffs else
                                "same-named CAD files are identical", {"differences": diffs}))
    return {
        "tool": "pcb_checks.py", "version": "1.0", "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "package": os.path.abspath(pkg), "profile": profile.get("name", "none"),
        "summary": {s: sum(1 for c in checks if c.status == s) for s in STATUS_ORDER},
        "checks": [asdict(c) for c in sorted(checks, key=lambda c: (STATUS_ORDER[c.status], c.id))],
    }


def to_markdown(res: dict) -> str:
    lines = [f"# Automatic package checks", "",
             f"- Package: `{res['package']}`", f"- Profile: {res['profile']}", f"- Generated: {res['generated']}",
             f"- Summary: " + ", ".join(f"{k} {v}" for k, v in res["summary"].items()), "",
             "| Status | ID | Check | Detail |", "|---|---|---|---|"]
    for c in res["checks"]:
        if c["id"] == "GBR-LAYERS":
            continue
        det = c["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {c['status']} | {c['id']} | {c['title']} | {det[:600]} |")
    lines += ["", "_Screening checks only. They do not replace the EDA tool's DRC/ERC, a Gerber viewer review, "
              "or the fab's own DFM._", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# PDF text extraction
# --------------------------------------------------------------------------

def run_text(pdfs: list[str], out: str) -> int:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        print("pypdf is not installed. Install it (pip install pypdf) or run install.py --with-pdf.", file=sys.stderr)
        return 2
    os.makedirs(out, exist_ok=True)
    for p in pdfs:
        r = PdfReader(p)
        dst = os.path.join(out, os.path.splitext(os.path.basename(p))[0] + ".txt")
        with open(dst, "w", encoding="utf-8") as fh:
            for i, page in enumerate(r.pages, 1):
                fh.write(f"\n\n===== PAGE {i} =====\n")
                fh.write(page.extract_text() or "")
        print(f"{p}: {len(r.pages)} pages -> {dst}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("package", help="screen a release package")
    p.add_argument("--package", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--profile", help="fab profile JSON")
    p.add_argument("--cad", action="append", default=[], help="extra CAD source dir (master project) for freshness checks")
    p.add_argument("--layers", type=int, help="expected copper layer count")
    p.add_argument("--strict", action="store_true", help="exit 1 if any FAIL")
    t = sub.add_parser("text", help="extract PDF text (needs pypdf)")
    t.add_argument("pdfs", nargs="+")
    t.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "text":
        return run_text(a.pdfs, a.out)
    profile = {}
    if a.profile:
        with open(a.profile, encoding="utf-8") as fh:
            profile = json.load(fh)
    res = run_package(a.package, profile, a.cad, a.layers)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "auto_checks.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2)
    with open(os.path.join(a.out, "auto_checks.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(res))
    print(json.dumps(res["summary"]))
    for c in res["checks"]:
        if c["status"] in ("FAIL", "WARN"):
            print(f"{c['status']:4} {c['id']}: {c['title']} - {c['detail'][:200]}")
    return 1 if a.strict and res["summary"].get("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
