import sys
import h5py
import numpy as np

path = sys.argv[1]
with h5py.File(path, "r") as f:
    mcos = f["#subsystem#"]["MCOS"]
    print("MCOS shape", mcos.shape)
    for i in list(range(4)) + [47, 48, 93, 94]:
        ref = mcos[0, i]
        obj = f[ref]
        a = obj[()]
        print(f"\n-- MCOS[{i}]: shape={obj.shape} dtype={obj.dtype} attrs={ {k:v for k,v in obj.attrs.items() if k!='H5PATH'} }")
        r = np.ravel(a)
        print("   first 48:", r[:48])
        if r.dtype == np.uint8 and r.size > 48:
            print("   ascii:", bytes(r[:200]).decode('latin1').replace('\x00','.'))
