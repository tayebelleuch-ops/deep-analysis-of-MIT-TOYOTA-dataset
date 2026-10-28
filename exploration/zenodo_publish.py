"""Deposit the v1.1 within-cycle extraction to Zenodo. DRAFT -- nothing uploaded yet.

Safety model, in order of importance:

1. **The token is read from the environment and never printed.** It is placed in an
   ``Authorization`` header, never in a URL or a query string (Zenodo accepts
   ``?access_token=`` and that would leak it into server logs, shell history and any
   traceback showing the request URL). Every exception is routed through
   :func:`_redact` before it reaches the terminal.
2. **Sandbox is the default.** ``--production`` must be passed explicitly, and the script
   refuses to run against production unless ``--i-have-rehearsed-on-sandbox`` is also
   given. A published Zenodo record cannot be edited or deleted, only superseded.
3. **Nothing is published by this script.** It creates a *draft* deposition and uploads
   files; the final "Publish" is left to a human in the web UI. There is no ``--publish``
   flag by design.
4. **Dry run is the default.** Without ``--go`` the script makes no write request at all;
   it validates the metadata, checks the files against ``SHA256SUMS.txt`` and prints the
   plan.
5. **Every uploaded file is verified by re-downloading it** and comparing SHA-256 with the
   local value. An upload that cannot be read back identically is reported as a failure.

Usage::

    export ZENODO_SANDBOX_TOKEN=...          # never echoed, never stored
    .venv/bin/python -I exploration/zenodo_publish.py                 # dry run, sandbox
    .venv/bin/python -I exploration/zenodo_publish.py --go            # real sandbox upload
    .venv/bin/python -I exploration/zenodo_publish.py --verify-only 12345

Token variables: ``ZENODO_SANDBOX_TOKEN`` for sandbox, ``ZENODO_TOKEN`` for production.
Required scopes: ``deposit:write`` (and ``deposit:actions`` only if you later publish via
the API, which this script does not do).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "extract_out"
METADATA = HERE / "zenodo_metadata.json"
LICENSE = HERE / "zenodo_LICENSE.txt"

SANDBOX = "https://sandbox.zenodo.org"
PRODUCTION = "https://zenodo.org"

# Files that go into the record. EXTRACTION.md travels with the data so the record is
# self-describing; the raw .mat files are NOT redistributed.
PAYLOAD = [
    (OUT / "within_cycle_2017-05-12.h5", "within_cycle_2017-05-12.h5"),
    (OUT / "within_cycle_2017-06-30.h5", "within_cycle_2017-06-30.h5"),
    (OUT / "within_cycle_2018-04-12.h5", "within_cycle_2018-04-12.h5"),
    (OUT / "within_cycle_index.csv", "within_cycle_index.csv"),
    (OUT / "within_cycle_cells.csv", "within_cycle_cells.csv"),
    (OUT / "SHA256SUMS.txt", "SHA256SUMS.txt"),
    (HERE / "EXTRACTION.md", "EXTRACTION.md"),
    (LICENSE, "LICENSE.txt"),
]
PLACEHOLDER = re.compile(r"PLACEHOLDER|^0000-0000-0000-0000$")


# ---------------------------------------------------------------------------
# token handling
# ---------------------------------------------------------------------------

def _token(sandbox: bool) -> str:
    var = "ZENODO_SANDBOX_TOKEN" if sandbox else "ZENODO_TOKEN"
    tok = os.environ.get(var, "").strip()
    if not tok:
        sys.exit(f"error: ${var} is not set. Export it and re-run; it is never printed, "
                 f"logged or written to disk by this script.")
    return tok


def _redact(text: str, tok: str) -> str:
    """Remove the token from anything on its way to the terminal."""
    if tok and tok in text:
        text = text.replace(tok, "<REDACTED>")
    # also catch a token echoed back in a URL by a library we do not control
    return re.sub(r"(access_token=)[^&\s\"']+", r"\1<REDACTED>", text)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# pre-flight, all local
# ---------------------------------------------------------------------------

def load_metadata(strict: bool) -> dict:
    """`strict` is True only when a write is about to happen: a dry run should still be
    able to show the plan while the placeholders are outstanding."""
    meta = json.loads(METADATA.read_text())["metadata"]
    bad = [k for k, v in meta.items() if isinstance(v, str) and PLACEHOLDER.search(v)]
    for i, c in enumerate(meta.get("creators", [])):
        bad += [f"creators[{i}].{k}" for k, v in c.items()
                if isinstance(v, str) and PLACEHOLDER.search(v)]
    if bad:
        msg = ("metadata still contains placeholders:\n  " + "\n  ".join(bad)
               + "\nFill them in exploration/zenodo_metadata.json.")
        if strict:
            sys.exit("error: " + msg + " Refusing to deposit.")
        print("WARNING: " + msg + "\n")
    meta["_placeholders"] = bad
    if meta.get("license") != "cc-by-4.0":
        sys.exit(f"error: licence is {meta.get('license')!r}, expected 'cc-by-4.0'. "
                 "These files are an adaptation of CC BY 4.0 data.")
    return meta


def check_payload() -> list[tuple[Path, str, str, int]]:
    """Confirm every file exists and matches SHA256SUMS.txt. Returns the plan."""
    sums_file = OUT / "SHA256SUMS.txt"
    if not sums_file.exists():
        sys.exit("error: extract_out/SHA256SUMS.txt is missing. Run "
                 "exploration/extract_checks.py first.")
    recorded = {}
    for line in sums_file.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            recorded[parts[-1]] = parts[0]

    plan, problems = [], []
    for path, name in PAYLOAD:
        if not path.exists():
            problems.append(f"missing: {path}")
            continue
        digest = sha256(path)
        if path.name in recorded and recorded[path.name] != digest:
            problems.append(f"{path.name}: on disk {digest[:16]}... but SHA256SUMS.txt "
                            f"records {recorded[path.name][:16]}... -- re-run the "
                            f"extraction, do not upload a file that does not match its "
                            f"manifest")
        plan.append((path, name, digest, path.stat().st_size))
    if problems:
        sys.exit("error: payload check failed:\n  " + "\n  ".join(problems))
    return plan


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

def _session(tok: str):
    try:
        import requests
    except ModuleNotFoundError:
        sys.exit("error: this script needs `requests`, which is not in the pinned "
                 "environment. Install it only in the shell you deposit from -- it is "
                 "not a dependency of the extraction itself.")
    s = requests.Session()
    # Header, never a query string: a token in the URL leaks into logs and tracebacks.
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def deposit(base: str, tok: str, meta: dict,
            plan: list[tuple[Path, str, str, int]]) -> dict:
    s = _session(tok)
    try:
        r = s.post(f"{base}/api/deposit/depositions", json={})
        r.raise_for_status()
        dep = r.json()
        dep_id, bucket = dep["id"], dep["links"]["bucket"]
        print(f"  created DRAFT deposition {dep_id}")
        print(f"  edit it at {base}/deposit/{dep_id}")

        r = s.put(f"{base}/api/deposit/depositions/{dep_id}",
                  json={"metadata": meta})
        r.raise_for_status()
        print("  metadata set")

        for path, name, digest, size in plan:
            print(f"  uploading {name} ({size:,} bytes) ...", flush=True)
            with open(path, "rb") as fh:
                r = s.put(f"{bucket}/{name}", data=fh)
            r.raise_for_status()
            # Zenodo returns the MD5 it computed; SHA-256 is verified by re-download
            # below, which is the check that actually matters to us.
            print(f"    stored")
        return dep
    except Exception as exc:                                   # noqa: BLE001
        sys.exit(_redact(f"error during deposit: {exc}", tok))


def verify(base: str, tok: str, dep_id: int,
           plan: list[tuple[Path, str, str, int]]) -> bool:
    """Download every file back and compare SHA-256 with the local value."""
    s = _session(tok)
    expect = {name: digest for _, name, digest, _ in plan}
    ok = True
    try:
        r = s.get(f"{base}/api/deposit/depositions/{dep_id}")
        r.raise_for_status()
        files = r.json().get("files", [])
        if not files:
            print("  no files on the deposition")
            return False
        for f in files:
            name = f.get("filename") or f.get("key")
            link = (f.get("links", {}).get("download")
                    or f.get("links", {}).get("self"))
            print(f"  verifying {name} ...", flush=True)
            h = hashlib.sha256()
            with s.get(link, stream=True) as d:
                d.raise_for_status()
                for chunk in d.iter_content(1 << 22):
                    h.update(chunk)
            got = h.hexdigest()
            want = expect.get(name)
            if want is None:
                print(f"    ?  {name} is on the record but not in the local plan")
                ok = False
            elif got == want:
                print(f"    OK {got[:16]}...")
            else:
                print(f"    FAIL local {want[:16]}... != downloaded {got[:16]}...")
                ok = False
        missing = set(expect) - {(f.get("filename") or f.get("key")) for f in files}
        if missing:
            print(f"  MISSING from the record: {sorted(missing)}")
            ok = False
        return ok
    except Exception as exc:                                   # noqa: BLE001
        sys.exit(_redact(f"error during verification: {exc}", tok))


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--production", action="store_true",
                    help="deposit to zenodo.org instead of sandbox.zenodo.org")
    ap.add_argument("--i-have-rehearsed-on-sandbox", action="store_true",
                    help="required with --production")
    ap.add_argument("--go", action="store_true",
                    help="actually make write requests (default is a dry run)")
    ap.add_argument("--verify-only", type=int, metavar="DEPOSITION_ID",
                    help="re-download an existing draft and check SHA-256")
    args = ap.parse_args()

    sandbox = not args.production
    base = SANDBOX if sandbox else PRODUCTION
    if args.production and not args.i_have_rehearsed_on_sandbox:
        sys.exit("error: --production requires --i-have-rehearsed-on-sandbox. A published "
                 "Zenodo record cannot be edited or deleted, only superseded.")

    meta = load_metadata(strict=args.go)
    placeholders = meta.pop("_placeholders", [])
    plan = check_payload()
    total = sum(sz for _, _, _, sz in plan)

    print(f"target      : {base} ({'SANDBOX' if sandbox else 'PRODUCTION'})")
    print(f"title       : {meta['title']}")
    print(f"licence     : {meta['license']}   access: {meta['access_right']}   "
          f"version: {meta['version']}")
    print(f"creators    : {', '.join(c['name'] for c in meta['creators'])}")
    for r in meta["related_identifiers"]:
        print(f"related     : {r['relation']:16s} {r['identifier']}")
    print(f"files       : {len(plan)}, {total:,} bytes ({total/1e9:.2f} GB)")
    for _, name, digest, size in plan:
        print(f"              {digest[:16]}...  {size:>13,}  {name}")
    print("token       : read from the environment; not shown")

    if args.verify_only:
        tok = _token(sandbox)
        print(f"\nverifying deposition {args.verify_only}")
        sys.exit(0 if verify(base, tok, args.verify_only, plan) else 1)

    if not args.go:
        if placeholders:
            print(f"\n{len(placeholders)} metadata placeholder(s) still to fill: "
                  f"{', '.join(placeholders)}")
        print("\nDRY RUN -- no request was made. Re-run with --go to create the draft.")
        print("Nothing is ever published by this script: it leaves a DRAFT for you to")
        print("review and publish by hand in the web UI.")
        return

    tok = _token(sandbox)
    print("\ncreating draft deposition ...")
    dep = deposit(base, tok, meta, plan)
    print("\nverifying by re-download ...")
    good = verify(base, tok, dep["id"], plan)
    print(f"\nDRAFT {dep['id']} created and {'VERIFIED' if good else 'NOT verified'}.")
    print(f"Review and publish by hand at {base}/deposit/{dep['id']}")
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
