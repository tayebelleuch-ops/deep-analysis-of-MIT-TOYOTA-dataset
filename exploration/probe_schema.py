"""Read-only probe of the MATR v7.3 (.mat/HDF5) batch structs: report the schema."""
import sys
import h5py
import numpy as np


def decode_matlab_string(f, ref):
    raw = f[ref][()]
    return raw.tobytes()[::2].decode(errors="replace")


def probe(path):
    print(f"\n{'='*78}\nFILE: {path}\n{'='*78}")
    with h5py.File(path, "r") as f:
        print("top-level keys:", list(f.keys()))
        batch = f["batch"]
        print("batch type:", type(batch), "keys:", list(batch.keys()))
        for k in batch.keys():
            d = batch[k]
            print(f"  batch[{k!r}]: shape={d.shape} dtype={d.dtype}")
        n = batch["summary"].shape[0]
        print(f"\nnum cells (batch['summary'].shape[0]) = {n}")

        # --- descriptors on cell 0
        print("\n-- cell 0 scalar/descriptor fields --")
        for k in batch.keys():
            if k in ("summary", "cycles"):
                continue
            ref = batch[k][0, 0]
            obj = f[ref]
            arr = obj[()]
            info = f"shape={getattr(arr,'shape',None)} dtype={getattr(arr,'dtype',None)}"
            txt = ""
            try:
                if arr.dtype.kind in "ui" and arr.size > 1:
                    txt = "  as_str=" + repr(arr.tobytes()[::2].decode(errors="replace"))
            except Exception:
                pass
            print(f"  {k}: {info}  raw={np.ravel(arr)[:6]}{txt}")

        # --- summary fields
        s = f[batch["summary"][0, 0]]
        print("\n-- summary group (cell 0) --")
        print("  keys:", list(s.keys()))
        for k in s.keys():
            print(f"    {k}: shape={s[k].shape} dtype={s[k].dtype}")
        cyc = np.hstack(s["cycle"][0, :].tolist()) if s["cycle"].shape[0] == 1 else np.ravel(s["cycle"][()])
        print(f"  summary['cycle'] first 8 = {cyc[:8]}  last 3 = {cyc[-3:]}  len={len(cyc)}")

        # --- cycles group
        c = f[batch["cycles"][0, 0]]
        print("\n-- cycles group (cell 0) --")
        print("  keys:", list(c.keys()))
        for k in c.keys():
            print(f"    {k}: shape={c[k].shape} dtype={c[k].dtype}")
        ncyc = c["I"].shape[0]
        print(f"  n cycle entries = {ncyc}")
        for k in c.keys():
            a = np.ravel(f[c[k][0, 0]][()])
            print(f"    cycles[{k}][0]: len={a.size} first={a[:3]} last={a[-3:]}")

        # Vdlin check
        if "Vdlin" in c.keys():
            v0 = np.ravel(f[c["Vdlin"][0, 0]][()])
            print(f"  Vdlin[0]: len={v0.size} range=({v0[0]}, {v0[-1]})")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        probe(p)
