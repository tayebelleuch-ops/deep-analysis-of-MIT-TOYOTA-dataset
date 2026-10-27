import sys
import h5py
import numpy as np

path = sys.argv[1]
with h5py.File(path, "r") as f:
    def walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            print(f"  DS  {name}: shape={obj.shape} dtype={obj.dtype} attrs={ {k:v for k,v in obj.attrs.items() if k!='H5PATH'} }")
        else:
            print(f"  GRP {name}: keys={list(obj.keys())}")
    print("### #subsystem# tree")
    f["#subsystem#"].visititems(walk)
    print("\n### batch_date")
    bd = f["batch_date"]
    print("  ", bd, dict(bd.attrs))
    a = bd[()]
    print("  raw", np.ravel(a)[:20], "->", repr(np.ravel(a).astype(np.uint32).tobytes().decode('utf-32-le', errors='replace') if a.dtype==np.uint32 else ''.join(chr(c) for c in np.ravel(a))))
