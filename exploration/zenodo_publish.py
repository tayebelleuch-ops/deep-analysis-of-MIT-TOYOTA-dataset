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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "extract_out"
METADATA = HERE / "zenodo_metadata.json"
LICENSE = HERE / "zenodo_LICENSE.txt"

SANDBOX = "https://sandbox.zenodo.org"
PRODUCTION = "https://zenodo.org"

# Upload progress. The file is never read into memory: it is served out in
# UPLOAD_CHUNK-sized pieces (see _ChunkedReader), so peak memory is one chunk
# regardless of file size.
UPLOAD_CHUNK = 1 << 20          # 1 MiB
PROGRESS_EVERY_PCT = 5.0        # non-TTY: emit at least every this many percent
PROGRESS_EVERY_S = 10.0         # non-TTY: ... or this many seconds, whichever first

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
# upload progress  (standard library only; nothing here touches the token)
# ---------------------------------------------------------------------------

def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TiB"


def _hms(seconds: float) -> str:
    if seconds != seconds or seconds in (float("inf"), float("-inf")) or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:d}:{sec:02d}"


class _Progress:
    """Upload progress, written to stderr.

    On a TTY one line is redrawn with a carriage return; otherwise a plain line is
    printed every PROGRESS_EVERY_PCT percent or PROGRESS_EVERY_S seconds, whichever
    comes first, so a log file gets a readable trail rather than thousands of lines.

    **Only file names and byte counts are ever written here.** The token is not passed
    to this class and no request object reaches it.
    """

    def __init__(self, n_files: int, total_bytes: int, stream=None):
        self.n_files = n_files
        self.total_bytes = total_bytes
        self.stream = stream if stream is not None else sys.stderr
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.files_done = 0
        self.bytes_done = 0          # completed files only
        self.name = ""
        self.size = 0
        self.sent = 0
        self._t0 = 0.0
        self._last_t = 0.0
        self._last_pct = -PROGRESS_EVERY_PCT
        self._open_line = False

    # -- line handling ------------------------------------------------------
    def _write(self, text: str, final: bool = False) -> None:
        if self.tty:
            self.stream.write("\r" + text.ljust(96))
            if final:
                self.stream.write("\n")
                self._open_line = False
            else:
                self._open_line = True
        else:
            self.stream.write(text + "\n")
        self.stream.flush()

    def _break_line(self) -> None:
        """End an in-progress TTY line before printing something else."""
        if self.tty and self._open_line:
            self.stream.write("\n")
            self.stream.flush()
            self._open_line = False

    # -- lifecycle ----------------------------------------------------------
    def start_file(self, name: str, size: int) -> None:
        self.name, self.size, self.sent = name, size, 0
        self._t0 = self._last_t = time.monotonic()
        self._last_pct = -PROGRESS_EVERY_PCT
        self._write(self._line())

    def advance(self, n: int) -> None:
        self.sent += n
        now = time.monotonic()
        pct = 100.0 * self.sent / self.size if self.size else 100.0
        due = (self.tty
               or pct - self._last_pct >= PROGRESS_EVERY_PCT
               or now - self._last_t >= PROGRESS_EVERY_S
               or self.sent >= self.size)
        if due:
            self._last_t, self._last_pct = now, pct
            self._write(self._line())

    def finalizing(self) -> None:
        self._break_line()
        self._write(f"    finalizing {self.name} ...", final=True)

    def finish_file(self) -> None:
        self.files_done += 1
        self.bytes_done += self.size
        self._write(
            f"    done {self.name}  "
            f"[{self.files_done}/{self.n_files} files, "
            f"{_human(self.bytes_done)} / {_human(self.total_bytes)}]", final=True)

    # -- rendering ----------------------------------------------------------
    def _line(self) -> str:
        elapsed = max(time.monotonic() - self._t0, 1e-9)
        rate = self.sent / elapsed
        pct = 100.0 * self.sent / self.size if self.size else 100.0
        eta = (self.size - self.sent) / rate if rate > 0 else float("inf")
        overall = self.bytes_done + self.sent
        return (f"  {self.name}  {_human(self.sent)}/{_human(self.size)} "
                f"{pct:5.1f}%  {_human(rate)}/s  ETA {_hms(eta)}  "
                f"| {self.files_done}/{self.n_files} files, "
                f"{_human(overall)}/{_human(self.total_bytes)}")


class _ChunkedReader:
    """File wrapper that streams in UPLOAD_CHUNK pieces and counts bytes served.

    Why the shape of this class matters to `requests`:

    * ``__iter__`` is what makes requests classify the body as a *stream*
      (``prepare_body`` tests ``hasattr(data, "__iter__")``), so the file is not
      slurped into a bytes object first.
    * ``__len__`` is what ``requests.utils.super_len`` reads first, so a
      ``Content-Length`` header is set and the body is **not** sent chunked.
    * ``read`` is provided because some urllib3/http.client paths prefer it. It is
      served from a one-chunk buffer, so disk reads stay UPLOAD_CHUNK-sized whatever
      block size the HTTP layer asks for.
    * ``tell`` and ``seek`` are deliberately **absent**: ``super_len`` subtracts
      ``tell()`` from ``len()`` when both exist, which would understate
      Content-Length once reading has begun.

    Peak memory is one chunk. Bytes are counted exactly once, as they leave the
    object, whichever of the two paths the HTTP layer takes.
    """

    def __init__(self, path: Path, size: int, on_advance=None,
                 chunk: int = UPLOAD_CHUNK):
        self._fh = open(path, "rb")
        self._size = size
        self._chunk = chunk
        self._on_advance = on_advance
        self._buf = b""
        self.count = 0                 # bytes served out of this object

    def __len__(self) -> int:
        return self._size

    def _advance(self, n: int) -> None:
        self.count += n
        if self._on_advance is not None:
            self._on_advance(n)

    def _refill(self) -> bool:
        if not self._buf:
            self._buf = self._fh.read(self._chunk)
        return bool(self._buf)

    def read(self, amt: int | None = None) -> bytes:
        if amt is None or amt < 0:
            out = []
            while self._refill():
                out.append(self._buf)
                self._advance(len(self._buf))
                self._buf = b""
            return b"".join(out)
        if not self._refill():
            return b""
        take, self._buf = self._buf[:amt], self._buf[amt:]
        self._advance(len(take))
        return take

    def __iter__(self):
        while self._refill():
            chunk, self._buf = self._buf, b""
            self._advance(len(chunk))
            yield chunk

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:                                      # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


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

REQUIRED_TOP = ("title", "upload_type", "access_right", "license")


def _prune(meta: dict) -> tuple[dict, list[str]]:
    """Drop optional fields left empty, rather than refusing to deposit.

    `publication_date` and a creator's `affiliation` are optional on Zenodo --
    publication_date defaults to the deposit date, and an absent affiliation simply
    does not appear on the record. Sending them as empty strings would either be
    rejected or render as a blank field, so they are removed here. Required fields
    are never pruned; they are checked instead.
    """
    dropped = []
    out = {k: v for k, v in meta.items() if not k.startswith("_")}
    for k in list(out):
        if isinstance(out[k], str) and not out[k].strip():
            if k in REQUIRED_TOP:
                continue                      # reported as an error below, not dropped
            dropped.append(k)
            del out[k]
    creators = []
    for i, c in enumerate(out.get("creators", [])):
        kept = {}
        for k, v in c.items():
            if isinstance(v, str) and not v.strip():
                dropped.append(f"creators[{i}].{k}")
            else:
                kept[k] = v
        creators.append(kept)
    if creators:
        out["creators"] = creators
    return out, dropped


def load_metadata(strict: bool) -> dict:
    """`strict` is True only when a write is about to happen: a dry run should still be
    able to show the plan while anything is outstanding."""
    meta = json.loads(METADATA.read_text())["metadata"]
    meta, dropped = _prune(meta)

    # genuine placeholders are still a hard stop -- an unfilled template must not be
    # deposited. An EMPTY optional field is not a placeholder; it is a choice.
    bad = [k for k, v in meta.items() if isinstance(v, str) and PLACEHOLDER.search(v)]
    for i, c in enumerate(meta.get("creators", [])):
        bad += [f"creators[{i}].{k}" for k, v in c.items()
                if isinstance(v, str) and PLACEHOLDER.search(v)]
    missing = [k for k in REQUIRED_TOP if not str(meta.get(k, "")).strip()]
    if not meta.get("creators") or any(not c.get("name", "").strip()
                                       for c in meta["creators"]):
        missing.append("creators[].name")

    if bad or missing:
        msg = ""
        if bad:
            msg += "unfilled placeholders:\n  " + "\n  ".join(bad) + "\n"
        if missing:
            msg += "missing required fields:\n  " + "\n  ".join(missing) + "\n"
        msg += "Fix them in exploration/zenodo_metadata.json."
        if strict:
            sys.exit("error: " + msg + " Refusing to deposit.")
        print("WARNING: " + msg + "\n")

    if meta.get("license") != "cc-by-4.0":
        sys.exit(f"error: licence is {meta.get('license')!r}, expected 'cc-by-4.0'. "
                 "These files are an adaptation of CC BY 4.0 data.")
    meta["_placeholders"] = bad + missing
    meta["_dropped"] = dropped
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

        prog = _Progress(len(plan), sum(sz for _, _, _, sz in plan))
        for path, name, digest, size in plan:
            prog.start_file(name, size)
            reader = _ChunkedReader(path, size, on_advance=prog.advance)
            try:
                r = s.put(f"{bucket}/{name}", data=reader)
                # every byte has left the wrapper; the server has not answered yet
                prog.finalizing()
                r.raise_for_status()
            finally:
                reader.close()
            if reader.count != size:
                sys.exit(f"error: {name}: streamed {reader.count:,} bytes but the file "
                         f"is {size:,} bytes -- refusing to continue")
            # Zenodo returns the MD5 it computed; SHA-256 is verified by re-download
            # below, which is the check that actually matters to us.
            prog.finish_file()
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
    dropped = meta.pop("_dropped", [])
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
    if dropped:
        print(f"omitted     : {', '.join(dropped)}  (optional and empty -- dropped, "
              f"not sent)")
    print(f"token       : read from ${'ZENODO_SANDBOX_TOKEN' if sandbox else 'ZENODO_TOKEN'}; never shown")
    print(f"streaming   : {_human(UPLOAD_CHUNK)} chunks, Content-Length set, progress to "
          f"stderr ({'TTY, one redrawn line' if sys.stderr.isatty() else f'not a TTY, a line every {PROGRESS_EVERY_PCT:.0f}% or {PROGRESS_EVERY_S:.0f} s'})")

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
