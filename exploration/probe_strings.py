"""Figure out how barcode / channel_id / policy strings are really encoded."""
import sys
import h5py
import numpy as np

path = sys.argv[1]
with h5py.File(path, "r") as f:
    batch = f["batch"]
    n = batch["summary"].shape[0]
    for k in ("barcode", "channel_id", "policy", "policy_readable"):
        print(f"\n### {k}")
        for i in list(range(3)) + [n - 1]:
            obj = f[batch[k][i, 0]]
            print(f"  cell {i}: hdf5 shape={obj.shape} dtype={obj.dtype} attrs={dict(obj.attrs)}")
            arr = obj[()]
            print(f"    raw   = {np.ravel(arr)[:10]}")
            for view in ("uint16", "uint8"):
                try:
                    v = np.ravel(arr).astype(np.uint64).view if False else None
                except Exception:
                    pass
            try:
                b = np.ravel(arr).tobytes()
                print(f"    bytes = {b[:32]!r}")
                print(f"    utf16 = {b.decode('utf-16-le', errors='replace')!r}")
                print(f"    chr-u16 = {''.join(chr(c) for c in np.ravel(arr).astype(np.uint32) if 0 < c < 0x110000)!r}")
            except Exception as e:
                print("    decode err", e)
