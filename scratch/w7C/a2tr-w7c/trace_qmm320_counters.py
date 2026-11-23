#!/usr/bin/env python3
import ctypes, importlib.metadata, json, os, time
os.environ.setdefault("MLX_DISABLE_COMPILE","1")
import mlx.core as mx
class TS(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint64) for n in (
        "gpu_primitive_dispatches","vk_submissions","vk_buffer_copies","vk_buffer_fills",
        "vk_compute_dispatches","omarchy_finalize_calls","commit_calls_with_work",
        "commit_calls_noop","barriers_emitted","barriers_skipped")]
lib=ctypes.CDLL(str(importlib.metadata.distribution("mlx-omarchy").locate_file("mlx/lib/libmlx.so")))
abi=lib.mlx_omarchy_trace_snapshot_abi_size(); assert abi==ctypes.sizeof(TS)
snap=lib.mlx_omarchy_trace_snapshot; snap.argtypes=[ctypes.POINTER(TS)]
def snap_dict():
    s=TS(); snap(ctypes.byref(s)); return {n:int(getattr(s,n)) for n,_ in TS._fields_}
k,n,gs,bits=2560,320,64,4
mx.random.seed(320)
x=mx.random.normal((1,k)).astype(mx.bfloat16)
w=(mx.random.normal((n,k))*0.02).astype(mx.bfloat16)
wq,s,b=mx.quantize(w,group_size=gs,bits=bits)
mx.eval(x,wq,s,b)
for _ in range(8): mx.eval(mx.quantized_matmul(x,wq,s,b,transpose=True,group_size=gs,bits=bits))
b0=snap_dict(); t0=time.perf_counter()
mx.eval(mx.quantized_matmul(x,wq,s,b,transpose=True,group_size=gs,bits=bits))
wall=(time.perf_counter()-t0)*1e3
b1=snap_dict(); d={k:b1[k]-b0[k] for k in b1}; d.update(wall_ms=round(wall,4), gbs=round((k*2+n*k//2)/(wall*1e-3)/1e9,2))
print(json.dumps(d,sort_keys=True))
