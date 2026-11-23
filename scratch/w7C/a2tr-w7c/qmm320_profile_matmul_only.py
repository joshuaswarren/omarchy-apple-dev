#!/usr/bin/env python3
import json, os, time, mlx.core as mx
os.environ.setdefault("MLX_DISABLE_COMPILE","1")
os.environ.setdefault("VK_DRIVER_FILES","/usr/share/vulkan/icd.d/asahi_icd.aarch64.json")
d=mx.load("/tmp/qmm320_state.safetensors")
x,wq,s,b=d["x"],d["wq"],d["s"],d["b"]
k,n,gs,bits=2560,320,64,4
t0=time.perf_counter()
mx.eval(mx.quantized_matmul(x,wq,s,b,transpose=True,group_size=gs,bits=bits))
print(json.dumps({"wall_ms":round((time.perf_counter()-t0)*1e3,4)}))
