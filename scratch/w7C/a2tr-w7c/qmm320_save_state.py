#!/usr/bin/env python3
import os, mlx.core as mx
os.environ.setdefault("MLX_DISABLE_COMPILE","1")
os.environ.setdefault("VK_DRIVER_FILES","/usr/share/vulkan/icd.d/asahi_icd.aarch64.json")
k,n,gs,bits=2560,320,64,4
mx.random.seed(320)
x=mx.random.normal((1,k)).astype(mx.bfloat16)
w=(mx.random.normal((n,k))*0.02).astype(mx.bfloat16)
wq,s,b=mx.quantize(w,group_size=gs,bits=bits)
mx.eval(x,wq,s,b)
mx.save_safetensors("/tmp/qmm320_state.safetensors",{"x":x,"wq":wq,"s":s,"b":b})
for _ in range(8): mx.eval(mx.quantized_matmul(x,wq,s,b,transpose=True,group_size=gs,bits=bits))
print("saved")
