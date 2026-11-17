import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Container, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { api } from './api'
import { CloudModelSetup } from './CloudModelSetup'

function SettingsForm({tenantId}:{tenantId:string}) {
  const client=useQueryClient()
  const query=useQuery({queryKey:['agent-settings',tenantId],queryFn:()=>api<any>(`/tenants/${tenantId}/agent-settings`)})
  const [draft,setDraft]=useState<any>(null)
  const [saved,setSaved]=useState(false)
  useEffect(()=>{if(query.data)setDraft(query.data.settings)},[query.data])
  const change=(patch:any)=>{setSaved(false);setDraft((old:any)=>({...old,...patch}))}
  const save=useMutation({mutationFn:()=>api<any>(`/tenants/${tenantId}/agent-settings`,{method:'PUT',body:JSON.stringify({...draft,expected_version:query.data.lock_version})}),onSuccess:async data=>{
    client.setQueryData(['agent-settings',tenantId],data);setSaved(true)
    await client.invalidateQueries({queryKey:['analysis-options']})
  }})
  if(query.isError)return <Alert severity="error">{String(query.error)}</Alert>
  if(!draft)return <Typography>Einstellungen werden geladen …</Typography>
  return <Stack spacing={2}>
    <Card><CardContent><Stack spacing={2}>
      <Typography variant="h6">Cloud-Modell & API-Schlüssel</Typography>
      <Typography variant="body2">Ein gemeinsames Cloud-Modell für die CrewAI-Agenten. API-Schlüssel werden verschlüsselt gespeichert.</Typography>
      <CloudModelSetup tenantId={tenantId} selectedProviderId={draft.default_provider_config_id} selectedModel={draft.default_model_id} onConfigured={(id,model)=>change({default_provider_config_id:id,default_model_id:model})}/>
      <TextField select label="Maximale Engineering-Runden" value={draft.max_rounds??2} onChange={e=>change({max_rounds:Number(e.target.value)})} disabled={save.isPending}>{[1,2,3].map(n=><MenuItem key={n} value={n}>{n} {n===1?'Runde':'Runden'}</MenuItem>)}</TextField>
    </Stack></CardContent></Card>
    {query.data.agents.map((agent:any)=><Card key={agent.id}><CardContent><Stack spacing={1.5}>
      <Typography variant="h6">{agent.label}</Typography>
      <Box component="details"><Box component="summary" sx={{cursor:'pointer'}}>Verbindliche Standardanweisung anzeigen</Box><Typography variant="body2" sx={{whiteSpace:'pre-wrap',mt:1}}>{agent.default_prompt}</Typography></Box>
      <TextField label="Zusätzliche Firmenanweisungen" multiline minRows={3} value={draft.instructions?.[agent.id]??''} onChange={e=>change({instructions:{...draft.instructions,[agent.id]:e.target.value}})} slotProps={{htmlInput:{maxLength:6000}}} helperText="Ergänzt die Standardanweisung. Quellenregeln, Verknüpfungsprüfungen und Ausgabeschema bleiben verbindlich." disabled={save.isPending}/>
      <Button sx={{alignSelf:'flex-start'}} onClick={()=>change({instructions:{...draft.instructions,[agent.id]:''}})} disabled={save.isPending||!draft.instructions?.[agent.id]}>Zusatzanweisung zurücksetzen</Button>
    </Stack></CardContent></Card>)}
    <Alert severity="info">Agenteneinstellungen speichern gilt für neue Läufe und Fortsetzungen. Laufende Analysen behalten ihren Einstellungsstand. Geänderte Anweisungen werden bei der Checkpoint-Prüfung berücksichtigt.</Alert>
    {saved&&<Alert severity="success">Agenteneinstellungen gespeichert.</Alert>}
    {save.error&&<Alert severity="error">{String(save.error)} Bei einem Versionskonflikt die Seite neu laden.</Alert>}
    <Button variant="contained" sx={{alignSelf:'flex-start'}} disabled={save.isPending} onClick={()=>save.mutate()}>{save.isPending?'Wird gespeichert …':'Agenteneinstellungen speichern'}</Button>
  </Stack>
}

export function AgentSettings() {
  const tenants=useQuery({queryKey:['tenants'],queryFn:()=>api<any[]>('/tenants')})
  const companies=(tenants.data??[]).filter(x=>x.role==='company_admin')
  const [selected,setSelected]=useState('')
  const tenantId=companies.find(x=>x.id===selected)?.id??companies[0]?.id
  return <Container maxWidth="md" disableGutters><Stack spacing={2}>
    <Typography variant="h4">Einstellungen · Agenten</Typography>
    <Typography color="text.secondary">Firmenweite Modellverbindung und Arbeitsanweisungen für die fünf CrewAI-Agenten.</Typography>
    {tenants.error&&<Alert severity="error">{String(tenants.error)}</Alert>}
    {companies.length>1&&<TextField select label="Firma" value={tenantId??''} onChange={e=>setSelected(e.target.value)}>{companies.map(x=><MenuItem key={x.id} value={x.id}>{x.name}</MenuItem>)}</TextField>}
    {tenantId?<SettingsForm key={tenantId} tenantId={tenantId}/>:<Alert severity="info">Diese Einstellungen können Firmen-Admins bearbeiten.</Alert>}
  </Stack></Container>
}
