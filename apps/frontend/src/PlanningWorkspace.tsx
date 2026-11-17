import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material'
import { api, me } from './api'
import { GanttChart } from './GanttChart'

export function PlanningReadiness({projectId}:{projectId:string}) {
  const packages=useQuery({queryKey:['workpackages',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/work-packages`)})
  const runs=useQuery({queryKey:['engineering-runs',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/analysis-runs`),enabled:packages.isSuccess&&!packages.data?.length})
  if(packages.data?.length)return null
  const candidate=runs.data?.find(run=>run.result?.work_packages?.length&&!run.activated_at)
  const quality=candidate?.result?.quality
  return <Alert severity={quality?.status==='blocked'?'warning':'info'}>
    {candidate?`${candidate.result.work_packages.length} Arbeitspakete liegen als Analyseentwurf vor. ${quality?.status==='blocked'?`Review blockiert: ${quality.findings?.length??0} offene Befunde nach ${quality.rounds_completed}/${quality.max_rounds} Runden.`:'Der geprüfte Entwurf muss noch übernommen werden.'}`:'Es sind noch keine Arbeitspakete im aktiven Projektstand vorhanden.'}
    <Box sx={{mt:1}}><Button component={Link} to={`/projects/${projectId}/requirements`}>Engineering & Review öffnen</Button></Box>
    {quality?.status==='blocked'&&quality.max_rounds<3&&<Typography variant="body2">Dieser Lauf war auf {quality.max_rounds} Review-Runde(n) begrenzt. Firmen-Admins können die Rundenzahl unter Einstellungen · Agenten erhöhen. Fachliche Rückfragen müssen im Prüfschritt geklärt werden.</Typography>}
  </Alert>
}

export function PlanningWorkspace({projectId}:{projectId:string}) {
  const client=useQueryClient()
  const auth=useQuery({queryKey:['me'],queryFn:me})
  const project=useQuery({queryKey:['project',projectId],queryFn:()=>api<any>(`/projects/${projectId}`)})
  const packages=useQuery({queryKey:['workpackages',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/work-packages`)})
  const schedule=useQuery({queryKey:['schedule',projectId],queryFn:()=>api<any>(`/projects/${projectId}/schedule`),enabled:!!packages.data?.length})
  const rates=useQuery({queryKey:['rates',projectId],queryFn:()=>api<any>(`/projects/${projectId}/rate-card`)})
  const drafts=useQuery({queryKey:['engineering-runs',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/analysis-runs`),enabled:packages.isSuccess&&!packages.data?.length})
  const [editing,setEditing]=useState<any>(null)
  const [rate,setRate]=useState<any>(null)
  const [start,setStart]=useState<string|null>(null)
  const canManage=(auth.data?.project_roles??[]).some((x:any)=>x.project_id===projectId&&x.role==='project_lead')||(auth.data?.tenant_roles??[]).some((x:any)=>x.tenant_id===project.data?.tenant_id&&x.role==='company_admin')
  const canEdit=canManage||(auth.data?.project_roles??[]).some((x:any)=>x.project_id===projectId&&x.role==='project_member')
  const refresh=async()=>{await Promise.all(['workpackages','schedule','rates','project','offers','offer-preview','engineering-runs'].map(key=>client.invalidateQueries({queryKey:key==='offer-preview'?[key]:[key,projectId]})))}
  const savePackage=useMutation({mutationFn:()=>api(`/work-packages/${editing.id}`,{method:'PATCH',body:JSON.stringify({expected_version:editing.lock_version,name:editing.name,description:editing.description,role_name:editing.role_name,min_hours:Number(editing.min_hours),likely_hours:Number(editing.likely_hours),max_hours:Number(editing.max_hours),plan_hours:Number(editing.plan_hours),max_fte:Number(editing.max_fte)})}),onSuccess:async()=>{setEditing(null);await refresh()}})
  const saveRate=useMutation({mutationFn:()=>api(`/rate-card-roles/${rate.id}`,{method:'PATCH',body:JSON.stringify({expected_version:rate.lock_version,capacity_fte:Number(rate.capacity_fte),sales_rate:Number(rate.sales_rate),...(rate.kind==='external'?{purchase_rate:Number(rate.cost)}:{internal_cost_rate:Number(rate.cost)})})}),onSuccess:async()=>{setRate(null);await refresh()}})
  const saveStart=useMutation({mutationFn:()=>api(`/projects/${projectId}`,{method:'PATCH',body:JSON.stringify({expected_version:project.data.lock_version,planned_start:start})}),onSuccess:async()=>{setStart(null);await refresh()}})
  const draft=drafts.data?.find(run=>run.result?.work_packages?.length&&!run.activated_at)
  const rows=packages.data?.length?packages.data:draft?.result?.work_packages??[]
  const isDraft=!packages.data?.length
  const editValid=editing&&editing.name.trim()&&Number(editing.min_hours)>=0&&Number(editing.min_hours)<=Number(editing.likely_hours)&&Number(editing.likely_hours)<=Number(editing.max_hours)&&Number(editing.plan_hours)>=0&&Number(editing.max_fte)>0
  return <Stack spacing={2}>
    <Stack direction="row" sx={{justifyContent:'space-between',alignItems:'center',gap:1}}><Typography variant="h6">Arbeitspakete & Terminplan</Typography><Button component={Link} to={`/projects/${projectId}/offers`} variant="contained" disabled={isDraft||schedule.isError||schedule.isPending}>Weiter zum Angebot</Button></Stack>
    {[packages.error,project.error,rates.error].filter(Boolean).map((error,i)=><Alert key={i} severity="error">{String(error)}</Alert>)}
    {packages.isPending?<Typography>Planung wird geladen …</Typography>:isDraft&&<PlanningReadiness projectId={projectId}/>}
    <Card><CardContent><Stack spacing={2}>
      <Typography variant="h6">Planungsgrundlage</Typography>
      <Stack direction={{xs:'column',sm:'row'}} spacing={1} sx={{alignItems:{sm:'center'}}}>
        <TextField label="Geplanter Projektstart" type="date" value={start??project.data?.planned_start??''} onChange={e=>setStart(e.target.value)} slotProps={{inputLabel:{shrink:true}}} disabled={!canManage||saveStart.isPending}/>
        {canManage&&<Button onClick={()=>saveStart.mutate()} disabled={!start||saveStart.isPending}>Startdatum speichern</Button>}
      </Stack>
      {!project.data?.planned_start&&<Typography variant="body2" color="text.secondary">Ohne festgelegtes Startdatum wird ab heute gerechnet.</Typography>}
      {saveStart.error&&<Alert severity="error">{String(saveStart.error)}</Alert>}
      {isDraft?<Typography>Termine werden nach Übernahme der Arbeitspakete berechnet.</Typography>:schedule.isError?<Alert severity="error">Terminplan konnte nicht berechnet werden: {String(schedule.error)}. Abhängigkeiten und verfügbare Kapazitäten prüfen.</Alert>:<Typography>Projektende: {schedule.data?.project_finish??'Wird berechnet …'} · Planaufwand: {packages.data?.reduce((sum,wp)=>sum+Number(wp.plan_hours),0)} Personenstunden</Typography>}
    </Stack></CardContent></Card>
    {!isDraft&&schedule.data&&<GanttChart workPackages={packages.data??[]} schedule={schedule.data}/>}
    <Card><CardContent><Typography variant="h6">{isDraft?'Arbeitspaket-Entwurf aus der Analyse':'Aktive Arbeitspakete'}</Typography>
      {!!rows.length&&<Box sx={{overflowX:'auto'}}><Table size="small"><TableHead><TableRow><TableCell>ID / Arbeitspaket</TableCell><TableCell>Fachrolle</TableCell><TableCell>Min / wahrscheinlich / Max (h)</TableCell><TableCell>Plan (h)</TableCell><TableCell>Vorgänger</TableCell><TableCell>Termin</TableCell><TableCell/></TableRow></TableHead><TableBody>
        {rows.map((wp:any)=>{const dates=schedule.data?.packages.find((item:any)=>item.id===wp.id);return <TableRow key={wp.id??wp.key}>
          <TableCell><Typography variant="body2" sx={{fontWeight:600}}>{wp.key} · {wp.name}</Typography><Typography variant="caption">{wp.description}</Typography>{isDraft&&<Typography variant="caption" sx={{display:"block"}}>SYS: {wp.system_requirement_keys?.join(', ')}</Typography>}</TableCell>
          <TableCell>{wp.role_name??wp.role}</TableCell><TableCell>{wp.min_hours} / {wp.likely_hours} / {wp.max_hours}</TableCell><TableCell>{wp.plan_hours??wp.likely_hours}</TableCell>
          <TableCell>{isDraft?wp.depends_on?.join(', ')||'—':wp.predecessor_ids?.map((id:string)=>packages.data?.find(item=>item.id===id)?.key??id).join(', ')||'—'}</TableCell>
          <TableCell>{dates?`${dates.start} → ${dates.finish}`:'Noch nicht geplant'}{dates?.critical&&<Chip size="small" color="warning" label="Kritischer Pfad"/>}</TableCell>
          <TableCell>{!isDraft&&canEdit&&<Button onClick={()=>{savePackage.reset();setEditing({...wp})}}>Bearbeiten</Button>}</TableCell>
        </TableRow>})}
      </TableBody></Table></Box>}
      {isDraft&&!!rows.length&&<Typography variant="body2" sx={{mt:1}}>Entwurf ist schreibgeschützt. Freigabe und Übernahme erfolgen unter Anforderungen → Engineering & Review.</Typography>}
    </CardContent></Card>
    <Card><CardContent><Typography variant="h6">Kapazitäten & Stundensätze</Typography><Typography variant="body2" color="text.secondary">Verfügbare FTE bestimmen die Terminierung; Kosten- und Verkaufssätze fließen ins Angebot ein.</Typography><Box sx={{overflowX:'auto'}}><Table size="small"><TableHead><TableRow><TableCell>Rolle</TableCell><TableCell>FTE</TableCell><TableCell>Kosten / h (€)</TableCell><TableCell>Verkauf / h (€)</TableCell><TableCell/></TableRow></TableHead><TableBody>
      {rates.data?.roles.map((item:any)=><TableRow key={item.id}><TableCell>{item.name}</TableCell><TableCell>{item.capacity_fte}</TableCell><TableCell>{item.internal_cost_rate??item.purchase_rate??'0'}</TableCell><TableCell>{item.sales_rate}</TableCell><TableCell>{canManage&&<Button onClick={()=>{saveRate.reset();setRate({...item,cost:item.internal_cost_rate??item.purchase_rate??'0'})}}>Bearbeiten</Button>}</TableCell></TableRow>)}
    </TableBody></Table></Box></CardContent></Card>
    <Dialog open={!!editing} onClose={()=>{if(!savePackage.isPending)setEditing(null)}} fullWidth><DialogTitle>Arbeitspaket bearbeiten</DialogTitle><DialogContent><Stack spacing={2} sx={{pt:1}}>
      <TextField label="Name" value={editing?.name??''} onChange={e=>setEditing({...editing,name:e.target.value})}/>
      <TextField label="Beschreibung" multiline value={editing?.description??''} onChange={e=>setEditing({...editing,description:e.target.value})}/>
      <TextField select label="Fachrolle" value={editing?.role_name??''} onChange={e=>setEditing({...editing,role_name:e.target.value})}>{rates.data?.roles.map((item:any)=><MenuItem key={item.id} value={item.name}>{item.name}</MenuItem>)}</TextField>
      {(['min_hours','likely_hours','max_hours','plan_hours','max_fte'] as const).map(field=><TextField key={field} type="number" label={{min_hours:'Minimum (h)',likely_hours:'Wahrscheinlich (h)',max_hours:'Maximum (h)',plan_hours:'Planaufwand (h)',max_fte:'Maximale FTE des Pakets'}[field]} value={editing?.[field]??''} onChange={e=>setEditing({...editing,[field]:e.target.value})} slotProps={{htmlInput:{min:0,step:field==='max_fte'?0.1:1}}}/>)}
      {savePackage.error&&<Alert severity="error">{String(savePackage.error)}</Alert>}
    </Stack></DialogContent><DialogActions><Button disabled={savePackage.isPending} onClick={()=>setEditing(null)}>Abbrechen</Button><Button variant="contained" disabled={!editValid||savePackage.isPending} onClick={()=>savePackage.mutate()}>Speichern & neu berechnen</Button></DialogActions></Dialog>
    <Dialog open={!!rate} onClose={()=>{if(!saveRate.isPending)setRate(null)}} fullWidth><DialogTitle>{rate?.name} · Kapazität & Sätze</DialogTitle><DialogContent><Stack spacing={2} sx={{pt:1}}>
      {(['capacity_fte','cost','sales_rate'] as const).map(field=><TextField key={field} type="number" label={{capacity_fte:'Verfügbare Kapazität (FTE)',cost:'Kosten je Stunde (€)',sales_rate:'Verkauf je Stunde (€)'}[field]} value={rate?.[field]??''} onChange={e=>setRate({...rate,[field]:e.target.value})} slotProps={{htmlInput:{min:0,step:0.1}}}/>)}
      {saveRate.error&&<Alert severity="error">{String(saveRate.error)}</Alert>}
    </Stack></DialogContent><DialogActions><Button disabled={saveRate.isPending} onClick={()=>setRate(null)}>Abbrechen</Button><Button variant="contained" disabled={saveRate.isPending||!rate||['capacity_fte','cost','sales_rate'].some(field=>!Number.isFinite(Number(rate[field]))||Number(rate[field])<0)} onClick={()=>saveRate.mutate()}>Speichern & neu berechnen</Button></DialogActions></Dialog>
  </Stack>
}
