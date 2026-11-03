import json,hashlib,sys,os
D=sys.argv[1]
spec=json.loads(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),"spec.json")).read())
out={}
for f,s in spec.items():
    a=open(os.path.join(D,f),"rb").read()
    if hashlib.sha256(a).hexdigest()!=s["old"]:
        print("MISMATCH old",f); sys.exit(1)
    lines=a.splitlines(True)
    for i1,i2,t in sorted(s["ops"],key=lambda o:-o[0]):
        lines[i1:i2]=[t.encode()] if t else []
    r=b"".join(lines)
    if hashlib.sha256(r).hexdigest()!=s["new"]:
        print("MISMATCH new",f); sys.exit(1)
    out[f]=r
for f,r in out.items():
    open(os.path.join(D,f),"wb").write(r)
    print("patched",f)
