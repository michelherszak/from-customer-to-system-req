import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, LinearProgress, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material'
import { api, artifactUrl, me } from './api'
import { PlanningReadiness } from './PlanningWorkspace'

const euro=(value:unknown)=>value===null||value===undefined?'—':new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(Number(value))
const dateLabel=(value:string|undefined)=>value?new Intl.DateTimeFormat('de-DE',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(`${value.slice(0,10)}T12:00:00`)): '—'
const offerStatusSx=(status:string)=>status==='freigegeben'?{bgcolor:'#DCF5E5',color:'#12663A'}:status==='zur Freigabe'?{bgcolor:'#FFF0B3',color:'#775900'}:status==='versendet'?{bgcolor:'#E3EAFE',color:'#274690'}:{bgcolor:'#EEF0F6',color:'#4A5265'}

export function OffersWorkspace({projectId}:{projectId:string}) {
  const client=useQueryClient()
  const location=useLocation()
  const navigate=useNavigate()
  const auth=useQuery({queryKey:['me'],queryFn:me})
  const project=useQuery({queryKey:['project',projectId],queryFn:()=>api<any>(`/projects/${projectId}`)})
  const packages=useQuery({queryKey:['workpackages',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/work-packages`)})
  const offers=useQuery({queryKey:['offers',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/offers`)})
  const canManage=(auth.data?.project_roles??[]).some((role:any)=>role.project_id===projectId&&role.role==='project_lead')||(auth.data?.tenant_roles??[]).some((role:any)=>role.tenant_id===project.data?.tenant_id&&role.role==='company_admin')
  const gmail=useQuery({queryKey:['gmail-status',projectId],queryFn:()=>api<any>(`/projects/${projectId}/gmail/status`),enabled:!!project.data&&canManage})
  const customers=useQuery({queryKey:['customers',project.data?.tenant_id],queryFn:()=>api<any[]>(`/customers?tenant_id=${project.data.tenant_id}`),enabled:!!project.data?.tenant_id&&canManage})
  const selectedId=new URLSearchParams(location.search).get('offer')??''
  const [working,setWorking]=useState('')
  const [error,setError]=useState<unknown>(null)
  const [mailOpen,setMailOpen]=useState(false)
  const [mailFields,setMailFields]=useState({to:'',subject:'',body:''})
  const [draftUrl,setDraftUrl]=useState('')
  const versions=offers.data?.flatMap(offer=>offer.versions.map((version:any)=>({...version,offer_id:offer.id,offer_number:offer.offer_number,variant_name:offer.variant_name})))??[]
  const selected=versions.find(version=>version.id===selectedId)??versions[0]
  const selectVersion=(id:string)=>navigate(`${location.pathname}?offer=${encodeURIComponent(id)}`,{replace:true})
  const customer=customers.data?.find((item:any)=>item.id===project.data?.customer_id)
  const preview=useQuery({queryKey:['offer-preview',selected?.id],queryFn:()=>api<any>(`/offer-versions/${selected.id}/preview`),enabled:!!selected})
  const responses=useQuery({queryKey:['offer-responses',selected?.id],queryFn:()=>api<any[]>(`/offer-versions/${selected.id}/responses`),enabled:!!selected,refetchInterval:30_000})
  const canApprove=canManage||(auth.data?.project_roles??[]).some((role:any)=>role.project_id===projectId&&role.role==='project_member')
  const run=async(label:string,action:()=>Promise<void>)=>{setWorking(label);setError(null);try{await action()}catch(caught){setError(caught)}finally{setWorking('')}}
  const create=()=>run('Angebotsentwurf wird aus der aktiven Planung erstellt …',async()=>{
    const created=await api<any>(`/projects/${projectId}/offers`,{method:'POST',body:JSON.stringify({variant_name:'Basis',primary_variant:true,language:project.data?.document_language??'de'})})
    selectVersion(created.version.id)
    await client.invalidateQueries({queryKey:['offers',projectId]})
  })
  const changeStatus=(target:string)=>run('Angebotsstatus wird aktualisiert …',async()=>{
    await api(`/offer-versions/${selected.id}/status`,{method:'POST',body:JSON.stringify({target_status:target,comment:target==='Entwurf'?'Zur Überarbeitung':''})})
    await Promise.all([client.invalidateQueries({queryKey:['offers',projectId]}),client.invalidateQueries({queryKey:['offer-preview',selected.id]})])
  })
  const exportFile=(format:string)=>run(`${format.toUpperCase()} wird erstellt …`,async()=>{
    const result=await api<any>(`/offer-versions/${selected.id}/export?format=${format}`,{method:'POST'})
    const anchor=document.createElement('a');anchor.href=artifactUrl(result.artifact_id);anchor.target='_blank';anchor.rel='noopener noreferrer';anchor.click()
  })
  const connectGmail=()=>{window.location.href=`/api/v1/projects/${projectId}/gmail/connect`}
  const openMailDraft=()=>{
    setDraftUrl('')
    setMailFields({to:customer?.email??'',subject:`${selected.offer_number} · ${selected.variant_name} · V${selected.version}`,body:`Guten Tag${project.data?.customer_contact?` ${project.data.customer_contact}`:''},\n\nanbei erhalten Sie unser freigegebenes Angebot ${selected.offer_number} als DOCX. Sie können direkt auf diese E-Mail antworten oder Ihre Rückmeldung im KuSys-Kundenbereich unter „Angebote & Rückmeldung“ eintragen.\n\nFreundliche Grüße\n${auth.data?.user?.display_name??''}`})
    setMailOpen(true)
  }
  const createMailDraft=()=>run('Gmail-Entwurf wird erstellt …',async()=>{
    const result=await api<any>(`/offer-versions/${selected.id}/gmail-drafts`,{method:'POST',body:JSON.stringify(mailFields)})
    setDraftUrl(result.gmail_url)
  })
  const newVersion=()=>run('Neue Angebotsversion wird erstellt …',async()=>{
    const result=await api<any>(`/offers/${selected.offer_id}/versions`,{method:'POST'})
    selectVersion(result.id);await client.invalidateQueries({queryKey:['offers',projectId]})
  })
  const pricing=preview.data?.pricing
  return <Stack spacing={2.5}>
    <Stack direction={{xs:'column',md:'row'}} sx={{justifyContent:'space-between',alignItems:{md:'flex-end'},gap:1.5}}>
      <Box><Typography variant="overline" color="text.secondary">Projektangebot</Typography><Typography variant="h5" sx={{mt:0.25}}>Angebote & Freigaben</Typography><Typography variant="body2" color="text.secondary" sx={{mt:0.5}}>Freigegebene Versionen, Kundenrückmeldungen und Versand an einem Ort.</Typography></Box>
      <Button variant="contained" disabled={!canManage||!packages.data?.length||!!working} onClick={()=>void create()}>Angebot aus Planung erstellen</Button>
    </Stack>
    {packages.isSuccess&&!packages.data?.length&&<PlanningReadiness projectId={projectId}/>}
    {working&&<Box><Typography>{working}</Typography><LinearProgress sx={{mt:1}}/></Box>}
    {[error,offers.error,packages.error,preview.error].filter(Boolean).map((item,i)=><Alert key={i} severity="error">{String(item)}</Alert>)}
    {offers.isPending&&<Typography>Angebote werden geladen …</Typography>}
    {offers.isSuccess&&!versions.length&&<Alert severity="info">Noch kein Angebot vorhanden. Nach Übernahme und Prüfung der Arbeitspakete kann hier ein Angebotsentwurf mit Kosten, Preisen und Terminen erstellt werden. <Button component={Link} to={`/projects/${projectId}/planning`}>Zur Planung</Button></Alert>}
    {selected&&<Card sx={{overflow:'hidden',borderRadius:3}}><CardContent sx={{p:0}}><Stack spacing={0}>
      <Box sx={{px:{xs:2.5,md:3.5},py:{xs:2.25,md:3},background:'linear-gradient(112deg, #15172E 0%, #252B61 100%)',color:'#FFF'}}><Stack direction={{xs:'column',md:'row'}} sx={{justifyContent:'space-between',gap:2}}><Box><Typography variant="overline" sx={{color:'#C9CCE3'}}>Freigegebener Angebotsstand</Typography><Stack direction="row" spacing={1} sx={{alignItems:'center',mt:.5,flexWrap:'wrap'}}><Typography variant="h5" sx={{color:'#FFF'}}>{selected.offer_number} · {selected.variant_name} · V{selected.version}</Typography><Chip size="small" label={selected.status} sx={{...offerStatusSx(selected.status),fontWeight:700}}/></Stack><Typography variant="body2" sx={{color:'#D8DCEC',mt:.75}}>Planungszeitraum {dateLabel(preview.data?.schedule?.project_start)} bis {dateLabel(preview.data?.schedule?.project_finish)}</Typography></Box>
        <Stack direction="row" sx={{gap:1,flexWrap:'wrap','& .MuiButton-root':{color:'#FFF',borderColor:'rgba(255,255,255,.42)',bgcolor:'rgba(255,255,255,.08)'},'& .MuiButton-root:hover':{bgcolor:'rgba(255,255,255,.16)'},'& .MuiButton-contained':{bgcolor:'#FFE433',color:'#15172E'},'& .MuiButton-contained:hover':{bgcolor:'#FFF06A'}}}>
          {canManage&&selected.status==='Entwurf'&&<Button disabled={!!working||preview.isError||preview.isPending} onClick={()=>void changeStatus('zur Freigabe')}>Zur Freigabe</Button>}
          {canApprove&&selected.status==='zur Freigabe'&&<Button disabled={!!working||preview.isError} variant="contained" onClick={()=>void changeStatus('freigegeben')}>Freigeben</Button>}
          {canManage&&selected.status==='zur Freigabe'&&<Button disabled={!!working} onClick={()=>void changeStatus('Entwurf')}>Überarbeiten</Button>}
          {canManage&&selected.status==='freigegeben'&&<Button disabled={!!working} onClick={()=>void changeStatus('versendet')}>Als versendet markieren</Button>}
          {canManage&&selected.status==='versendet'&&<><Button disabled={!!working} onClick={()=>void changeStatus('angenommen')}>Angenommen</Button><Button disabled={!!working} color="error" onClick={()=>void changeStatus('abgelehnt')}>Abgelehnt</Button></>}
          {canManage&&<Button disabled={!!working} onClick={()=>void newVersion()}>Neue Version</Button>}
          {canManage&&<><Button disabled={!!working||preview.isError||preview.isPending} onClick={()=>void exportFile('docx')}>DOCX</Button><Button disabled={!!working||preview.isError||preview.isPending} onClick={()=>void exportFile('xlsx')}>Excel</Button></>}
          {canManage&&selected.status==='freigegeben'&&!gmail.data?.connected&&gmail.data?.configured&&<Button disabled={gmail.isPending} onClick={connectGmail}>Gmail verbinden</Button>}
          {canManage&&selected.status==='freigegeben'&&gmail.data?.connected&&<Button disabled={!!working} onClick={openMailDraft}>E-Mail-Entwurf</Button>}
        </Stack>
      </Stack></Box>
      <Box sx={{p:{xs:2.5,md:3.5}}}>
        {selected.status==='freigegeben'&&gmail.isSuccess&&!gmail.data?.configured&&<Alert severity="info" sx={{mb:2}}>Gmail ist vorbereitet. Für E-Mail-Entwürfe fehlen noch die OAuth-Zugangsdaten aus Google Cloud.</Alert>}
        {draftUrl&&<Alert severity="success" sx={{mb:2}} action={<Button component="a" href={draftUrl} target="_blank" rel="noreferrer" color="inherit">Entwurf prüfen</Button>}>Der E-Mail-Entwurf mit Angebotsanhang liegt in Gmail. Er wurde nicht versendet.</Alert>}
        {preview.isPending?<LinearProgress/>:pricing&&<Stack spacing={3}>
          <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr 1fr',md:'repeat(4, 1fr)'},gap:1.25}}>{[
            ['Netto',euro(pricing.net_eur),'#15172E'],['Brutto',euro(pricing.gross_eur),'#2E3FE6'],['Deckungsbeitrag',euro(pricing.margin_eur),'#12663A'],['Sachpositionen',euro(pricing.material_sales_eur),'#6A4C00']
          ].map(([label,value,color])=><Box key={label} sx={{p:1.75,border:'1px solid',borderColor:'divider',borderTop:`3px solid ${color}`,borderRadius:2,bgcolor:'#FBFCFE'}}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography sx={{fontWeight:750,fontSize:{xs:'1rem',md:'1.15rem'},mt:.25,fontVariantNumeric:'tabular-nums'}}>{value}</Typography></Box>)}</Box>
          <Box><Stack direction="row" sx={{justifyContent:'space-between',alignItems:'baseline',mb:1}}><Typography variant="h6">Enthaltene Arbeitspakete</Typography><Typography variant="caption" color="text.secondary">{preview.data.work_packages?.length??0} Positionen</Typography></Stack><Box sx={{overflowX:'auto',border:'1px solid',borderColor:'divider',borderRadius:2}}><Table size="small"><TableHead><TableRow><TableCell>Arbeitspaket</TableCell><TableCell>Fachrolle</TableCell><TableCell>Planstunden</TableCell><TableCell>Termin</TableCell></TableRow></TableHead><TableBody>{preview.data.work_packages?.map((wp:any)=>{const dates=preview.data.schedule.packages.find((item:any)=>item.id===wp.id);return <TableRow key={wp.id} hover><TableCell sx={{fontWeight:600}}>{wp.key} <Box component="span" sx={{fontWeight:400}}>· {wp.name}</Box></TableCell><TableCell>{wp.role}</TableCell><TableCell>{wp.plan_hours} h</TableCell><TableCell>{dates?`${dateLabel(dates.start)} – ${dateLabel(dates.finish)}`:'—'}</TableCell></TableRow>})}</TableBody></Table></Box></Box>
          <Box><Typography variant="h6" sx={{mb:1}}>Budget- und Preiswirkung</Typography><Box sx={{overflowX:'auto',border:'1px solid',borderColor:'divider',borderRadius:2}}><Table size="small"><TableHead><TableRow><TableCell>Anforderung</TableCell><TableCell align="right">Budget</TableCell><TableCell align="right">Preisanteil</TableCell><TableCell align="right">Spielraum</TableCell></TableRow></TableHead><TableBody>{pricing.attribution.map((item:any)=><TableRow key={item.requirement_id} hover><TableCell><strong>{item.key}</strong> · {item.title}</TableCell><TableCell align="right">{euro(item.budget_eur)}</TableCell><TableCell align="right">{euro(item.sales_eur)}</TableCell><TableCell align="right">{euro(item.budget_delta_eur)}</TableCell></TableRow>)}</TableBody></Table></Box></Box>
        </Stack>}
        <Divider sx={{my:3}}/>
        <Stack direction="row" sx={{justifyContent:'space-between',alignItems:'baseline',mb:1}}><Box><Typography variant="h6">Kundenrückmeldungen</Typography><Typography variant="body2" color="text.secondary">Antworten aus dem Kundenbereich und dem verbundenen Gmail-Thread.</Typography></Box><Chip size="small" label={`${responses.data?.length??0} Nachrichten`} sx={{bgcolor:'#EEF0F6'}}/></Stack>
        {responses.isPending?<LinearProgress/>:responses.data?.length?<Stack spacing={1}>{responses.data.map((response:any)=><Alert key={response.id} severity="info" sx={{alignItems:'flex-start'}}><strong>{response.author_name}</strong>{response.author_email?` · ${response.author_email}`:''} · {new Date(response.created_at).toLocaleString('de-DE')}<br/><span style={{whiteSpace:'pre-wrap'}}>{response.body}</span></Alert>)}</Stack>:<Box sx={{p:2,border:'1px dashed',borderColor:'divider',borderRadius:2,bgcolor:'#FBFCFE'}}><Typography variant="body2" color="text.secondary">Noch keine Rückmeldung zu diesem Angebot. Der Kunde kann im Kundenbereich antworten; E-Mail-Antworten erscheinen nach der Gmail-Verknüpfung hier.</Typography></Box>}
      </Box>
    </Stack></CardContent></Card>}
    <Dialog open={mailOpen} onClose={()=>{if(!working)setMailOpen(false)}} fullWidth maxWidth="sm">
      <DialogTitle>Gmail-Entwurf mit Angebot</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{pt:1}}>
        <Typography variant="body2" color="text.secondary">Der freigegebene Angebotsstand wird als DOCX angehängt. Der Entwurf wird in Gmail gespeichert und nicht gesendet.</Typography>
        <TextField label="An" type="email" value={mailFields.to} onChange={event=>setMailFields({...mailFields,to:event.target.value})} required fullWidth/>
        <TextField label="Betreff" value={mailFields.subject} onChange={event=>setMailFields({...mailFields,subject:event.target.value})} required fullWidth/>
        <TextField label="Nachricht" value={mailFields.body} onChange={event=>setMailFields({...mailFields,body:event.target.value})} required fullWidth multiline minRows={8}/>
        {Boolean(error)&&<Alert severity="error">{String(error)}</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button onClick={()=>setMailOpen(false)} disabled={!!working}>Schließen</Button><Button variant="contained" onClick={()=>void createMailDraft()} disabled={!!working||!mailFields.to.trim()||!mailFields.subject.trim()||!mailFields.body.trim()}>{working?'Wird erstellt …':'Entwurf in Gmail speichern'}</Button></DialogActions>
    </Dialog>
  </Stack>
}
