import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Chip, Collapse, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { api, me } from './api'

const roleLabels:Record<string,string>={project_lead:'Projektleitung',project_member:'Projektmitglied',customer:'Kunde'}
type Member={id:string;user_id:string;display_name:string;username:string;role:string;active:boolean}
type Candidate={id:string;display_name:string;username:string;tenant_role:string;default_role:string}

export function ProjectMembers({projectId,tenantId}:{projectId:string;tenantId:string}) {
  const client=useQueryClient()
  const navigate=useNavigate()
  const auth=useQuery({queryKey:['me'],queryFn:me})
  const [open,setOpen]=useState(false)
  const [search,setSearch]=useState('')
  const [roles,setRoles]=useState<Record<string,string>>({})
  const canManage=(auth.data?.project_roles??[]).some((role:any)=>role.project_id===projectId&&role.role==='project_lead')||(auth.data?.tenant_roles??[]).some((role:any)=>role.tenant_id===tenantId&&role.role==='company_admin')
  const members=useQuery({queryKey:['project-members',projectId],queryFn:()=>api<Member[]>(`/projects/${projectId}/members`),enabled:open&&canManage})
  const candidates=useQuery({queryKey:['project-member-candidates',projectId],queryFn:()=>api<Candidate[]>(`/projects/${projectId}/member-candidates`),enabled:open&&canManage})
  const refresh=async()=>{await Promise.all([
    client.invalidateQueries({queryKey:['project-members',projectId]}),
    client.invalidateQueries({queryKey:['project-member-candidates',projectId]}),
    client.invalidateQueries({queryKey:['projects']}),
    client.invalidateQueries({queryKey:['me']}),
  ])}
  const add=useMutation({mutationFn:(person:Candidate)=>api(`/projects/${projectId}/members`,{method:'POST',body:JSON.stringify({user_id:person.id,role:roles[person.id]??person.default_role})}),onSuccess:refresh})
  const remove=useMutation({mutationFn:(person:Member)=>api(`/projects/${projectId}/members/${person.user_id}`,{method:'DELETE'}),onSuccess:async(_data,person)=>{
    if(person.user_id===auth.data?.user.id){navigate('/');await refresh()}else await refresh()
  }})
  if(!canManage)return null
  const busy=add.isPending||remove.isPending
  const filtered=candidates.data?.filter(person=>`${person.display_name} ${person.username}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()))??[]
  const leadCount=members.data?.filter(person=>person.role==='project_lead'&&person.active).length??0
  return <Box sx={{mb:2}}>
    <Box sx={{display:'flex',justifyContent:'flex-end'}}><Button variant={open?'contained':'outlined'} onClick={()=>setOpen(!open)} aria-expanded={open} aria-controls={`project-team-${projectId}`}>Projektteam {open?'schließen':'verwalten'}</Button></Box>
    <Collapse in={open} unmountOnExit><Card id={`project-team-${projectId}`} sx={{mt:1}}><CardContent><Stack spacing={2}>
      <Typography variant="h6">Projektteam</Typography>
      <Typography variant="body2" color="text.secondary">Firmen-Admins sehen das Projekt automatisch. Personen der eigenen Firma können hier mit einem Klick hinzugefügt werden.</Typography>
      {[members.error,candidates.error,add.error,remove.error].filter(Boolean).map((error,index)=><Alert key={index} severity="error">{String(error)}</Alert>)}
      {(members.isPending||candidates.isPending)&&<Typography>Personen werden geladen …</Typography>}
      {!!members.data?.length&&<Stack spacing={1}>{members.data.map(person=><Stack key={person.user_id} direction={{xs:'column',sm:'row'}} sx={{gap:1,alignItems:{sm:'center'},py:1,borderBottom:'1px solid',borderColor:'divider'}}>
        <Box sx={{flex:1}}><Typography variant="body2" sx={{fontWeight:600}}>{person.display_name}{person.user_id===auth.data?.user.id?' (du)':''}</Typography><Typography variant="caption" color="text.secondary">{person.username}</Typography></Box>
        <Chip size="small" label={`${roleLabels[person.role]??person.role}${person.active?'':' · inaktiv'}`}/>
        <Button color="error" disabled={busy||(person.role==='project_lead'&&person.active&&leadCount<=1)} onClick={()=>{if(window.confirm(`${person.display_name} aus dem Projekt entfernen?`))remove.mutate(person)}}>Entfernen</Button>
      </Stack>)}</Stack>}
      <Typography variant="subtitle1">Person hinzufügen</Typography>
      <TextField label="Person suchen" size="small" value={search} onChange={event=>setSearch(event.target.value)}/>
      {filtered.map(person=><Stack key={person.id} direction={{xs:'column',sm:'row'}} sx={{gap:1,alignItems:{sm:'center'}}}>
        <Box sx={{flex:1}}><Typography variant="body2" sx={{fontWeight:600}}>{person.display_name}</Typography><Typography variant="caption" color="text.secondary">{person.username}</Typography></Box>
        <TextField select size="small" label="Projektrolle" value={roles[person.id]??person.default_role} sx={{minWidth:180}} disabled={busy||person.tenant_role==='customer'} onChange={event=>setRoles({...roles,[person.id]:event.target.value})}>
          {person.tenant_role==='customer'?<MenuItem value="customer">Kunde</MenuItem>:[<MenuItem key="project_member" value="project_member">Projektmitglied</MenuItem>,<MenuItem key="project_lead" value="project_lead">Projektleitung</MenuItem>]}
        </TextField>
        <Button variant="contained" disabled={busy} onClick={()=>add.mutate(person)}>Hinzufügen</Button>
      </Stack>)}
      {candidates.isSuccess&&!filtered.length&&<Typography variant="body2" color="text.secondary">{search?'Keine passende Person gefunden.':'Alle verfügbaren Personen sind bereits zugeordnet.'}</Typography>}
      <Typography variant="caption" color="text.secondary">Kunden sehen freigegebene Dokumente und Klärungspunkte im Kundenportal. Die letzte aktive Projektleitung bleibt erhalten.</Typography>
    </Stack></CardContent></Card></Collapse>
  </Box>
}
