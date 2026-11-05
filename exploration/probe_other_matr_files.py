"""Stage 0, inventory only: the MATR .mat files in this repo that are NOT part of
the published 124-cell dataset.

Nothing downstream reads these. This script records what they are -- batch date,
struct rows, channels, barcodes, cycle counts, schema shape -- so that "outside
the dataset" is a measured statement rather than an assumption. It extracts no
within-cycle data and writes nothing to the files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matr

REPO = Path(__file__).resolve().parent.parent
CANDIDATES = [
    REPO / "Data" / "2019-01-24_batchdata_updated_struct_errorcorrect.mat",
    REPO / "Data" / "2018-02-20_batchdata_updated_struct_errorcorrect.mat",
    REPO / "Data" / "2018-04-03_varcharge_batchdata_updated_struct_errorcorrect.mat",
    REPO / "dataset batteries" / "2018-02-20_batchdata_updated_struct_errorcorrect.mat",
    REPO / "dataset batteries" / "2018-04-03_varcharge_batchdata_updated_struct_errorcorrect.mat",
]
PUBLISHED = {p.resolve() for p in matr.BATCH_FILES.values()}


def describe(path: Path) -> None:
    print("=" * 74)
    print(path.relative_to(REPO) if path.is_relative_to(REPO) else path)
    if not path.exists():
        print("  absent")
        return
    real = path.resolve()
    print(f"  bytes: {path.stat().st_size:,}")
    if real in PUBLISHED:
        print("  NOTE: resolves to one of the three published batch files -- duplicate")
    try:
        f = h5py.File(path, "r")
    except OSError as e:
        print(f"  UNREADABLE: {e}")
        print("  -> the file on disk is shorter than its own HDF5 superblock says;"
              " an incomplete download, not a schema difference.")
        return
    with f:
        top = sorted(f.keys())
        print(f"  top level: {top}")
        date = np.ravel(f["batch_date"][()]).astype(np.uint16).tobytes().decode("utf-16-le")
        batch = f["batch"]
        print(f"  batch_date field: {date!r}")
        print(f"  batch fields: {sorted(batch.keys())}")
        n = batch["summary"].shape[0]
        print(f"  struct rows: {n}")
        summary0 = f[batch["summary"][0, 0]]
        cycles0 = f[batch["cycles"][0, 0]]
        print(f"  summary fields: {sorted(summary0.keys())}")
        print(f"  cycles fields : {sorted(cycles0.keys())}")
        ncyc, chans, bars, pol = [], [], [], []
        for i in range(n):
            ncyc.append(f[batch["cycles"][i, 0]]["I"].shape[0])
            try:
                chans.append(matr.decode_mcos_string(f, batch["channel_id"][i, 0]))
                bars.append(matr.decode_mcos_string(f, batch["barcode"][i, 0]))
            except Exception as e:                       # noqa: BLE001
                chans.append(f"<undecodable: {type(e).__name__}>")
                bars.append("")
            pol.append(matr.decode_char(f, batch["policy_readable"][i, 0]))
        print(f"  n_cycles per row: min={min(ncyc)} median={int(np.median(ncyc))} "
              f"max={max(ncyc)} total={sum(ncyc):,}")
        print(f"  channels: {chans}")
        print(f"  barcodes: {sorted(set(b.upper() for b in bars if b))[:6]}"
              f"{' ...' if len(set(bars)) > 6 else ''} ({len(set(b.upper() for b in bars if b))} distinct)")
        print(f"  distinct policies ({len(set(pol))}): {sorted(set(pol))[:8]}"
              f"{' ...' if len(set(pol)) > 8 else ''}")
        # overlap with the published dataset, on barcode
        pub = set()
        for d in matr.BATCH_DATES:
            for r in matr.read_batch_metadata(d):
                pub.add(r.barcode.upper())
        mine = {b.upper() for b in bars if b}
        print(f"  barcodes shared with the published 135 cells: {len(mine & pub)}")


def main() -> None:
    seen = set()
    for p in CANDIDATES:
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        describe(p)


if __name__ == "__main__":
    main()
