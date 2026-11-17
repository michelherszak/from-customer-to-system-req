"""Bounded role outputs; complete cross-reference checks still run over the whole graph."""
from kusys.analysis.contracts import SystemDesign, Plan, Review

BATCH_SIZE = 10

def chunks(items):
    return [items[i:i+BATCH_SIZE] for i in range(0,len(items),BATCH_SIZE)]


def derive_systems(call, base, requirements, previous, feedback, round_no):
    bundles = chunks(requirements)
    if len(bundles) == 1:
        return call("systems_engineer",{**base,"requirements":requirements,"previous":previous,"feedback":feedback},SystemDesign,round_no)
    result={"system_requirements":[],"architecture":[]}
    for index, bundle in enumerate(bundles,1):
        req_ids={r["key"] for r in bundle}
        out=call("systems_engineer",{**base,"requirements":bundle,
            "previous":[s for s in previous if req_ids.intersection(s["parent_keys"])],
            "feedback":[f for f in feedback if f["target_key"] in req_ids or any(f["target_key"]==s["key"] and req_ids.intersection(s["parent_keys"]) for s in previous)],
            "batch":{"index":index,"count":len(bundles)},"instruction":"Nur die übergebenen Anforderungen technisch ableiten."},SystemDesign,round_no)
        mapping={s["key"]:f"SYS-{index:03d}-{i:03d}" for i,s in enumerate(out["system_requirements"],1)}
        if len(mapping)!=len(out["system_requirements"]):raise ValueError("Doppelte System-IDs innerhalb eines Pakets")
        for s in out["system_requirements"]:s["key"]=mapping[s["key"]]
        for i,a in enumerate(out["architecture"],1):
            a["key"]=f"ARC-{index:03d}-{i:03d}"
            a["covers"]=[mapping.get(key,key) for key in a["covers"]]
        result["system_requirements"].extend(out["system_requirements"])
        result["architecture"].extend(out["architecture"])
    return result


def plan_work(call, base, result, feedback, round_no):
    bundles=chunks(result["system_requirements"])
    if len(bundles)==1:
        return call("work_planner",{**base,**result,"feedback":feedback},Plan,round_no)
    packages=[]
    for index,bundle in enumerate(bundles,1):
        sys_ids={s["key"] for s in bundle}; req_ids={k for s in bundle for k in s["parent_keys"]}
        out=call("work_planner",{**base,"requirements":[r for r in result["requirements"] if r["key"] in req_ids],
            "system_requirements":bundle,"architecture":[a for a in result["architecture"] if sys_ids.intersection(a["covers"])],
            "previous":[w for w in result["work_packages"] if sys_ids.intersection(w["system_requirement_keys"])],
            "existing_package_index":[{"key":w["key"],"name":w["name"]} for w in packages],
            "feedback":feedback,"batch":{"index":index,"count":len(bundles)}},Plan,round_no)
        mapping={w["key"]:f"AP-{index:03d}-{i:03d}" for i,w in enumerate(out["work_packages"],1)}
        if len(mapping)!=len(out["work_packages"]):raise ValueError("Doppelte Arbeitspaket-IDs innerhalb eines Pakets")
        for w in out["work_packages"]:
            w["key"]=mapping[w["key"]]
            w["depends_on"]=[mapping.get(key,key) for key in w["depends_on"]]
        packages.extend(out["work_packages"])
    return {"work_packages":packages}


def review_all(call, base, result, history, code_findings, round_no):
    # The reviewer's only sparring partner is the systems engineer.
    compact = {
        "requirements": [{"key": x["key"], "text": x["text"], "priority": x["priority"], "source_section_id": x["source_section_id"]} for x in result["requirements"]],
        "system_requirements": result["system_requirements"],
        "architecture": result["architecture"],
        "code_findings": [x for x in code_findings if x.get("owner") == "systems_engineer"],
        "previous_rounds": history,
        "instruction": "Prüfe ausschließlich SYS und Architektur. Rückfragen und Korrekturaufträge ausschließlich an den Systems Engineer richten. Keine Bewertung von REQ oder Arbeitspaketen.",
    }
    review = call("review_engineer", {**base, **compact}, Review, round_no)
    expected = {item["key"] for item in result["system_requirements"]}
    seen = set()
    assessments = []
    for assessment in review["assessments"]:
        key = assessment["target_key"]
        if assessment["owner"] == "systems_engineer" and key in expected and key not in seen:
            assessments.append(assessment)
            seen.add(key)
    return {"assessments": assessments, "summary": review["summary"]}
