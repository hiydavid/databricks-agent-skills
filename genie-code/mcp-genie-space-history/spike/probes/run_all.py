"""Local probe runner for the P0 scriptable criteria (#2 local id, #3, #4, #5, #6).

Usage (from the ``spike/`` directory, with a venv that has databricks-sdk>=0.118.0):

    python -m probes.run_all              # run all probes
    python -m probes.run_all whoami       # just one
    python -m probes.run_all provision variant roundtrip etag

Each probe prints its real JSON result. A final RESULT SUMMARY block maps outcomes to
the §12 residuals. Exit code is non-zero if any selected probe reported ok=False.

These run under the developer's own identity via ``config.SPIKE_PROFILE`` (no App
request path needed). Criteria #1 (connect-from-Genie-Code) and #2-over-OBO-header are
UI/deploy steps — see ../RUNBOOK.md.
"""

import sys

import config
import spike_core

from . import _common

PROBES = ["whoami", "provision", "variant", "roundtrip", "etag"]


def run(name: str, w) -> dict:
    if name == "whoami":
        return spike_core.whoami(w)
    if name == "provision":
        return spike_core.provision(
            w, catalog=config.HISTORY_CATALOG, schema=config.HISTORY_SCHEMA,
            warehouse_id=config.SQL_WAREHOUSE_ID,
        )
    if name == "variant":
        return spike_core.variant_probe(
            w, catalog=config.HISTORY_CATALOG, schema=config.HISTORY_SCHEMA,
            warehouse_id=config.SQL_WAREHOUSE_ID,
        )
    if name == "roundtrip":
        return spike_core.genie_roundtrip(w, space_id=config.GENIE_SPACE_ID, apply=True)
    if name == "etag":
        return spike_core.etag_check(w, space_id=config.GENIE_SPACE_ID)
    raise SystemExit(f"unknown probe: {name}")


def main(argv: list):
    selected = [a for a in argv if not a.startswith("-")] or PROBES
    _common.banner("RESOLVED SPIKE CONFIG")
    _common.show(config.as_dict())

    w = _common.build_client()
    results: dict[str, dict] = {}
    for name in selected:
        _common.banner(f"PROBE: {name}")
        try:
            res = run(name, w)
        except Exception as e:  # noqa: BLE001 - record, don't crash the whole run
            res = {"ok": False, "error_class": type(e).__name__, "error": str(e)}
        results[name] = res
        _common.show(res)

    _common.banner("RESULT SUMMARY")
    all_ok = True
    for name in selected:
        ok = results[name].get("ok", False)
        all_ok = all_ok and ok
        print(f"  {name:10s} ok={ok}")
    # Residual-specific call-outs.
    if "variant" in results:
        print(f"  -> VARIANT decision : {results['variant'].get('recommendation', '?')}")
    if "etag" in results:
        print(f"  -> etag enforced    : {results['etag'].get('stale_update_rejected', '?')}")
    if "whoami" in results:
        print(f"  -> identity         : {results['whoami'].get('user_name', '?')}")
    print("=" * 78)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
