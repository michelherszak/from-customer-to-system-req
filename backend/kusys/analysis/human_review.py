"""Versioned project-lead answers; only a subsequent model review can close findings."""
import hashlib
import json
from sqlalchemy import select
from kusys.persistence.models import AnalysisStep


def findings(run):
    output=[];seen=set()
    for item in ((run.result_json or {}).get('quality') or {}).get('findings',[]):
        identity={key:item.get(key,'') for key in ('target_key','owner','question','required_change','origin')}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
        if key not in seen:
            seen.add(key);output.append({**identity,'finding_id':key})
    return output


def response_step(db, run_id):
    return db.scalar(select(AnalysisStep).where(AnalysisStep.analysis_run_id==run_id,AnalysisStep.step_name=='human_review'))


def snapshot(db, run):
    step=response_step(db,run.id)
    stored=(step.result_json or {}) if step else {}
    answers={answer['finding_id']:answer for answer in ((run.result_json or {}).get('human_review') or {}).get('answers',[])}
    answers.update(stored.get('answers',{}))
    return {'source_run_id':str(run.id),'version':stored.get('version',0),'answers':list(answers.values())}
