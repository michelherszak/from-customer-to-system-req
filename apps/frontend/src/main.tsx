import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DndContext, DragEndEvent, useDraggable, useDroppable } from '@dnd-kit/core'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CircularProgress, Container, CssBaseline, Dialog, DialogActions, LinearProgress,
  DialogContent, DialogTitle, Divider, Drawer, FormControl, InputLabel, MenuItem, Select, Stack, Tab, Tabs,
  TextField, ThemeProvider, Toolbar, Typography, Table, TableBody, TableCell, TableHead, TableRow, Checkbox, Paper, createTheme
} from '@mui/material'
import { api, artifactUrl, login, me, uploadDocument } from './api'
import { JobProgressProvider, useJobProgress } from './jobProgress'

const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: 'light',
    primary: { main: '#0F766E', light: '#14B8A6', dark: '#115E59', contrastText: '#fff' },
    secondary: { main: '#1E293B' },
    background: { default: '#F1F5F9', paper: '#FFFFFF' },
    text: { primary: '#0F172A', secondary: '#64748B' },
    divider: 'rgba(15, 23, 42, 0.08)',
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", sans-serif',
    h4: { fontFamily: 'Outfit, "IBM Plex Sans", sans-serif', fontWeight: 650, letterSpacing: '-0.02em' },
    h5: { fontFamily: 'Outfit, "IBM Plex Sans", sans-serif', fontWeight: 650, letterSpacing: '-0.02em' },
    h6: { fontFamily: 'Outfit, "IBM Plex Sans", sans-serif', fontWeight: 600, letterSpacing: '-0.01em' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiButton: { styleOverrides: { root: { borderRadius: 10 }, contained: { boxShadow: 'none', '&:hover': { boxShadow: '0 4px 14px rgba(15,118,110,0.25)' } } } },
    MuiCard: { styleOverrides: { root: { border: '1px solid rgba(15,23,42,0.06)', boxShadow: '0 1px 2px rgba(15,23,42,0.04)' } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiAppBar: { styleOverrides: { root: { boxShadow: 'none' } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 44 } } },
  },
})


const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 3000 } } })
window.addEventListener('kusys-job-finished', event => {
  const { projectId, kind } = (event as CustomEvent<{ projectId: string; kind: string }>).detail
  if (kind === 'document_extract') {
    void qc.invalidateQueries({ queryKey: ['docs', projectId] })
    void qc.invalidateQueries({ queryKey: ['review', projectId] })
  } else if (kind === 'analysis') {
    for (const key of ['requirements', 'workpackages', 'schedule', 'offers']) void qc.invalidateQueries({ queryKey: [key, projectId] })
  }
})
const drawerWidth = 250
const eur = (v: any) => v == null ? '–' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Number(v))

function ErrorBox({ error }: { error: unknown }) { return error ? <Alert severity="error" sx={{ my: 2 }}>{String((error as any)?.message ?? error)}</Alert> : null }
function Loading() { return <Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /><Typography sx={{ mt: 1 }}>Daten werden geladen…</Typography></Box> }

function LoginPage() {
  const nav = useNavigate(); const [username, setUsername] = useState('max.mustermann'); const [password, setPassword] = useState('KuSys-Demo-2026'); const [error, setError] = useState('')
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setError(''); try { await login(username, password); const next = await me(); qc.setQueryData(['me'], next); nav('/') } catch (e: any) { setError(e.message) } }
  return <Box sx={{
    minHeight: '100vh', display: 'grid', placeItems: 'center', px: 2,
    background: 'radial-gradient(1200px 600px at 10% -10%, #99F6E4 0%, transparent 55%), radial-gradient(900px 500px at 100% 0%, #BFDBFE 0%, transparent 50%), linear-gradient(180deg, #F8FAFC 0%, #E2E8F0 100%)',
  }}>
    <Card sx={{ width: '100%', maxWidth: 440, borderRadius: 3, boxShadow: '0 20px 50px rgba(15,23,42,0.08)' }}>
      <CardContent sx={{ p: 4 }}>
        <Typography variant="h4" sx={{ mb: 0.5 }}>KuSys</Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>Engineering, Terminplanung und Angebotskalkulation</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box component="form" onSubmit={submit}>
          <Stack spacing={2}>
            <TextField label="Benutzername" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
            <TextField type="password" label="Passwort" value={password} onChange={e => setPassword(e.target.value)} />
            <Button type="submit" size="large" variant="contained">Anmelden</Button>
          </Stack>
        </Box>
        <Divider sx={{ my: 3 }} />
        <Typography variant="body2" color="text.secondary">Demo: max.mustermann / KuSys-Demo-2026 · Freigabe: lea.pruefer</Typography>
      </CardContent>
    </Card>
  </Box>
}

const DEMO_PASSWORD = 'KuSys-Demo-2026'
const DEMO_ACCOUNTS = [
  { username: 'max.mustermann', label: 'Projektleitung · Max' },
  { username: 'lea.pruefer', label: 'Freigabe · Lea' },
  { username: 'tom.mitglied', label: 'Mitglied · Tom' },
  { username: 'sophie.schneider', label: 'Firmen-Admin · Sophie' },
  { username: 'kunde.nordstern', label: 'Kunde · Anna' },
  { username: 'platform.admin', label: 'Platform-Admin' },
] as const

function roleLabel(role: string): string {
  return ({
    company_admin: 'Firmen-Admin',
    project_lead: 'Projektleitung',
    project_member: 'Projektmitglied',
    customer: 'Kunde',
    platform_admin: 'Platform-Admin',
  } as Record<string, string>)[role] || role
}

function summarizeRoles(auth: any): string {
  if (auth?.user?.is_platform_admin) return 'Platform-Admin'
  const labels = [
    ...(auth?.tenant_roles ?? []).map((r: any) => roleLabel(r.role)),
    ...(auth?.project_roles ?? []).map((r: any) => roleLabel(r.role)),
  ]
  return [...new Set(labels)].join(' · ') || 'Benutzer'
}

function isProjectLead(auth: any, projectId: string): boolean {
  return (auth?.project_roles ?? []).some((r: any) => r.project_id === projectId && r.role === 'project_lead')
}

function DemoRoleSwitcher({ auth }: { auth: any }) {
  const nav = useNavigate()
  const { clearJobs } = useJobProgress()
  const [busy, setBusy] = useState(false)
  const current = auth?.user?.username ?? ''
  const [selected, setSelected] = useState(current)
  useEffect(() => {
    if (!busy) setSelected(current)
  }, [busy, current])
  const switchTo = async (username: string) => {
    if (!username || username === current || busy) return
    setSelected(username)
    setBusy(true)
    try {
      try { await api('/auth/logout', { method: 'POST' }) } catch { /* session may already be gone */ }
      clearJobs()
      sessionStorage.clear()
      await login(username, DEMO_PASSWORD)
      const next = await me()
      if (next.user.username !== username) throw new Error('Der gewählte Benutzer wurde nicht angemeldet')
      await qc.cancelQueries()
      qc.removeQueries({ predicate: query => query.queryKey[0] !== 'me' })
      // Keep the active auth query: updating it notifies App immediately.
      qc.setQueryData(['me'], next)
      nav('/')
    } catch (error) {
      try { qc.setQueryData(['me'], await me()) } catch { qc.setQueryData(['me'], null) }
      setSelected(current)
      window.alert(`Rollenwechsel fehlgeschlagen: ${String((error as Error)?.message ?? error)}`)
    } finally {
      setBusy(false)
    }
  }
  const value = DEMO_ACCOUNTS.some(a => a.username === selected)
    ? selected
    : (DEMO_ACCOUNTS.some(a => a.username === current) ? current : '')
  return (
    <FormControl size="small" sx={{ minWidth: 220 }} disabled={busy}>
      <InputLabel id="demo-role-label">Rolle wechseln</InputLabel>
      <Select
        labelId="demo-role-label"
        label="Rolle wechseln"
        value={value}
        onChange={e => void switchTo(String(e.target.value))}
      >
        {DEMO_ACCOUNTS.map(a => (
          <MenuItem key={a.username} value={a.username}>{a.label}</MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

function Shell({ auth }: { auth: any }) {
  const loc = useLocation(); const nav = useNavigate(); const { clearJobs } = useJobProgress(); const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<any[]>('/projects') })
  const logout = async () => { await api('/auth/logout', { method: 'POST' }); sessionStorage.clear(); clearJobs(); await qc.cancelQueries(); qc.removeQueries({ predicate: query => query.queryKey[0] !== 'me' }); qc.setQueryData(['me'], null); nav('/login') }
  const roles = summarizeRoles(auth)
  const navBtn = (to: string, label: React.ReactNode, active?: boolean) => (
    <Button component={Link} to={to} fullWidth sx={{
      justifyContent: 'flex-start', textAlign: 'left', px: 1.5, py: 1, mb: 0.5, borderRadius: 2,
      bgcolor: active ? 'rgba(15,118,110,0.1)' : 'transparent', color: active ? 'primary.dark' : 'text.primary',
      '&:hover': { bgcolor: active ? 'rgba(15,118,110,0.14)' : 'rgba(15,23,42,0.04)' },
    }}>{label}</Button>
  )
  return <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
    <AppBar position="fixed" color="transparent" sx={{
      zIndex: t => t.zIndex.drawer + 1, bgcolor: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid', borderColor: 'divider', color: 'text.primary',
    }}>
      <Toolbar sx={{ gap: 1.5 }}>
        <Typography variant="h6" sx={{ flexGrow: 1, color: 'primary.dark' }}>KuSys</Typography>
        <Stack direction="row" spacing={1} sx={{ mr: 0.5, alignItems: 'center' }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{auth.user.display_name}</Typography>
          <Chip label={roles} size="small" color="primary" variant="outlined" sx={{ borderWidth: 1.5, bgcolor: 'rgba(15,118,110,0.06)' }} />
          <DemoRoleSwitcher auth={auth} />
        </Stack>
        <Button onClick={logout} variant="outlined" size="small" color="secondary">Abmelden</Button>
      </Toolbar>
    </AppBar>
    <Drawer variant="permanent" sx={{
      width: drawerWidth, flexShrink: 0,
      [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box', borderRight: '1px solid', borderColor: 'divider', bgcolor: '#fff' },
    }}>
      <Toolbar />
      <Box sx={{ p: 2 }}>
        {navBtn('/', 'Projekte', loc.pathname === '/')}
        {navBtn('/admin/templates', 'Vorlagen', loc.pathname.startsWith('/admin/templates'))}
        <Divider sx={{ my: 2 }} />
        <Typography variant="overline" sx={{ px: 1.5, color: 'text.secondary', letterSpacing: '0.08em' }}>Projekte</Typography>
        {projects.data?.map(p => navBtn(
          `/projects/${p.id}/documents`,
          <Box><Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>{p.project_number}</Typography><Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>{p.name}</Typography></Box>,
          loc.pathname.includes(`/projects/${p.id}`),
        ))}
      </Box>
    </Drawer>
    <Box component="main" sx={{ flexGrow: 1, p: { xs: 2, md: 3 }, width: `calc(100% - ${drawerWidth}px)` }}>
      <Toolbar />
      <Routes>
        <Route path="/" element={<ProjectsPage />} /><Route path="/projects/:projectId/*" element={<ProjectWorkspace />} /><Route path="/admin/templates" element={<TemplatesPage />} /><Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Box>
  </Box>
}

function ProjectsPage() {
  const q = useQuery({ queryKey: ['projects'], queryFn: () => api<any[]>('/projects') })
  if (q.isLoading) return <Loading />
  return <Container maxWidth="lg" disableGutters>
    <Typography variant="h4" gutterBottom>Projekte</Typography>
    <Typography color="text.secondary" sx={{ mb: 3 }}>Aktive Vorhaben und Demo-Durchstich</Typography>
    <ErrorBox error={q.error} />
    <Stack spacing={2}>{q.data?.map(p => (
      <Card key={p.id} sx={{ transition: 'border-color .15s, box-shadow .15s', '&:hover': { borderColor: 'primary.light', boxShadow: '0 8px 24px rgba(15,23,42,0.06)' } }}>
        <CardContent sx={{ py: 2.5 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>{p.project_number}</Typography>
              <Typography variant="h6">{p.name}</Typography>
              <Typography color="text.secondary">{p.short_description}</Typography>
            </Box>
            <Button component={Link} to={`/projects/${p.id}/documents`} variant="contained">Öffnen</Button>
          </Stack>
        </CardContent>
      </Card>
    ))}</Stack>
  </Container>
}

function ProjectWorkspace() {
  const { projectId = '' } = useParams(); const loc = useLocation(); const p = useQuery({ queryKey: ['project', projectId], queryFn: () => api<any>(`/projects/${projectId}`) })
  if (p.isLoading) return <Loading />
  const tabs = ['documents','review','requirements','planning','commercial','offers','audit']
  const current = tabs.find(x => loc.pathname.includes(`/${x}`)) ?? 'documents'
  return <Container maxWidth="xl" disableGutters>
    <Typography variant="h4">{p.data?.project_number}</Typography>
    <Typography variant="h5" sx={{ mb: 0.5 }}>{p.data?.name}</Typography>
    <Typography color="text.secondary" sx={{ mb: 2 }}>Kundendokument → Prüfschritt → Anforderungen → Arbeitspakete → Terminplan → Angebot</Typography>
    <Tabs value={current} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}><Tab value="documents" label="1 Dokumente" component={Link} to={`/projects/${projectId}/documents`} /><Tab value="review" label="2 Prüfschritt" component={Link} to={`/projects/${projectId}/review`} /><Tab value="requirements" label="3 Anforderungen" component={Link} to={`/projects/${projectId}/requirements`} /><Tab value="planning" label="4 Planung" component={Link} to={`/projects/${projectId}/planning`} /><Tab value="commercial" label="5 Sachpositionen" component={Link} to={`/projects/${projectId}/commercial`} /><Tab value="offers" label="6 Angebote" component={Link} to={`/projects/${projectId}/offers`} /><Tab value="audit" label="Audit" component={Link} to={`/projects/${projectId}/audit`} /></Tabs>
    <Routes><Route path="documents" element={<DocumentsPage projectId={projectId} />} /><Route path="review" element={<ReviewPage projectId={projectId} />} /><Route path="requirements" element={<RequirementsPage projectId={projectId} />} /><Route path="planning" element={<PlanningPage projectId={projectId} />} /><Route path="commercial" element={<CommercialPage projectId={projectId} />} /><Route path="offers" element={<OffersPage projectId={projectId} />} /><Route path="audit" element={<AuditPage projectId={projectId} />} /><Route path="*" element={<Navigate to="documents" replace />} /></Routes>
  </Container>
}

function DocumentsPage({ projectId }: { projectId: string }) {
  const client = useQueryClient(); const { trackJob } = useJobProgress(); const auth = useQuery({ queryKey: ['me'], queryFn: me })
  const q = useQuery({ queryKey: ['docs', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/documents`) }); const [file, setFile] = useState<File | null>(null); const [uploadPercent, setUploadPercent] = useState<number | null>(null)
  const canDelete = isProjectLead(auth.data, projectId)
  const upload = useMutation({ mutationFn: () => uploadDocument(projectId, file!, setUploadPercent), onSuccess: data => { trackJob({ id: data.job_id, kind: 'document_extract', label: data.version.filename, projectId }); setFile(null); setUploadPercent(null); client.invalidateQueries({ queryKey: ['docs', projectId] }) }, onError: () => setUploadPercent(null) })
  const rebuild = useMutation({ mutationFn: () => api(`/projects/${projectId}/review/rebuild`, { method: 'POST', body: JSON.stringify({ source_selection: {} }) }), onSuccess: () => client.invalidateQueries({ queryKey: ['review', projectId] }) })
  const remove = useMutation({
    mutationFn: (documentId: string) => api(`/documents/${documentId}?reason=${encodeURIComponent('Über UI gelöscht')}`, { method: 'DELETE' }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['docs', projectId] }); void client.invalidateQueries({ queryKey: ['review', projectId] }) },
  })
  return <Stack spacing={2}><Card><CardContent><Typography variant="h6">Kundendokument hochladen</Typography><Stack direction={{xs:'column',md:'row'}} spacing={2} sx={{ mt: 2 }}><Button component="label" variant="outlined">Datei wählen<input hidden type="file" accept=".pdf,.docx,.png" onChange={e => setFile(e.target.files?.[0] ?? null)} /></Button><Typography sx={{ alignSelf:'center' }}>{file?.name ?? 'PDF, DOCX oder PNG'}</Typography><Button variant="contained" disabled={!file || upload.isPending} onClick={() => { setUploadPercent(0); upload.mutate() }}>{upload.isPending ? 'Upload läuft…' : 'Hochladen & extrahieren'}</Button><Button variant="contained" color="secondary" disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>{rebuild.isPending ? 'Prüfschritt wird aufgebaut…' : 'Prüfschritt neu aufbauen'}</Button></Stack>{upload.isPending && <Box sx={{ mt: 2 }}><Typography variant="body2">{uploadPercent === null ? 'Upload wird vorbereitet…' : uploadPercent < 100 ? `Datei wird übertragen: ${uploadPercent} %` : 'Datei übertragen; Server bestätigt den Auftrag…'}</Typography><LinearProgress variant={uploadPercent === null ? 'indeterminate' : 'determinate'} value={uploadPercent ?? 0} sx={{ mt: 1 }} /></Box>}{rebuild.isPending && <Box sx={{ mt: 2 }}><Typography variant="body2">Prüfschritt wird aufgebaut…</Typography><LinearProgress sx={{ mt: 1 }} /></Box>}<ErrorBox error={upload.error || rebuild.error || remove.error} /></CardContent></Card>
    {q.data?.map(d => <Card key={d.id}><CardContent>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'flex-start' } }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6">{d.name}</Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mt: 1 }}>{d.versions.map((v: any) => <Chip key={v.id} label={`v${v.version} · ${v.status} · ${v.page_count ?? '?'} Seiten`} color={v.status === 'ready' ? 'success' : 'default'} />)}</Stack>
        </Box>
        {canDelete && <Button
          color="error"
          variant="outlined"
          size="small"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Dokument „${d.name}“ wirklich löschen?`)) remove.mutate(d.id)
          }}
        >Löschen</Button>}
      </Stack>
    </CardContent></Card>)}</Stack>
}

function ReviewPage({ projectId }: { projectId: string }) {
  const client=useQueryClient(); const { jobs, trackJob }=useJobProgress(); const analysisRunning=jobs.some(job=>job.kind==='analysis' && job.projectId===projectId && ['queued','running','activating'].includes(job.status)); const q=useQuery({queryKey:['review',projectId],queryFn:()=>api<any>(`/projects/${projectId}/review`)})
  const approve=useMutation({mutationFn:()=>api(`/review-revisions/${q.data.review.id}/approve`,{method:'POST'}),onSuccess:()=>client.invalidateQueries({queryKey:['review',projectId]})})
  const analyze=useMutation({mutationFn:()=>api<any>(`/projects/${projectId}/analysis-runs`,{method:'POST'}),onSuccess:data=>trackJob({id:data.job_id,kind:'analysis',label:'Anforderungsanalyse',projectId,runId:data.analysis_run.id})})
  if(q.isLoading)return <Loading/>; if(!q.data?.review)return <Alert severity="info">Noch kein Prüfschritt. Bitte unter „Dokumente“ neu aufbauen.</Alert>
  const update=async(s:any,patch:any)=>{await api(`/review-revisions/${q.data.review.id}/sections/${s.id}`,{method:'PATCH',body:JSON.stringify({expected_version:s.lock_version,...patch})});await client.invalidateQueries({queryKey:['review',projectId]})}
  return <Stack spacing={2}><Card><CardContent><Stack direction="row" sx={{justifyContent:'space-between'}}><Box><Typography variant="h6">Prüfschritt Revision {q.data.review.revision_no}</Typography><Chip label={q.data.review.status} color={q.data.review.status==='approved'?'success':'warning'} /></Box><Stack direction="row" spacing={1}><Button variant="outlined" onClick={()=>approve.mutate()} disabled={q.data.review.status==='approved'}>Freigeben</Button><Button variant="contained" onClick={()=>analyze.mutate()} disabled={q.data.review.status!=='approved'||analyze.isPending||analysisRunning}>{analyze.isPending||analysisRunning?'Analyse läuft…':'Analyse ausführen & aktivieren'}</Button></Stack></Stack><ErrorBox error={approve.error||analyze.error}/>{analysisRunning&&<Alert severity="info" sx={{mt:2}}>Die Analyse läuft. Den Fortschritt siehst Du unter „Aktivitäten“.</Alert>}</CardContent></Card>
  <Paper><Table size="small"><TableHead><TableRow><TableCell>#</TableCell><TableCell>Typ</TableCell><TableCell>Text</TableCell><TableCell>Kategorie</TableCell><TableCell>Ausgeschlossen</TableCell></TableRow></TableHead><TableBody>{q.data.sections.map((s:any)=><TableRow key={s.id} sx={{opacity:s.excluded?.5:1}}><TableCell>{s.order_index+1}</TableCell><TableCell>{s.section_type}</TableCell><TableCell sx={{minWidth:500}}><TextField size="small" fullWidth multiline value={s.edited_text} onChange={()=>{}} onBlur={e=>{if(e.target.value!==s.edited_text)update(s,{edited_text:e.target.value})}} /></TableCell><TableCell><Select size="small" value={s.category} onChange={e=>update(s,{category:e.target.value})}><MenuItem value="requirement">Anforderung</MenuItem><MenuItem value="context">Kontext</MenuItem></Select></TableCell><TableCell><Checkbox checked={s.excluded} onChange={e=>update(s,{excluded:e.target.checked})}/></TableCell></TableRow>)}</TableBody></Table></Paper></Stack>
}

function RequirementsPage({projectId}:{projectId:string}){
  const client=useQueryClient();const q=useQuery({queryKey:['requirements',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/requirements`)});const [impact,setImpact]=useState<any>(null);const [selected,setSelected]=useState<any>(null)
  if(q.isLoading)return <Loading/>;return <Stack spacing={2}><Paper><Table><TableHead><TableRow><TableCell>ID</TableCell><TableCell>Anforderung</TableCell><TableCell>Priorität</TableCell><TableCell>Budget</TableCell><TableCell /></TableRow></TableHead><TableBody>{q.data?.map(r=><TableRow key={r.id}><TableCell>{r.key}</TableCell><TableCell>{r.title}</TableCell><TableCell>{r.priority}</TableCell><TableCell>{eur(r.budget_eur)}</TableCell><TableCell><Stack direction="row" spacing={1}><Button size="small" onClick={async()=>setImpact(await api(`/requirements/${r.id}/impact`))}>Impact</Button><Button size="small" onClick={()=>setSelected(r)}>Bearbeiten</Button></Stack></TableCell></TableRow>)}</TableBody></Table></Paper>
    {impact&&<Card><CardContent><Typography variant="h6">What-if Entfall</Typography><Typography>Stunden: {impact.hours_delta} h · Netto: {eur(impact.net_delta_eur)} · Termin: {impact.finish_delta_days} Tage</Typography><Typography>Abhängige Anforderungen: {impact.dependent_requirement_ids.join(', ')||'keine'}</Typography><Button onClick={()=>setImpact(null)}>Schließen</Button></CardContent></Card>}
    <Dialog open={!!selected} onClose={()=>setSelected(null)} fullWidth><DialogTitle>{selected?.key}</DialogTitle><DialogContent><TextField sx={{mt:1}} fullWidth label="Titel" defaultValue={selected?.title} id="req-title"/><TextField sx={{mt:2}} fullWidth multiline label="Text" defaultValue={selected?.text} id="req-text"/><TextField sx={{mt:2}} fullWidth label="Budget EUR" defaultValue={selected?.budget_eur??''} id="req-budget"/></DialogContent><DialogActions><Button onClick={()=>setSelected(null)}>Abbrechen</Button><Button variant="contained" onClick={async()=>{const title=(document.getElementById('req-title') as HTMLInputElement).value;const text=(document.getElementById('req-text') as HTMLInputElement).value;const budget=(document.getElementById('req-budget') as HTMLInputElement).value;await api(`/requirements/${selected.id}`,{method:'PATCH',body:JSON.stringify({expected_version:selected.lock_version,title,text,budget_eur:budget?Number(budget):null})});setSelected(null);client.invalidateQueries({queryKey:['requirements',projectId]})}}>Speichern</Button></DialogActions></Dialog>
  </Stack>
}

function PlanningPage({projectId}:{projectId:string}){
  const w=useQuery({queryKey:['workpackages',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/work-packages`)});const s=useQuery({queryKey:['schedule',projectId],queryFn:()=>api<any>(`/projects/${projectId}/schedule`)});const rates=useQuery({queryKey:['rates',projectId],queryFn:()=>api<any>(`/projects/${projectId}/rate-card`)})
  if(w.isLoading||s.isLoading)return <Loading/>;const maxDays=Math.max(...(s.data?.packages??[]).map((x:any)=>x.duration_days),1)
  return <Stack spacing={2}><Card><CardContent><Typography variant="h6">Terminplan</Typography><Typography>Projektende: {s.data?.project_finish}</Typography><Stack direction="row" spacing={1} sx={{mt:1}}>{s.data?.critical_path.map((x:string)=><Chip key={x} label={x} color="warning"/>)}</Stack></CardContent></Card>
  <Paper sx={{p:2}}>{w.data?.map((wp:any)=>{const sp=s.data?.packages.find((x:any)=>x.id===wp.id);return <Box key={wp.id} sx={{mb:1}}><Stack direction="row" spacing={2}><Typography sx={{width:100}}>{wp.key}</Typography><Typography sx={{width:260}}>{wp.name}</Typography><Box sx={{flex:1,bgcolor:sp?.critical?'warning.light':'action.hover',borderRadius:1,px:1}}>{sp?.start} → {sp?.finish} · {wp.plan_hours} h</Box></Stack></Box>})}</Paper>
  <Card><CardContent><Typography variant="h6">Rate Card</Typography><Table size="small"><TableHead><TableRow><TableCell>Rolle</TableCell><TableCell>Kapazität FTE</TableCell><TableCell>Kosten/h</TableCell><TableCell>Verkauf/h</TableCell></TableRow></TableHead><TableBody>{rates.data?.roles.map((r:any)=><TableRow key={r.id}><TableCell>{r.name}</TableCell><TableCell>{r.capacity_fte}</TableCell><TableCell>{eur(r.internal_cost_rate)}</TableCell><TableCell>{eur(r.sales_rate)}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card></Stack>
}

function OffersPage({projectId}:{projectId:string}){
  const client=useQueryClient();const q=useQuery({queryKey:['offers',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/offers`)});const reqs=useQuery({queryKey:['requirements',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/requirements`)});const [selected,setSelected]=useState<any>(null);const [working,setWorking]=useState('');const [actionError,setActionError]=useState<unknown>(null);const preview=useQuery({queryKey:['offer-preview',selected?.id],queryFn:()=>api<any>(`/offer-versions/${selected.id}/preview`),enabled:!!selected})
  const runWithProgress=async(label:string,action:()=>Promise<void>)=>{setWorking(label);setActionError(null);try{await action()}catch(error){setActionError(error)}finally{setWorking('')}}
  const create=()=>runWithProgress('Angebot wird angelegt…',async()=>{await api(`/projects/${projectId}/offers`,{method:'POST',body:JSON.stringify({offer_number:`ANG-${new Date().getFullYear()}-0001`,variant_name:'Basis',primary_variant:true,language:'de'})});await client.invalidateQueries({queryKey:['offers',projectId]})})
  const status=(target:string)=>runWithProgress('Angebotsstatus wird aktualisiert…',async()=>{await api(`/offer-versions/${selected.id}/status`,{method:'POST',body:JSON.stringify({target_status:target,comment:target==='Entwurf'?'Zur Überarbeitung':''})});await client.invalidateQueries({queryKey:['offers',projectId]});await client.invalidateQueries({queryKey:['offer-preview',selected.id]})})
  const exportFile=(format:string)=>runWithProgress(`${format.toUpperCase()} wird erstellt…`,async()=>{const r=await api<any>(`/offer-versions/${selected.id}/export?format=${format}`,{method:'POST'});window.open(artifactUrl(r.artifact_id),'_blank')})
  if(q.isLoading)return <Loading/>;const versions=q.data?.flatMap((o:any)=>o.versions.map((v:any)=>({...v,offer_number:o.offer_number,variant_name:o.variant_name})))??[]
  return <Stack spacing={2}><Stack direction="row" sx={{justifyContent:'space-between'}}><Typography variant="h6">Angebote</Typography><Button variant="contained" disabled={!!working} onClick={create}>Neue Basisvariante</Button></Stack>{working&&<Box><Typography variant="body2">{working}</Typography><LinearProgress sx={{mt:1}} /></Box>}<ErrorBox error={actionError}/>{versions.map((v:any)=><Card key={v.id} onClick={()=>setSelected(v)} sx={{cursor:'pointer',border:selected?.id===v.id?2:0,borderColor:'primary.main'}}><CardContent><Stack direction="row" sx={{justifyContent:'space-between'}}><Typography>{v.offer_number} · {v.variant_name} · V{v.version}</Typography><Chip label={v.status}/></Stack></CardContent></Card>)}
  {selected&&<Card><CardContent><Stack direction={{xs:'column',lg:'row'}} spacing={2} sx={{justifyContent:'space-between'}}><Box><Typography variant="h5">{selected.offer_number} · V{selected.version}</Typography><Typography>Netto {eur(preview.data?.pricing.net_eur)} · Brutto {eur(preview.data?.pricing.gross_eur)} · DB {eur(preview.data?.pricing.margin_eur)}</Typography><Typography>Projektende {preview.data?.schedule.project_finish}</Typography></Box><Stack direction="row" spacing={1} sx={{flexWrap:'wrap'}}>{selected.status==='Entwurf'&&<Button disabled={!!working} onClick={()=>status('zur Freigabe')}>Zur Freigabe</Button>}{selected.status==='zur Freigabe'&&<Button variant="contained" disabled={!!working} onClick={()=>status('freigegeben')}>Freigeben</Button>}{selected.status==='freigegeben'&&<Button disabled={!!working} onClick={()=>status('versendet')}>Als versendet markieren</Button>}<Button disabled={!!working} onClick={()=>exportFile('docx')}>DOCX</Button><Button disabled={!!working} onClick={()=>exportFile('xlsx')}>Excel</Button></Stack></Stack><Divider sx={{my:2}}/><Typography variant="h6">Budget-/Preiswirkung</Typography>{preview.data?.pricing.attribution.map((a:any)=><Box key={a.requirement_id} sx={{display:'grid',gridTemplateColumns:'120px 1fr 140px 140px 140px',gap:1,py:.5}}><b>{a.key}</b><span>{a.title}</span><span>Budget {eur(a.budget_eur)}</span><span>Preis {eur(a.sales_eur)}</span><span>Spielraum {eur(a.budget_delta_eur)}</span></Box>)}</CardContent></Card>}</Stack>
}


function CommercialPage({projectId}:{projectId:string}){
  const client=useQueryClient();const reqs=useQuery({queryKey:['requirements',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/requirements`)});const q=useQuery({queryKey:['materials',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/materials`)});const [description,setDescription]=useState('');const [cost,setCost]=useState('0');const [sales,setSales]=useState('0');const [reqId,setReqId]=useState('')
  const create=async()=>{await api(`/projects/${projectId}/materials`,{method:'POST',body:JSON.stringify({description,cost_eur:Number(cost),sales_eur:Number(sales),requirement_ids:reqId?[reqId]:[],scaling_mode:'proportional'})});setDescription('');setCost('0');setSales('0');client.invalidateQueries({queryKey:['materials',projectId]})}
  return <Stack spacing={2}><Card><CardContent><Typography variant="h6">Sachpositionen</Typography><Stack direction={{xs:'column',md:'row'}} spacing={1} sx={{mt:2}}><TextField label="Beschreibung" value={description} onChange={e=>setDescription(e.target.value)} fullWidth/><TextField label="Kosten EUR" type="number" value={cost} onChange={e=>setCost(e.target.value)}/><TextField label="Verkauf EUR" type="number" value={sales} onChange={e=>setSales(e.target.value)}/><FormControl sx={{minWidth:220}}><InputLabel>Anforderung</InputLabel><Select label="Anforderung" value={reqId} onChange={e=>setReqId(String(e.target.value))}><MenuItem value="">Übergreifend</MenuItem>{reqs.data?.map((r:any)=><MenuItem key={r.id} value={r.id}>{r.key}</MenuItem>)}</Select></FormControl><Button variant="contained" disabled={!description} onClick={create}>Hinzufügen</Button></Stack></CardContent></Card><Paper><Table><TableHead><TableRow><TableCell>ID</TableCell><TableCell>Beschreibung</TableCell><TableCell>Kosten</TableCell><TableCell>Verkauf</TableCell><TableCell>Verknüpfung</TableCell></TableRow></TableHead><TableBody>{q.data?.map((m:any)=><TableRow key={m.id}><TableCell>{m.key}</TableCell><TableCell>{m.description}</TableCell><TableCell>{eur(m.cost_eur)}</TableCell><TableCell>{eur(m.sales_eur)}</TableCell><TableCell>{m.requirement_ids.join(', ')||'übergreifend'}</TableCell></TableRow>)}</TableBody></Table></Paper></Stack>
}

function AuditPage({projectId}:{projectId:string}){const q=useQuery({queryKey:['audit',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/audit`)});const presence=useQuery({queryKey:['presence',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/presence`),refetchInterval:30000});return <Stack spacing={2}><Card><CardContent><Typography variant="h6">Aktive Projektbenutzer</Typography><Stack direction="row" spacing={1} sx={{mt:1}}>{presence.data?.map((x:any)=><Chip key={x.user_id} label={`${x.name} · ${x.area}`}/>)}</Stack></CardContent></Card><Card><CardContent><Typography variant="h6">Audit-Ereignisse</Typography><Table size="small"><TableHead><TableRow><TableCell>Zeit</TableCell><TableCell>Benutzer</TableCell><TableCell>Aktion</TableCell><TableCell>Objekt</TableCell></TableRow></TableHead><TableBody>{q.data?.map((x:any)=><TableRow key={x.id}><TableCell>{x.created_at}</TableCell><TableCell>{x.actor_user_id}</TableCell><TableCell>{x.action}</TableCell><TableCell>{x.entity_type} {x.entity_id}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card></Stack>}

function DraggableBlock({id,text}:{id:string,text:string}){const d=useDraggable({id});const drop=useDroppable({id});return <Paper ref={(node)=>{d.setNodeRef(node);drop.setNodeRef(node)}} {...d.listeners} {...d.attributes} sx={{p:1,my:1,cursor:'grab',opacity:d.isDragging?.5:1,outline:drop.isOver?'2px solid':'none',outlineColor:'primary.main'}}>{text}</Paper>}
function TemplatesPage(){const tenants=useQuery({queryKey:['tenants'],queryFn:()=>api<any[]>('/tenants')});const tenantId=tenants.data?.[0]?.id;const q=useQuery({queryKey:['templates',tenantId],queryFn:()=>api<any[]>(`/templates?tenant_id=${tenantId}`),enabled:!!tenantId});const editor=useEditor({extensions:[StarterKit],content:'<p>Wir bedanken uns für Ihre Anfrage und bieten wie folgt an.</p>'});const [blocks,setBlocks]=useState(['Einleitung','Leistungsumfang','Terminplan','Preis','Zahlungsplan']);const onDragEnd=(e:DragEndEvent)=>{const a=blocks.indexOf(String(e.active.id)),b=blocks.indexOf(String(e.over?.id??''));if(a>=0&&b>=0){const n=[...blocks];const [x]=n.splice(a,1);n.splice(b,0,x);setBlocks(n)}}
  return <Container maxWidth="lg"><Typography variant="h4" gutterBottom>Abgabedokument-Vorlagen</Typography><Typography color="text.secondary">Versionierte Vorlagen mit Rich-Text-Bausteinen und Systemplatzhaltern.</Typography><Card sx={{mt:2}}><CardContent><Typography variant="h6">Rich Text</Typography><Box sx={{border:'1px solid',borderColor:'divider',borderRadius:1,p:2,my:1}}><EditorContent editor={editor}/></Box><Typography variant="h6" sx={{mt:2}}>Baustein-Reihenfolge</Typography><DndContext onDragEnd={onDragEnd}>{blocks.map(x=><DraggableBlock key={x} id={x} text={x}/>)}</DndContext></CardContent></Card><Stack sx={{mt:2}} spacing={1}>{q.data?.map((t:any)=><Card key={t.id}><CardContent><Typography>{t.name}</Typography><Typography variant="body2">Versionen: {t.versions.map((v:any)=>`v${v.version} (${v.status})`).join(', ')}</Typography></CardContent></Card>)}</Stack></Container>
}

function CustomerPortalShell({auth}:{auth:any}){const nav=useNavigate();const {clearJobs}=useJobProgress();const projects=useQuery({queryKey:['projects'],queryFn:()=>api<any[]>('/projects')});const logout=async()=>{await api('/auth/logout',{method:'POST'});sessionStorage.clear();clearJobs();await qc.cancelQueries();qc.removeQueries({predicate:query=>query.queryKey[0]!=='me'});qc.setQueryData(['me'],null);nav('/login')};const roles=summarizeRoles(auth);return <Box sx={{minHeight:'100vh',bgcolor:'background.default'}}><AppBar position="static" color="transparent" sx={{bgcolor:'rgba(255,255,255,0.9)',backdropFilter:'blur(12px)',borderBottom:'1px solid',borderColor:'divider',color:'text.primary'}}><Toolbar sx={{gap:1.5}}><Typography variant="h6" sx={{flexGrow:1,color:'primary.dark'}}>KuSys Kundenportal</Typography><Typography variant="body2" sx={{fontWeight:600}}>{auth.user.display_name}</Typography><Chip label={roles} size="small" color="primary" variant="outlined" sx={{borderWidth:1.5,bgcolor:'rgba(15,118,110,0.06)'}}/><DemoRoleSwitcher auth={auth}/><Button onClick={logout} variant="outlined" size="small" color="secondary">Abmelden</Button></Toolbar></AppBar><Container maxWidth="lg" sx={{py:4}}><Routes><Route path="/" element={<Stack spacing={2}><Typography variant="h4">Veröffentlichte Projekte</Typography>{projects.data?.map((p:any)=><Card key={p.id}><CardContent><Stack direction="row" sx={{justifyContent:'space-between'}}><Box><Typography variant="h6">{p.project_number} · {p.name}</Typography><Typography color="text.secondary">{p.status}</Typography></Box><Button component={Link} to={`/portal/${p.id}`} variant="contained">Öffnen</Button></Stack></CardContent></Card>)}</Stack>}/><Route path="/portal/:projectId" element={<CustomerProjectPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></Container></Box>}

function CustomerProjectPage(){const {projectId=''}=useParams();const client=useQueryClient();const q=useQuery({queryKey:['portal',projectId],queryFn:()=>api<any>(`/portal/projects/${projectId}`)});const [answers,setAnswers]=useState<Record<string,string>>({});if(q.isLoading)return <Loading/>;return <Stack spacing={3}><Button component={Link} to="/" sx={{alignSelf:'flex-start'}}>← Projekte</Button><Box><Typography variant="h4">{q.data?.project_number} · {q.data?.name}</Typography><Typography color="text.secondary">Status: {q.data?.status}</Typography></Box><Card><CardContent><Typography variant="h6">Freigegebene Dokumente</Typography><Stack spacing={1} sx={{mt:1}}>{q.data?.published_artifacts.length?q.data.published_artifacts.map((a:any)=><Button key={a.artifact_id} component="a" href={artifactUrl(a.artifact_id)} target="_blank" rel="noreferrer" variant="outlined" sx={{alignSelf:'flex-start'}}>{a.kind} ({a.language}) herunterladen</Button>):<Typography color="text.secondary">Noch keine veröffentlichten Dokumente.</Typography>}</Stack></CardContent></Card><Card><CardContent><Typography variant="h6">Klärungspunkte</Typography><Stack spacing={2} sx={{mt:2}}>{q.data?.clarifications.map((c:any)=><Box key={c.id}><Typography sx={{fontWeight:600}}>{c.key} · {c.text}</Typography><Typography variant="body2" color="text.secondary">{c.status}</Typography>{c.answer?<Alert severity="info" sx={{mt:1}}>{c.answer}</Alert>:<Stack direction={{xs:'column',md:'row'}} spacing={1} sx={{mt:1}}><TextField size="small" fullWidth label="Ihre Antwort" value={answers[c.id]??''} onChange={e=>setAnswers({...answers,[c.id]:e.target.value})}/><Button variant="contained" onClick={async()=>{await api(`/portal/clarifications/${c.id}/answer`,{method:'POST',body:JSON.stringify({answer:answers[c.id]??''})});setAnswers({...answers,[c.id]:''});client.invalidateQueries({queryKey:['portal',projectId]})}}>Antworten</Button></Stack>}</Box>)}</Stack></CardContent></Card></Stack>}

function App(){const auth=useQuery({queryKey:['me'],queryFn:me});if(auth.isLoading)return <Loading/>;if(auth.isError||!auth.data?.user)return <Routes><Route path="*" element={<LoginPage/>}/></Routes>;const projectRoles=auth.data.project_roles??[];const internalProjectRole=projectRoles.some((r:any)=>r.role==='project_lead'||r.role==='project_member');const companyAdmin=(auth.data.tenant_roles??[]).some((r:any)=>r.role==='company_admin');const customer=projectRoles.some((r:any)=>r.role==='customer')&&!internalProjectRole&&!companyAdmin&&!auth.data.user.is_platform_admin;return customer?<CustomerPortalShell key={auth.data.user.id} auth={auth.data}/>:<Shell key={auth.data.user.id} auth={auth.data}/>}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={qc}>
        <JobProgressProvider>
          <BrowserRouter><App /></BrowserRouter>
        </JobProgressProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
)
