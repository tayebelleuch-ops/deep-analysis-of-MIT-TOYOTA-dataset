"""Tests for the upload-progress wrapper in zenodo_publish.py.

Run it directly; there is no test runner in this repository:

    .venv/bin/python -I exploration/test_zenodo_progress.py

Makes no network call and needs no token. The last test reads the real 823 MB
HDF5 file if it is present, to confirm memory stays flat, and is skipped otherwise.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import resource
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location("zp", HERE / "zenodo_publish.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


zp = _load()
_fails = 0


def ck(name: str, ok: bool, detail: object = "") -> None:
    global _fails
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if not ok else ""))
    _fails += (not ok)


# ---------------------------------------------------------------------------

def test_counts_small_file() -> None:
    print("\n1. _ChunkedReader against a small temporary file")
    payload = bytes(range(256)) * 1234            # 315,904 bytes, not a chunk multiple
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sample.bin"
        p.write_bytes(payload)
        size = p.stat().st_size

        # -- iterator path
        seen = []
        r = zp._ChunkedReader(p, size, on_advance=seen.append, chunk=4096)
        got = b"".join(r)
        r.close()
        ck("__len__ equals the file size", len(r) == size, f"{len(r)} != {size}")
        ck("iterating yields the file byte-for-byte", got == payload)
        ck("count equals the file size", r.count == size, f"{r.count} != {size}")
        ck("on_advance total equals the file size", sum(seen) == size, sum(seen))
        ck("chunks are at most the requested size", max(seen) <= 4096, max(seen))
        ck("all chunks but the last are exactly the chunk size",
           all(x == 4096 for x in seen[:-1]), sorted(set(seen[:-1])))

        # -- read() path, with a block size unrelated to the chunk size
        seen2 = []
        r2 = zp._ChunkedReader(p, size, on_advance=seen2.append, chunk=4096)
        out = io.BytesIO()
        while True:
            b = r2.read(8192)
            if not b:
                break
            out.write(b)
        r2.close()
        ck("read() returns the file byte-for-byte", out.getvalue() == payload)
        ck("read() counts the file size exactly", r2.count == size, r2.count)
        ck("read() never returns more than asked", max(seen2) <= 8192, max(seen2))

        # -- read(None) path
        r3 = zp._ChunkedReader(p, size, chunk=4096)
        ck("read(None) returns the whole file", r3.read(None) == payload)
        ck("read(None) counts the whole file", r3.count == size, r3.count)
        ck("a second read() returns b''", r3.read(10) == b"")
        r3.close()

        # -- empty file
        e = Path(d) / "empty.bin"
        e.write_bytes(b"")
        r4 = zp._ChunkedReader(e, 0)
        ck("empty file: len 0, no bytes, count 0",
           len(r4) == 0 and b"".join(r4) == b"" and r4.count == 0)
        r4.close()


def test_requests_contract() -> None:
    print("\n2. the shape `requests` relies on")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.bin"
        p.write_bytes(b"a" * 5000)
        r = zp._ChunkedReader(p, 5000)
        ck("has __iter__ (so requests treats it as a stream, not a buffer)",
           hasattr(r, "__iter__"))
        ck("has __len__ (so super_len sets Content-Length)", hasattr(r, "__len__"))
        ck("has read (for the urllib3/http.client read path)", hasattr(r, "read"))
        ck("has NO tell (super_len would subtract it from __len__)",
           not hasattr(r, "tell"))
        ck("has NO seek (nothing should rewind a counted stream)",
           not hasattr(r, "seek"))
        try:
            from requests.utils import super_len
            ck("requests.utils.super_len reports the full size",
               super_len(r) == 5000, super_len(r))
        except ModuleNotFoundError:
            print("  ----  requests not importable; super_len check skipped")
        r.close()


def test_progress_is_token_free() -> None:
    print("\n3. progress output carries names and byte counts only")
    buf = io.StringIO()
    prog = zp._Progress(2, 3000, stream=buf)        # not a TTY -> plain lines
    prog.start_file("within_cycle_2017-05-12.h5", 2000)
    for _ in range(20):
        prog.advance(100)
    prog.finalizing()
    prog.finish_file()
    prog.start_file("LICENSE.txt", 1000)
    prog.advance(1000)
    prog.finalizing()
    prog.finish_file()
    text = buf.getvalue()
    TOK = "sbtok_SECRET_VALUE_1234567890"
    ck("no token-like string in progress output", TOK not in text)
    ck("no 'Bearer' in progress output", "Bearer" not in text)
    ck("no 'access_token' in progress output", "access_token" not in text)
    ck("no URL in progress output", "http" not in text)
    ck("reports the file name", "within_cycle_2017-05-12.h5" in text)
    ck("reports 100%", "100.0%" in text)
    ck("prints 'finalizing' before 'done'",
       text.index("finalizing within_cycle_2017-05-12.h5") < text.index("done within_cycle"))
    ck("reports files done / total", "2/2 files" in text, text.splitlines()[-1])
    ck("reports overall bytes", "2.9 KiB" in text or "2.9 KiB" in text.replace(",", ""),
       text.splitlines()[-1])
    ck("non-TTY output contains no carriage return", "\r" not in text)
    # Throttling: feed many small advances and check the line count tracks
    # PROGRESS_EVERY_PCT rather than the number of advance() calls. (Above, each
    # advance was exactly 5%, so every one of them is legitimately due.)
    buf2 = io.StringIO()
    prog2 = zp._Progress(1, 2000, stream=buf2)
    prog2.start_file("big.h5", 2000)
    for _ in range(200):                       # 0.5% each
        prog2.advance(10)
    lines = [l for l in buf2.getvalue().splitlines() if l.strip()]
    expected = 100 / zp.PROGRESS_EVERY_PCT     # ~20
    ck("non-TTY throttles to ~100/PROGRESS_EVERY_PCT lines, not one per advance",
       len(lines) <= expected + 3, f"{len(lines)} lines for 200 advances")
    ck("non-TTY still emits the final 100% line", "100.0%" in buf2.getvalue())


def test_tty_mode() -> None:
    print("\n4. TTY mode redraws a single line")

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    buf = FakeTTY()
    prog = zp._Progress(1, 1000, stream=buf)
    prog.start_file("f.h5", 1000)
    for _ in range(10):
        prog.advance(100)
    prog.finalizing()
    prog.finish_file()
    text = buf.getvalue()
    ck("uses carriage returns", "\r" in text)
    ck("every advance redraws (11 writes incl. start)", text.count("\r") >= 11,
       text.count("\r"))
    ck("finalizing and done still appear",
       "finalizing f.h5" in text and "done f.h5" in text)


def test_memory_flat() -> None:
    print("\n5. memory stays flat on the real 823 MB file")
    big = HERE / "extract_out" / "within_cycle_2018-04-12.h5"
    if not big.exists():
        print(f"  ----  {big.name} absent; skipped")
        return
    size = big.stat().st_size
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_delta = 0
    h = hashlib.sha256()
    r = zp._ChunkedReader(big, size)
    for chunk in r:
        h.update(chunk)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_delta = max(peak_delta, rss - base)
    r.close()
    print(f"        file {size:,} bytes; peak RSS growth {peak_delta * 1024:,} bytes "
          f"({peak_delta / 1024:.1f} MiB)")
    ck("streamed the whole file", r.count == size, f"{r.count} != {size}")
    # one 1 MiB chunk plus interpreter noise; nothing proportional to 823 MB
    ck("peak RSS growth under 16 MiB (not proportional to the file)",
       peak_delta < 16 * 1024, f"{peak_delta / 1024:.1f} MiB")
    sums = HERE / "extract_out" / "SHA256SUMS.txt"
    if sums.exists():
        want = {l.split()[-1]: l.split()[0] for l in sums.read_text().splitlines()
                if len(l.split()) >= 2}
        if big.name in want:
            ck("streamed bytes hash to the recorded SHA-256",
               h.hexdigest() == want[big.name], h.hexdigest()[:16])


def test_failed_request_leaks_nothing() -> None:
    """A failing upload must not put the token in progress output, on stderr, or in
    the exit message -- even when the server's error text contains it."""
    print("\n6. a failed request leaks no token")
    import contextlib
    TOK = "sbtok_SECRET_VALUE_1234567890"

    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "within_cycle_fake.h5"
        f.write_bytes(b"z" * (3 << 20))               # 3 MiB, so progress really runs
        plan = [(f, "within_cycle_fake.h5", "deadbeef", f.stat().st_size)]

        class StubSession:
            headers = {}

            def post(self, url, **kw):
                class R:
                    @staticmethod
                    def raise_for_status():
                        pass

                    @staticmethod
                    def json():
                        return {"id": 999, "links": {"bucket": "https://example/bucket"}}
                return R()

            def put(self, url, json=None, data=None, **kw):
                if data is None:                      # the metadata PUT
                    class R:
                        @staticmethod
                        def raise_for_status():
                            pass
                    return R()
                for i, _chunk in enumerate(data):     # drive the progress reporter
                    if i >= 2:
                        break
                raise RuntimeError(
                    f"401 Client Error: Unauthorized for url: "
                    f"https://sandbox.zenodo.org/api/files/x?access_token={TOK} "
                    f"(Authorization: Bearer {TOK})")

        orig = zp._session
        zp._session = lambda tok: StubSession()
        err, out = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                zp.deposit("https://sandbox.zenodo.org", TOK, {"title": "t"}, plan)
        except SystemExit as e:
            code = str(e.code)
        finally:
            zp._session = orig

        combined = err.getvalue() + out.getvalue() + (code or "")
        ck("the request did fail (SystemExit raised)", code is not None)
        ck("token absent from stderr progress output", TOK not in err.getvalue())
        ck("token absent from stdout", TOK not in out.getvalue())
        ck("token absent from the exit message", code is not None and TOK not in code)
        ck("token absent from everything the process emitted", TOK not in combined)
        ck("the exit message is redacted, not suppressed",
           code is not None and "<REDACTED>" in code, code)
        ck("progress still reported the file name", "within_cycle_fake.h5" in err.getvalue())
        ck("no raw 'access_token=<value>' survives",
           "access_token=" + TOK not in combined)


def main() -> None:
    print("zenodo_publish.py upload-progress tests (no network, no token)")
    test_counts_small_file()
    test_requests_contract()
    test_progress_is_token_free()
    test_tty_mode()
    test_memory_flat()
    test_failed_request_leaks_nothing()
    print(f"\n{'FAILED: ' + str(_fails) + ' check(s)' if _fails else 'all checks passed'}")
    sys.exit(1 if _fails else 0)


if __name__ == "__main__":
    main()
