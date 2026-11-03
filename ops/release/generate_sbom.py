from __future__ import annotations
import json, re, tomllib
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

ROOT=Path(__file__).resolve().parents[2]
components=[]

def add(name, version, kind="library", purl=None):
    c={"type":kind,"name":name,"version":str(version)}
    if purl: c["purl"]=purl
    components.append(c)

py=tomllib.loads((ROOT/'backend/pyproject.toml').read_text())
for dep in py['project']['dependencies']:
    m=re.match(r'([^=\[\]]+)(?:\[[^\]]+\])?==(.+)',dep)
    if m:add(m.group(1),m.group(2),purl=f"pkg:pypi/{m.group(1).lower()}@{m.group(2)}")
for dep in py['project']['optional-dependencies']['dev']:
    m=re.match(r'([^=\[\]]+)(?:\[[^\]]+\])?==(.+)',dep)
    if m:add(m.group(1),m.group(2),purl=f"pkg:pypi/{m.group(1).lower()}@{m.group(2)}")

pkg=json.loads((ROOT/'apps/frontend/package.json').read_text())
for section in ('dependencies','devDependencies'):
    for name,version in pkg.get(section,{}).items():add(name,version,purl=f"pkg:npm/{name}@{version}")

compose=(ROOT/'docker-compose.yml').read_text()
for image in sorted(set(re.findall(r'image:\s*([^\s]+)',compose))):
    if ':' in image:
        name,version=image.rsplit(':',1)
        add(name,version,'container',f"pkg:docker/{name}@{version}")

doc={
  "bomFormat":"CycloneDX","specVersion":"1.6","serialNumber":f"urn:uuid:{uuid5(NAMESPACE_URL,'kusys-1.0.0')}","version":1,
  "metadata":{"component":{"type":"application","name":"KuSys","version":"1.0.0"}},
  "components":sorted(components,key=lambda x:(x['type'],x['name'].lower(),x['version']))
}
(ROOT/'SBOM.cdx.json').write_text(json.dumps(doc,indent=2,ensure_ascii=False)+"\n")
print(f"SBOM components: {len(components)}")
