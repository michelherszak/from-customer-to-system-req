import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Chip, Stack, TextField, Typography } from '@mui/material'
import { api } from './api'
import { Link } from 'react-router'

const roles:Record<string,string>={requirements_engineer:'Requirements Engineer',systems_engineer:'Systems Engineer',work_planner:'Arbeitsplaner & Aufwandsschätzer',review_engineer:'Review Engineer'}
type Answer={response:string;actor_name:string;answered_at:string;source_run_id:string}
type Finding={finding_id:string;target_key:string;owner:string;question:string;required_change:string;target_text:string;source_text?:string|null;answer?:Answer}
type Responses={version:number;can_respond:boolean;can_recheck:boolean;findings:Finding[]}

export function ReviewBlockers({runId,projectId,busy,onRechecked}:{runId:string;projectId:string;busy:boolean;onRechecked:(data:any)=>Promise<void>}) {
  const client=useQueryClient()
  const query=useQuery({queryKey:['review-responses',runId],queryFn:()=>api<Responses>(`/analysis-runs/${runId}/review-responses`)})
  const [drafts,setDrafts]=useState<Record<string,string>>({})
  const save=useMutation({mutationFn:(finding:Finding)=>api<Responses>(`/analysis-runs/${runId}/review-responses`,{method:'POST',body:JSON.stringify({finding_id:finding.finding_id,response:drafts[finding.finding_id]??finding.answer?.response??'',expected_version:query.data?.version})}),onSuccess:(data,finding)=>{
    client.setQueryData(['review-responses',runId],data)
    setDrafts(old=>{const next={...old};delete next[finding.finding_id];return next})
  }})
  const recheck=useMutation({mutationFn:()=>api<any>(`/analysis-runs/${runId}/recheck`,{method:'POST'}),onSuccess:onRechecked})
  if(query.isError)return <Alert severity="error">Offene Befunde konnten nicht geladen werden: {String(query.error)}</Alert>
  if(!query.data)return <Typography>Offene Befunde werden geladen …</Typography>
  if(!query.data.findings.length)return null
  const answered=query.data.findings.filter(finding=>finding.answer).length
  const unsaved=query.data.findings.some(finding=>drafts[finding.finding_id]!==undefined&&drafts[finding.finding_id].trim()!==(finding.answer?.response??''))
  const pending=busy||save.isPending||recheck.isPending
  return <Box id={`review-responses-${runId}`} sx={{scrollMarginTop:100,p:2,border:'1px solid',borderColor:'warning.main',borderRadius:2}}><Stack spacing={2}>
    <Typography variant="h6">Offene Befunde beantworten</Typography>
    <Typography variant="body2">{answered}/{query.data.findings.length} Antworten gespeichert. Befunde aufklappen, fachlich beantworten und speichern. Anschließend prüft das Modell die überarbeiteten Ergebnisse erneut. Eine Antwort allein schließt keinen Blocker.</Typography>
    {!query.data.can_respond&&<Alert severity="info">Antworten und Nachprüfungen sind für Projektleitung und Firmen-Admins freigegeben. Deine aktuelle Projektrolle darf die Befunde nur lesen.</Alert>}
    {(save.error||recheck.error)&&<Alert severity="error">{String(save.error??recheck.error)} Bei einem Versionskonflikt die Seite neu laden.</Alert>}
    {query.data.can_respond&&<Stack direction="row" sx={{gap:1,alignItems:'center',flexWrap:'wrap'}}>
      <Button variant="contained" disabled={pending||!query.data.can_recheck||unsaved} onClick={()=>recheck.mutate()}>{recheck.isPending?'Nachprüfung wird gestartet …':'Antworten nachprüfen lassen'}</Button>
      {unsaved&&<Typography variant="caption">Geänderte Antworten zuerst speichern oder verwerfen.</Typography>}
    </Stack>}
    {query.data.findings.map((finding,index)=>{
      const value=drafts[finding.finding_id]??finding.answer?.response??''
      const changed=value.trim()!==(finding.answer?.response??'')
      return <Box component="details" key={finding.finding_id} open={index===0} sx={{p:1.5,border:'1px solid',borderColor:finding.answer?'info.light':'error.light',borderRadius:1}}>
        <Box component="summary" sx={{cursor:'pointer'}}><strong>{finding.target_key} · {roles[finding.owner]??finding.owner}</strong> <Chip size="small" sx={{ml:1}} color={finding.answer?'info':'error'} label={finding.answer?'Antwort gespeichert · Befund offen':'Antwort offen'}/><Typography component="span" variant="body2" sx={{display:'block',mt:0.5}}>{finding.question}</Typography></Box>
        <Stack spacing={1.5} sx={{mt:2}}>
          {finding.source_text&&<Box sx={{p:1,bgcolor:'action.hover',borderRadius:1}}><Typography variant="caption">Betroffener freigegebener Prüfschritt-Abschnitt</Typography><Typography variant="body2" sx={{whiteSpace:'pre-wrap'}}>{finding.source_text}</Typography></Box>}
          {finding.target_text&&<Box sx={{p:1,bgcolor:'action.hover',borderRadius:1}}><Typography variant="caption">Betroffene Anforderung / Arbeitspaket</Typography><Typography variant="body2">{finding.target_text}</Typography></Box>}
          {finding.required_change&&<Typography variant="body2"><strong>Geforderte Korrektur:</strong> {finding.required_change}</Typography>}
          <TextField label="Fachliche Antwort / Klarstellung der Projektleitung" multiline minRows={3} value={value} onChange={event=>setDrafts({...drafts,[finding.finding_id]:event.target.value})} disabled={!query.data?.can_respond||pending} slotProps={{htmlInput:{maxLength:6000}}} helperText="Konkret beschreiben, was gelten soll, welche Information fehlt oder wie die Anforderung zu präzisieren ist."/>
          {finding.answer&&<Typography variant="caption">Gespeichert von {finding.answer.actor_name} am {new Date(finding.answer.answered_at).toLocaleString('de-DE')}{finding.answer.source_run_id!==runId?' · Bereits im vorherigen Prüflauf berücksichtigt; Befund weiterhin offen.':''}</Typography>}
          <Stack direction="row" sx={{gap:1,flexWrap:'wrap'}}>
            {query.data?.can_respond&&<><Button variant="outlined" disabled={pending||!value.trim()||!changed} onClick={()=>save.mutate(finding)}>Antwort speichern</Button><Button disabled={pending||!changed} onClick={()=>setDrafts(old=>{const next={...old};delete next[finding.finding_id];return next})}>Verwerfen</Button></>}
            {finding.source_text?<Button component={Link} to={`/projects/${projectId}/review#section-${finding.target_key}`}>Zum Abschnitt im Prüfschritt</Button>:<Button component="a" href={`#engineering-${finding.target_key}`}>Zum betroffenen Ergebnis</Button>}
          </Stack>
        </Stack>
      </Box>
    })}
  </Stack></Box>
}
