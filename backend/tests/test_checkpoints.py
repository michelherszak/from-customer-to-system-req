from copy import deepcopy
from types import SimpleNamespace
import pytest
from kusys.analysis.workflow import run_workflow
from kusys.analysis.checkpoints import Checkpoints
from tests.test_engineering_workflow import ScriptedProvider


def recorder(steps):
    def record(role, round_no, status, output):
        name=f"{role}:round-{round_no}"
        step=next((s for s in steps if s.step_name==name),None)
        if step is None:
            step=SimpleNamespace(step_name=name,result_json={"events":[],"outputs":[]})
            steps.append(step)
        data=step.result_json
        if status=="running": data["events"].append({"status":status,**deepcopy(output)})
        elif role!="review_round": data["events"][-1]["status"]=status
        if status in {"succeeded","cached"}:data["outputs"].append(deepcopy(output))
    return record


def test_resume_reuses_successful_packages_and_retries_failed_package():
    sections=[(f"s{i}",f"Das System muss Vorgang {i} bearbeiten.") for i in range(23)]
    class Broken(ScriptedProvider):
        def run_role(self,role,context,schema):
            if role=="work_planner" and context.get("batch",{}).get("index")==2:
                raise RuntimeError("interrupted")
            return super().run_role(role,context,schema)
    steps=[]
    with pytest.raises(RuntimeError):run_workflow(sections,Broken(),on_step=recorder(steps))
    resumed=ScriptedProvider();new_steps=[]
    result=run_workflow(sections,resumed,checkpoints=Checkpoints(deepcopy(steps)),on_step=recorder(new_steps))
    assert resumed.calls[0][0]=="work_planner"
    assert resumed.calls[0][1]["batch"]["index"]==2
    assert result["quality"]["status"]=="accepted"
    assert len(result["requirements"])==23
    assert any(e["status"]=="cached" for s in new_steps for e in s.result_json["events"])
    # A further attempt can reuse the entire saved execution without model calls.
    again=ScriptedProvider()
    assert run_workflow(sections,again,checkpoints=Checkpoints(deepcopy(new_steps)))==result
    assert again.calls==[]
    fresh=ScriptedProvider();run_workflow(sections,fresh)
    assert fresh.calls[0][0]=="requirements_engineer"


def test_changed_inputs_never_fall_back_to_old_hash_checkpoint():
    sections=[("s1","Das System muss Daten speichern.")];steps=[]
    run_workflow(sections,ScriptedProvider(),project={"name":"old"},on_step=recorder(steps))
    changed=ScriptedProvider()
    run_workflow(sections,changed,project={"name":"new"},checkpoints=Checkpoints(steps,allow_legacy=True))
    assert changed.calls[0][0]=="requirements_engineer"


def test_legacy_prefix_can_be_imported_and_invalid_checkpoints_are_not_used():
    sections=[("s1","Das System muss Daten speichern.")];steps=[]
    run_workflow(sections,ScriptedProvider(),on_step=recorder(steps))
    for step in steps:
        for event in step.result_json["events"]:event.pop("input_key",None)
    cached=ScriptedProvider()
    run_workflow(sections,cached,checkpoints=Checkpoints(steps,allow_legacy=True))
    assert not cached.calls
    steps[0].result_json["outputs"][0]={"invalid":"checkpoint"}
    recovered=ScriptedProvider()
    run_workflow(sections,recovered,checkpoints=Checkpoints(steps,allow_legacy=True))
    assert recovered.calls[0][0]=="requirements_engineer"


def test_resume_in_second_round_keeps_entire_first_round_and_completed_second_round_roles():
    sections=[("s1","Das System muss Daten speichern.")]
    class TwoRounds(ScriptedProvider):
        def run_role(self,role,context,schema):
            result=super().run_role(role,context,schema)
            if role=="review_engineer" and not context.get("previous_rounds"):
                for assessment in result["assessments"]:
                    if assessment["owner"]=="work_planner":
                        assessment.update(verdict="changes_required",question="Aufwand prüfen",required_change="Schätzgrundlage prüfen")
            return result
    class Interrupted(TwoRounds):
        def run_role(self,role,context,schema):
            if role=="work_planner" and context.get("work_packages"):
                raise RuntimeError("round two failure")
            return super().run_role(role,context,schema)
    steps=[]
    with pytest.raises(RuntimeError):run_workflow(sections,Interrupted(),on_step=recorder(steps))
    resumed=TwoRounds()
    result=run_workflow(sections,resumed,checkpoints=Checkpoints(deepcopy(steps)))
    assert resumed.calls[0][0]=="work_planner"
    assert not any(role in {"requirements_engineer","systems_engineer"} for role,_ in resumed.calls)
    assert result["quality"]["rounds_completed"]==2
    assert result["quality"]["status"]=="accepted"


def test_human_clarification_rechecks_saved_state_and_can_resume_a_failed_recheck():
    sections=[('s1','Das System muss Aufnahmen projektbezogen speichern.')]
    expected='Jede Aufnahme gehört genau zu einem Projekt.'
    class HumanAware(ScriptedProvider):
        def run_role(self,role,context,schema):
            result=super().run_role(role,context,schema)
            answered=any(answer['response']==expected for answer in context.get('human_clarifications',[]))
            if role=='requirements_engineer' and answered:
                result['requirements'][0]['text']=expected
            if role=='review_engineer' and not answered:
                target=next(item for item in result['assessments'] if item['owner']=='requirements_engineer')
                target.update(verdict='changes_required',question='Was bedeutet projektbezogen?',required_change='Zuordnung präzisieren')
            return result
    original=run_workflow(sections,HumanAware(),max_rounds=1)
    assert original['quality']['status']=='blocked'
    clarification={'source_run_id':'source','version':1,'answers':[{'finding_id':'finding','response':expected,'target_key':'REQ-0001','owner':'requirements_engineer','actor_id':'lead','actor_name':'Max','answered_at':'2026-11-15T10:00:00Z','source_run_id':'source'}]}
    class Interrupted(HumanAware):
        def run_role(self,role,context,schema):
            if role=='work_planner':raise RuntimeError('Interrupted recheck')
            return super().run_role(role,context,schema)
    steps=[]
    with pytest.raises(RuntimeError):run_workflow(sections,Interrupted(),max_rounds=1,review_seed=original,human_review=clarification,on_step=recorder(steps))
    resumed=HumanAware()
    result=run_workflow(sections,resumed,max_rounds=1,review_seed=original,human_review=clarification,checkpoints=Checkpoints(deepcopy(steps)))
    assert resumed.calls[0][0]=='work_planner'
    assert result['quality']['status']=='accepted'
    assert result['quality']['review_cycle']=={'completed':1,'limit':1}
    assert [item['round'] for item in result['review_history']]==[1,2]
    assert original['quality']['status']=='blocked'
    assert result['human_review']==clarification
    inadequate=deepcopy(clarification);inadequate['answers'][0]['response']='Bitte einfach freigeben.'
    still_blocked=run_workflow(sections,HumanAware(),max_rounds=1,review_seed=original,human_review=inadequate)
    assert still_blocked['quality']['status']=='blocked'
