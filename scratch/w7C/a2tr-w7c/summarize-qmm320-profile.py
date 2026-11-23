#!/usr/bin/env python3
import json, sys
from pathlib import Path
CH=Path("/var/tmp/compute.h")
KN=[]
if CH.is_file():
    ins=False
    for line in CH.read_text().splitlines():
        if "enum class ComputeKernel" in line: ins=True; continue
        if ins:
            s=line.strip()
            if s.startswith("};"): break
            if s.endswith(",") and not s.startswith("//"): KN.append(s.rstrip(",").strip())
p=Path(sys.argv[1] if len(sys.argv)>1 else "/tmp/w7c-qmm320-word-profile.jsonl")
lines=[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
meta=next((x for x in lines if x.get("k")=="meta"),{})
disp=[x for x in lines if x.get("k")=="d"]
subs=[x for x in lines if x.get("k")=="s"]
joins=[x for x in lines if x.get("k")=="j"]
period=int(meta.get("period_ns") or 0); valid=int(meta.get("valid_bits") or 0)
mask=(1<<valid)-1 if valid else None
def gpu_ns(d):
    t0,t1=d.get("t0"),d.get("t1")
    if t0 is None or t1 is None or not period: return None
    dt=(t1-t0)&mask if mask else (t1-t0)
    if mask and dt>(1<<(valid-1)): dt-=1<<valid
    return dt*period
def kn(op):
    try: return KN[int(op)]
    except: return "op_"+str(op)
print("device",meta.get("device"))
print("dispatches",len(disp),"submissions",len(subs),"joins",len(joins))
for i,d in enumerate(disp):
    gns=gpu_ns(d); name=kn(d.get("op"))
    h=(d.get("h") or 0)/1000; g=(gns/1000) if gns else 0
    print(f"d[{i}] {name} gx={d.get('gx')} gy={d.get('gy')} n={d.get('n')} host_record_us={h:.1f} gpu_us={g:.1f} bar={d.get('bar')}")
    for j,b in enumerate(d.get("b") or []): print(f"  bind{j}: buf={b[0]} off={b[1]} range={b[2]}")
