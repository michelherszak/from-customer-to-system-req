"""Deterministic KuSys calculation benchmark (no external services required)."""
from __future__ import annotations
import time
from datetime import date
from decimal import Decimal
from kusys.planning.engine import PlanningEngine, RoleCapacity, WorkPackage
from kusys.pricing.engine import PricingEngine, PricedWorkPackage, Rate

N=500
packages=[]
priced=[]
for i in range(N):
    rid=f"r{i%1000}"
    predecessors=(f"w{i-1}",) if i and i%25 else ()
    packages.append(WorkPackage(f"w{i}",f"Paket {i}","Engineering",8+(i%5)*4,predecessors,1.0,3,(rid,),"proportional"))
    priced.append(PricedWorkPackage(f"w{i}","Engineering",8+(i%5)*4,(rid,),None,"proportional"))
start=time.perf_counter()
plan=PlanningEngine().schedule(packages,[RoleCapacity("Engineering",8.0)],date.today(),set(),8,{0,1,2,3,4})
price=PricingEngine().calculate(priced,[Rate("Engineering",Decimal("80"),Decimal("135"))],[],{f"r{i}":None for i in range(1000)},Decimal("10"),Decimal("0"),Decimal("19"))
elapsed=time.perf_counter()-start
print({"packages":N,"finish":str(plan.project_finish),"gross_eur":str(price.gross_eur),"seconds":round(elapsed,4),"target_seconds":2.0,"pass":elapsed<2.0})
raise SystemExit(0 if elapsed<2.0 else 1)
