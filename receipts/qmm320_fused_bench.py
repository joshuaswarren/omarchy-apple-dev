#!/usr/bin/env python3
import os, sys, time
os.environ.setdefault("MLX_DISABLE_COMPILE", "1")
os.environ["MLX_OMARCHY_FUSED_GEMV"] = "1"
os.environ.setdefault("VK_DRIVER_FILES", "/usr/share/vulkan/icd.d/asahi_icd.aarch64.json")
import mlx.core as mx
k,n,gs,bits=2560,320,64,4
def make_linear(seed):
    mx.random.seed(seed)
    w=(mx.random.normal((n,k))*0.05).astype(mx.bfloat16)
    wq,s,b=mx.quantize(w, group_size=gs, bits=bits)
    bias=mx.random.normal((n,)).astype(mx.bfloat16)
    mx.eval(wq,s,b,bias)
    return wq,s,b,bias
def forward(x, legs):
    return [mx.add(mx.quantized_matmul(x,wq,s,b,transpose=True,group_size=gs,bits=bits), bias) for wq,s,b,bias in legs]
geom=sys.argv[1] if len(sys.argv)>1 else "default"
if geom!="default": os.environ["MLX_OMARCHY_QMM_GEOM"]=geom
mx.random.seed(320)
x=mx.random.normal((1,1,k)).astype(mx.bfloat16)
mx.eval(x)
legs=[make_linear(320+i) for i in range(3)]
for _ in range(6): mx.eval(forward(x,legs))
best=1e9
for _ in range(5):
    t0=time.perf_counter()
    for _ in range(32): mx.eval(forward(x,legs))
    best=min(best,(time.perf_counter()-t0)/32)
nbytes=3*(k*2+n*k//2)
print(f"mode=fused3 geom={geom} ms={best*1e3:.4f} GB/s={nbytes/best/1e9:.2f}")
