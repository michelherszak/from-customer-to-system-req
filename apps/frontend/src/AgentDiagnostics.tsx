import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Chip, LinearProgress, Stack, Typography } from '@mui/material'
import { api } from './api'

const names: Record<string, string> = { requirements_engineer: 'Requirements Engineer', systems_engineer: 'Systems Engineer', work_planner: 'Arbeitsplaner & Aufwandsschätzer', review_engineer: 'Review Engineer' }
const tasks: Record<string, string> = { requirements_engineer: 'Extrahiert und strukturiert Kundenanforderungen.', systems_engineer: 'Leitet technische Systemanforderungen und Architektur ab.', work_planner: 'Erstellt Arbeitspakete und schätzt den Aufwand.', review_engineer: 'Prüft jede Zielanforderung und fordert nötige Korrekturen an.' }
const states: Record<string,string> = {running:'Aktiv',succeeded:'Abgeschlossen',failed:'Fehlgeschlagen',cancelled:'Abgebrochen',queued:'Wartet',cached:'Aus Checkpoint übernommen'}
const seconds = (start: string, finish?: string) => Math.max(0, Math.floor(((finish ? Date.parse(finish) : Date.now()) - Date.parse(start)) / 1000))
export function AgentDiagnostics({runId}: {runId:string}) {
  const client = useQueryClient()
  const query = useQuery({queryKey:['agent-diagnostics',runId],queryFn:()=>api<any>(`/analysis-runs/${runId}/diagnostics`),refetchInterval:q=>['running','queued'].includes(q.state.data?.status ?? 'running') ? 2000 : false})
  const cancel = useMutation({mutationFn:()=>api(`/jobs/${query.data.job_id}/cancel`,{method:'POST'}),onSuccess:()=>{void query.refetch();void client.invalidateQueries({queryKey:['engineering-runs']})}})
  const [,tick]=useState(0)
  useEffect(()=>{
    if(!['running','queued'].includes(query.data?.status))return
    const timer=window.setInterval(()=>tick(x=>x+1),1000)
    return()=>window.clearInterval(timer)
  },[query.data?.status])
  const data=query.data
  if(!data)return <Alert severity={query.isError?'error':'info'}>{query.isError?'Diagnose konnte nicht geladen werden.':'Agentenstatus wird geladen …'}</Alert>
  const entries=data.steps.flatMap((step:any)=>step.events.map((event:any)=>({...event,step:step.name,role:step.name.split(':')[0]})))
  const running=['running','queued'].includes(data.status)
  const current=entries.findLast((x:any)=>x.status==='running')
  const latest=entries.at(-1)
  const download=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({...data,exported_at:new Date().toISOString()},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`KuSys-Diagnose-${runId}.json`;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <Box sx={{p:2,border:'1px solid',borderColor:'divider',borderRadius:2}}><Stack spacing={1.5}>
    <Stack direction="row" sx={{alignItems:'center',gap:1,flexWrap:'wrap'}}><Typography variant="subtitle1" sx={{flex:1}}>Agenten live & Diagnose</Typography><Chip size="small" label={states[data.status]??data.status}/>{running&&data.job_id&&<Button color="secondary" variant="outlined" disabled={cancel.isPending||data.job_status==='cancel_requested'} onClick={()=>cancel.mutate()}>{data.job_status==='cancel_requested'?'Stopp angefordert':'Ablauf stoppen & Checkpoint sichern'}</Button>}<Button onClick={download}>Diagnose herunterladen</Button></Stack>
    <Typography variant="caption">Lauf-ID: {runId} · {data.provider} / {data.model_id} · Aktualisierung alle 2 Sekunden während der Verarbeitung</Typography>
    {data.resume_from_run_id&&<Typography variant="body2">Fortsetzung von Lauf {data.resume_from_run_id} · {data.cached_packages??0} Pakete aus Checkpoints übernommen</Typography>}
    <Stack direction="row" sx={{gap:1,flexWrap:'wrap'}}>{Object.entries(names).map(([key,label])=><Chip key={key} label={label} color={running&&current?.role===key?'primary':'default'} variant={running&&current?.role===key?'filled':'outlined'}/>)}</Stack>
    {running&&current&&<><Typography><strong>{names[current.role]??current.role}</strong> · {current.step.split(':')[1]?.replace('round-','Runde ')}{current.batch?` · Paket ${current.batch.index}/${current.batch.count}`:''} · seit {seconds(current.started_at)} s</Typography><Typography variant="body2">{tasks[current.role]} Warte auf Modellantwort.</Typography><LinearProgress/>{seconds(current.started_at)>180&&<Alert severity="warning">Lange Wartezeit. Der letzte gespeicherte Status ist aktiv; dies bestätigt keinen Fortschritt beim Modellanbieter.</Alert>}</>}
    {cancel.error&&<Alert severity="error">Stopp konnte nicht angefordert werden: {String(cancel.error)}</Alert>}
    {data.job_status==='cancel_requested'&&<Alert severity="info">Stopp angefordert. Abgeschlossene Agentenpakete bleiben gespeichert. Der aktuelle Modellaufruf endet spätestens nach drei Minuten; danach kannst du ab dem letzten Checkpoint fortsetzen.</Alert>}
    {!running&&data.status==='failed'&&data.error_code==='cancelled'&&<Alert severity="info">Ablauf gestoppt. Abgeschlossene Pakete sind gespeichert. Du kannst mit „Ab letztem Checkpoint fortsetzen“ weiterarbeiten.</Alert>}
    {running&&!current&&<Typography>Wartet auf den nächsten gespeicherten Agentenschritt.</Typography>}
    {!running&&data.status==='failed'&&data.error_code!=='cancelled'&&<Alert severity="error">Lauf fehlgeschlagen · {data.error_code}. Letzter Schritt: {latest ? names[latest.role]??latest.role : 'Noch kein Agentenprotokoll vorhanden'}.</Alert>}
    <Box component="details"><Box component="summary" sx={{cursor:'pointer'}}>Diagnoseprotokoll · {entries.length} Modellaufrufe</Box>
    {!entries.length&&<Typography variant="body2">Für ältere Läufe sind keine detaillierten Aufrufdaten gespeichert. Neue Läufe protokollieren jeden Aufruf.</Typography>}
    {entries.map((event:any,index:number)=><Box key={index} sx={{py:1,borderBottom:'1px solid',borderColor:'divider'}}>
      <Typography variant="body2"><strong>{names[event.role]??event.role}</strong> · {event.step} · {states[event.status]??event.status}{event.batch?` · Paket ${event.batch.index}/${event.batch.count}`:''}</Typography>
      <Typography variant="caption">Start: {new Date(event.started_at).toLocaleString('de-DE')} · {event.finished_at?`Ende: ${new Date(event.finished_at).toLocaleString('de-DE')}`:'Kein Abschluss gespeichert'} · {seconds(event.started_at,event.finished_at)} s{!event.finished_at&&!running?' (Zeit seit Start; Dauer unbekannt)':''}</Typography>
      <Typography variant="body2" sx={{overflowWrap:'anywhere'}}>Quell-IDs: {event.source_keys?.join(', ')||'keine'}{event.target_keys?.length?` · Prüfziele: ${event.target_keys.join(', ')}`:''}</Typography>
      {event.counts&&<Typography variant="body2">Ergebnis: {Object.entries(event.counts).map(([key,count])=>`${key}: ${count}`).join(' · ')}</Typography>}
      {event.validation_issues?.map((issue:any,i:number)=><Typography key={i} variant="body2" color="error">Schema: {issue.path} · {issue.type}</Typography>)}
      {event.error_type&&<Alert severity="error">{event.error_code??event.error_type}{event.http_status?` · HTTP ${event.http_status}`:""}{event.upstream_status?` · Anbieter HTTP ${event.upstream_status}`:""}: {event.message}</Alert>}
    </Box>)}</Box>
    {query.isError&&<Alert severity="warning">Aktualisierung fehlgeschlagen. Angezeigt wird der letzte geladene Stand.</Alert>}
  </Stack></Box>
}
