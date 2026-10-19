#!/usr/bin/env python3
"""eda_snapshot.py - take a read-only snapshot of a live EDA design through an MCP server.

Talks MCP (JSON-RPC over stdio) to an EDA server such as eda-agent, calls a
fixed list of READ-ONLY tools and writes each result to OUT/<tool>.json, so
the snapshot never has to pass through a model's context. Only tools on the
built-in allowlist can be called; anything else is refused.

Usage:
  python eda_snapshot.py --out DIR [--mcp-json .mcp.json --server eda-agent]
                         [--cmd EXE ARG ...] [--timeout 90] [--only a,b]

The server command is read from the project's .mcp.json (mcpServers.<server>)
unless --cmd is given. eda-agent is started with --no-dashboard when the
command is "serve".
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

# Read-only tools and the arguments to use. Order matters: ping first.
ALTIUM_EDA_AGENT = [
    ("app_ping", {}),
    ("app_get_active_document", {}),
    ("app_list_documents", {}),
    ("proj_get_stats", {}),
    ("proj_get_compile_freshness", {}),
    ("proj_get_differences", {}),
    ("proj_get_erc_violations", {}),
    ("pcb_get_components", {}),
    ("pcb_get_board_outline", {}),
    ("pcb_get_layer_stackup", {}),
    ("pcb_get_design_rules", {}),
    ("pcb_get_diff_pair_rules", {}),
    ("pcb_get_net_classes", {"members": False}),
    ("pcb_get_differential_pairs", {}),
    ("pcb_get_trace_lengths", {}),
    ("pcb_get_vias", {}),
    ("pcb_get_polygons", {}),
    ("pcb_get_unrouted_nets", {}),
    ("proj_get_nets", {"limit": 5000}),
    ("proj_get_bom", {}),
]
READ_ONLY = {name for name, _ in ALTIUM_EDA_AGENT} | {
    "pcb_get_component_pads", "pcb_get_pad_properties", "obj_query", "proj_get_connectivity",
    "proj_get_component_info", "pcb_get_board_statistics", "pcb_get_fab_stats", "list_nets", "list_components",
}


class McpClient:
    def __init__(self, cmd: list[str]):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self.next_id = 1

    def _reader(self):
        for line in self.p.stdout:
            self.q.put(line)

    def send(self, msg):
        self.p.stdin.write((json.dumps(msg) + "\n").encode())
        self.p.stdin.flush()

    def request(self, method, params, timeout):
        rid = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(self.q.get(timeout=1))
            except queue.Empty:
                if self.p.poll() is not None:
                    raise RuntimeError("server exited")
                continue
            except json.JSONDecodeError:
                continue
            if m.get("id") == rid:
                return m
        raise TimeoutError(f"{method} timed out after {timeout}s")

    def close(self):
        try:
            self.p.kill()
        except OSError:
            pass


def server_cmd(args) -> list[str]:
    if args.cmd:
        cmd = list(args.cmd)
    else:
        with open(args.mcp_json, encoding="utf-8") as fh:
            cfg = json.load(fh)["mcpServers"][args.server]
        cmd = [cfg["command"]] + list(cfg.get("args", []))
    if "serve" in cmd and "--no-dashboard" not in cmd:
        cmd.append("--no-dashboard")
    return cmd


def unwrap(result):
    """Return the tool's JSON payload if it is JSON text, else the raw MCP result."""
    content = (result or {}).get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return {"text": texts[0]}
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mcp-json", default=".mcp.json")
    ap.add_argument("--server", default="eda-agent")
    ap.add_argument("--cmd", nargs=argparse.REMAINDER, help="explicit server command (must be last)")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--only", help="comma-separated subset of tools")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    plan = ALTIUM_EDA_AGENT
    if a.only:
        want = [t.strip() for t in a.only.split(",") if t.strip()]
        bad = [t for t in want if t not in READ_ONLY]
        if bad:
            print(f"refusing non-allowlisted tools: {bad}", file=sys.stderr)
            return 2
        plan = [(t, dict(ALTIUM_EDA_AGENT).get(t, {})) for t in want]
    cli = McpClient(server_cmd(a))
    index = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "results": []}
    try:
        init = cli.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                          "clientInfo": {"name": "pcb-review-snapshot", "version": "1.0"}}, 60)
        index["server"] = init.get("result", {}).get("serverInfo")
        cli.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        for name, args in plan:
            if name not in READ_ONLY:
                continue
            t0 = time.time()
            try:
                r = cli.request("tools/call", {"name": name, "arguments": args}, a.timeout)
                res = r.get("result")
                payload = unwrap(res) if res is not None else {"error": r.get("error")}
                ok = res is not None and not res.get("isError", False)
                if isinstance(payload, dict):
                    txt = str(payload.get("text", ""))
                    if "error" in payload or txt.startswith("Error") or payload.get("success") is False:
                        ok = False
                if not ok and isinstance(payload, dict) and "error" not in payload:
                    payload = {"error": payload.get("text") or payload.get("message") or "tool reported failure",
                               "raw": payload}
            except Exception as e:  # noqa: BLE001
                payload, ok = {"error": str(e)}, False
            with open(os.path.join(a.out, f"{name}.json"), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1)
            index["results"].append({"tool": name, "ok": ok, "seconds": round(time.time() - t0, 1)})
            print(f"{'ok ' if ok else 'ERR'} {name} ({time.time() - t0:.1f}s)")
            if not ok and "polling loop is probably not running" in json.dumps(payload):
                print("Altium bridge is not running (start StartMCPServer or run `eda-agent relaunch`); stopping",
                      file=sys.stderr)
                break
            if name == "app_ping" and not ok:
                print("bridge not answering; stopping snapshot", file=sys.stderr)
                break
    finally:
        cli.close()
        with open(os.path.join(a.out, "_index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=1)
    return 0 if all(r["ok"] for r in index["results"]) else 1


if __name__ == "__main__":
    sys.exit(main())
