#!/usr/bin/env python3
"""pcb_calc.py - closed-form PCB calculators for reviewers (standard library only).

Every result carries the formula and its validity range, so a reviewer can
cite it. These are first-order estimates; the fab's field solver and the
EDA tool's impedance profile are the reference.

Commands (lengths in mm unless stated):
  microstrip       --w --h --t --er            single-ended Z0, IPC-2141
  diff-microstrip  --w --s --h --t --er        edge-coupled differential Z, IPC-2141
  stripline        --w --b --t --er            symmetric stripline Z0 (b = plane-to-plane)
  diff-stripline   --w --s --b --t --er
  trace-current    --w --oz --rise [--internal]          IPC-2221 current for a width
  trace-width      --current --oz --rise [--internal]    IPC-2221 width for a current
  contacts         --load --rating [--derate 0.7]         connector contacts needed
  spacing          --volts                                IPC-2221B Table 6-1 minimum spacing
  skew             --delta-mm [--er-eff 3.0] [--ui-ps]    length mismatch to time skew
  oz               --oz                                   copper weight to thickness
Add --json for machine-readable output.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

OZ_MM = 0.0348  # 1 oz/ft^2 copper ~ 34.8 um (1.37 mil)


def microstrip(w, h, t, er):
    z0 = 87.0 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
    return {"z0_ohm": round(z0, 2), "formula": "IPC-2141: 87/sqrt(er+1.41)*ln(5.98h/(0.8w+t))",
            "valid": 0.1 < w / h < 2.0 and 1 < er < 15, "w_over_h": round(w / h, 3),
            "note": "Ignores solder mask (mask typically lowers Z by ~2-5 %)."}


def diff_microstrip(w, s, h, t, er):
    z0 = microstrip(w, h, t, er)["z0_ohm"]
    zd = 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h))
    return {"z0_ohm": z0, "zdiff_ohm": round(zd, 2),
            "formula": "IPC-2141: Zdiff = 2*Z0*(1-0.48*exp(-0.96*s/h))",
            "valid": 0.1 < w / h < 2.0, "s_over_h": round(s / h, 3),
            "note": "Closed-form estimate, often within ~5-10 % of a field solver; mask lowers Zdiff a few ohms."}


def stripline(w, b, t, er):
    z0 = 60.0 / math.sqrt(er) * math.log(4 * b / (0.67 * math.pi * (0.8 * w + t)))
    return {"z0_ohm": round(z0, 2), "formula": "IPC-2141: 60/sqrt(er)*ln(4b/(0.67*pi*(0.8w+t)))",
            "valid": w / b < 0.35 and t / b < 0.25}


def diff_stripline(w, s, b, t, er):
    z0 = stripline(w, b, t, er)["z0_ohm"]
    zd = 2 * z0 * (1 - 0.347 * math.exp(-2.9 * s / b))
    return {"z0_ohm": z0, "zdiff_ohm": round(zd, 2), "formula": "IPC-2141: Zdiff = 2*Z0*(1-0.347*exp(-2.9*s/b))"}


def _k(internal):
    return 0.024 if internal else 0.048


def trace_current(w, oz, rise, internal=False):
    area_mil2 = (w / 0.0254) * (oz * OZ_MM / 0.0254)
    i = _k(internal) * rise ** 0.44 * area_mil2 ** 0.725
    return {"current_a": round(i, 3), "area_mil2": round(area_mil2, 2),
            "formula": f"IPC-2221: I = {_k(internal)}*dT^0.44*A^0.725 (A in mil^2)",
            "note": "IPC-2221 charts are conservative for external layers; IPC-2152 gives the modern curves."}


def trace_width(current, oz, rise, internal=False):
    area = (current / (_k(internal) * rise ** 0.44)) ** (1 / 0.725)
    w_mil = area / (oz * OZ_MM / 0.0254)
    return {"width_mm": round(w_mil * 0.0254, 4), "width_mil": round(w_mil, 2),
            "formula": f"IPC-2221 inverse, k={_k(internal)}"}


def contacts(load, rating, derate=0.7):
    per = rating * derate
    n = math.ceil(load / per - 1e-9)
    return {"contacts_needed": n, "per_contact_a": round(per, 3),
            "note": "Use the connector datasheet's all-contacts-loaded derating; add the same count of return contacts."}


# IPC-2221B Table 6-1, minimum electrical conductor spacing in mm.
# Columns: B1 internal; B2 external uncoated sea level-3050 m; B3 external uncoated >3050 m;
# B4 external with permanent polymer coating; A5 external with conformal coating over assembly;
# A6 external component lead/termination, uncoated; A7 external component lead/termination, conformal coated.
IPC2221_T61 = [
    (15, dict(B1=0.05, B2=0.1, B3=0.1, B4=0.05, A5=0.13, A6=0.13, A7=0.13)),
    (30, dict(B1=0.05, B2=0.1, B3=0.1, B4=0.05, A5=0.13, A6=0.25, A7=0.13)),
    (50, dict(B1=0.1, B2=0.6, B3=0.6, B4=0.13, A5=0.13, A6=0.4, A7=0.13)),
    (100, dict(B1=0.1, B2=0.6, B3=1.5, B4=0.13, A5=0.13, A6=0.5, A7=0.13)),
    (150, dict(B1=0.2, B2=0.6, B3=3.2, B4=0.4, A5=0.4, A6=0.8, A7=0.4)),
    (170, dict(B1=0.2, B2=1.25, B3=3.2, B4=0.4, A5=0.4, A6=0.8, A7=0.4)),
    (250, dict(B1=0.2, B2=1.25, B3=6.4, B4=0.4, A5=0.4, A6=0.8, A7=0.4)),
    (300, dict(B1=0.2, B2=1.25, B3=12.5, B4=0.4, A5=0.4, A6=0.8, A7=0.8)),
    (500, dict(B1=0.25, B2=2.5, B3=12.5, B4=0.8, A5=0.8, A6=1.5, A7=0.8)),
]


def spacing(volts):
    for vmax, row in IPC2221_T61:
        if volts <= vmax:
            return {"volts_peak": volts, "band_max_v": vmax, "min_spacing_mm": row,
                    "legend": "B1 internal; B2 ext uncoated <3050 m; B3 ext uncoated >3050 m; B4 ext permanent polymer "
                              "coating (solder mask is commonly treated as B4); A5 ext conformal-coated assembly; "
                              "A6 ext component lead/termination uncoated (exposed pads); A7 ext lead conformal-coated",
                    "note": "Use DC or AC PEAK voltage. Values transcribed from IPC-2221B Table 6-1; check your copy of "
                            "the standard before citing."}
    return {"volts_peak": volts, "note": "Above 500 V: use the per-volt increments in IPC-2221B Table 6-1."}


def skew(delta_mm, er_eff=3.0, ui_ps=None):
    ps_per_mm = math.sqrt(er_eff) / 0.299792458
    s = delta_mm * ps_per_mm
    out = {"skew_ps": round(s, 2), "ps_per_mm": round(ps_per_mm, 3),
           "formula": "t = L*sqrt(er_eff)/c"}
    if ui_ps:
        out["fraction_of_ui"] = round(s / ui_ps, 4)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, *args, **flags):
        p = sub.add_parser(name)
        for a in args:
            p.add_argument(f"--{a}", type=float, required=True)
        for f, default in flags.items():
            if isinstance(default, bool):
                p.add_argument(f"--{f}", action="store_true")
            else:
                p.add_argument(f"--{f.replace('_', '-')}", dest=f, type=float, default=default)
        p.add_argument("--json", action="store_true")
        return p

    add("microstrip", "w", "h", "t", "er")
    add("diff-microstrip", "w", "s", "h", "t", "er")
    add("stripline", "w", "b", "t", "er")
    add("diff-stripline", "w", "s", "b", "t", "er")
    add("trace-current", "w", "oz", "rise", internal=False)
    add("trace-width", "current", "oz", "rise", internal=False)
    add("contacts", "load", "rating", derate=0.7)
    add("spacing", "volts")
    add("skew", er_eff=3.0, ui_ps=None).add_argument("--delta-mm", dest="delta_mm", type=float, required=True)
    add("oz", "oz")
    a = ap.parse_args(argv)
    c = a.cmd
    if c == "microstrip":
        r = microstrip(a.w, a.h, a.t, a.er)
    elif c == "diff-microstrip":
        r = diff_microstrip(a.w, a.s, a.h, a.t, a.er)
    elif c == "stripline":
        r = stripline(a.w, a.b, a.t, a.er)
    elif c == "diff-stripline":
        r = diff_stripline(a.w, a.s, a.b, a.t, a.er)
    elif c == "trace-current":
        r = trace_current(a.w, a.oz, a.rise, a.internal)
    elif c == "trace-width":
        r = trace_width(a.current, a.oz, a.rise, a.internal)
    elif c == "contacts":
        r = contacts(a.load, a.rating, a.derate)
    elif c == "spacing":
        r = spacing(a.volts)
    elif c == "skew":
        r = skew(a.delta_mm, a.er_eff, a.ui_ps)
    else:
        r = {"thickness_mm": round(a.oz * OZ_MM, 4), "thickness_mil": round(a.oz * OZ_MM / 0.0254, 3)}
    print(json.dumps(r, indent=None if a.json else 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
