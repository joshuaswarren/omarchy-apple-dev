#!/usr/bin/env python3
import json, os, sys, time
os.environ.setdefault("MLX_DISABLE_COMPILE", "1")
os.environ.setdefault("VK_DRIVER_FILES", "/usr/share/vulkan/icd.d/asahi_icd.aarch64.json")
import mlx.core as mx
geom = sys.argv[1] if len(sys.argv) > 1 else "default"
if geom != "default":
    os.environ["MLX_OMARCHY_QMM_GEOM"] = geom
k, n, gs, bits = 2560, 320, 64, 4
mx.random.seed(320)
x = mx.random.normal((1, 1, k)).astype(mx.bfloat16)
w = (mx.random.normal((n, k)) * 0.05).astype(mx.bfloat16)
wq, scales, biases = mx.quantize(w, group_size=gs, bits=bits)
mx.eval(x, wq, scales, biases)
mx.eval(mx.quantized_matmul(x, wq, scales, biases, transpose=True, group_size=gs, bits=bits))
t0 = time.perf_counter()
out = mx.quantized_matmul(x, wq, scales, biases, transpose=True, group_size=gs, bits=bits)
mx.eval(out)
wall_ms = (time.perf_counter() - t0) * 1e3
nbytes = k * 2 + n * k // 2
print(json.dumps({"geom": "2x16(default G17C)" if geom=="default" else geom, "wall_ms": round(wall_ms,4), "gbs_roof": round(nbytes/(wall_ms*1e-3)/1e9,2), "nbytes": nbytes}))
