import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Chip, MenuItem, Select, Stack, Typography } from '@mui/material'
import { api, me } from './api'
import { AgentDiagnostics } from './AgentDiagnostics'
import { ReviewBlockers } from './ReviewBlockers'
import { useJobProgress } from './jobProgress'

const labels: Record<string, string> = { accepted: 'Geprüft', needs_human_review: 'Fachliche Bestätigung erforderlich', blocked: 'Offene Blocker', accepted_with_assumptions: 'Mit Annahmen', changes_required: 'Überarbeiten' }
const roles: Record<string, string> = { requirements_engineer: 'Requirements Engineer', systems_engineer: 'Systems Engineer', work_planner: 'Arbeitsplaner / Aufwandsschätzer', review_engineer: 'Review Engineer' }
const checks = ['source_fidelity', 'necessity', 'completeness', 'feasibility', 'verifiability', 'sizing']
const checkLabels: Record<string, string> = { source_fidelity: 'Quellentreue', necessity: 'Notwendigkeit', completeness: 'Vollständigkeit', feasibility: 'Machbarkeit', verifiability: 'Prüfbarkeit', sizing: 'Dimensionierung / Aufwand' }

export function EngineeringReview({ projectId }: { projectId: string }) {
  const client = useQueryClient()
  const { trackJob } = useJobProgress()
  const runs = useQuery({ queryKey: ['engineering-runs', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/analysis-runs`), refetchInterval: query => query.state.data?.some(run => ['queued','running'].includes(run.status)) ? 4000 : 30000 })
  const auth = useQuery({ queryKey: ['me'], queryFn: me })
  const [selected, setSelected] = useState('')
  const [round, setRound] = useState<number | null>(null)
  const [error, setError] = useState('')
  const run = runs.data?.find(x => x.id === selected) ?? runs.data?.[0]
  const result = run?.result
  const quality = result?.quality
  const history = result?.review_history ?? []
  const snapshot = history.find((x: any) => x.round === round) ?? history.at(-1)
  const artifacts = snapshot?.artifacts ?? result
  const canActivate = (auth.data?.project_roles ?? []).some((x: any) => x.project_id === projectId && x.role === 'project_lead') || (auth.data?.tenant_roles ?? []).some((x: any) => x.tenant_id === run?.tenant_id && x.role === 'company_admin')
  const inProgress = runs.data?.some(x => ['queued','running'].includes(x.status))
  const onRechecked = async (data:any) => {
    setSelected(data.analysis_run.id); setRound(null)
    trackJob({id:data.job_id,kind:'analysis',label:'Engineering-Nachprüfung',projectId,runId:data.analysis_run.id})
    await client.invalidateQueries({queryKey:['engineering-runs',projectId]})
  }
  const retry = useMutation({
    mutationFn: (mode: 'resume' | 'restart') => api<any>(`/analysis-runs/${run.id}/${mode}`, {method:'POST'}),
    onSuccess: onRechecked,
  })
  const activate = useMutation({
    mutationFn: () => api(`/analysis-runs/${run.id}/activate`, { method: 'POST', body: JSON.stringify({ acknowledge_assumptions: quality?.status === 'needs_human_review' }) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['engineering-runs', projectId] }); void client.invalidateQueries({ queryKey: ['requirements', projectId] }); void client.invalidateQueries({ queryKey: ['workpackages', projectId] }); void client.invalidateQueries({ queryKey: ['schedule', projectId] }) },
  })
  const download = async () => {
    setError('')
    try {
      const response = await api<Response>(`/analysis-runs/${run.id}/documentation`)
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `KuSys-Engineering-${run.id}.md`; anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError(String(e)) }
  }
  if (!runs.data?.length) return <Alert severity={runs.isError ? 'error' : 'info'}>{runs.isError ? String(runs.error) : 'Nach einer Analyse erscheinen hier Systemableitungen, Architektur, Einzelprüfungen und Schätzgrundlagen.'}</Alert>
  return <Card><CardContent><Stack spacing={2}>
    <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
      <Typography variant="h6" sx={{ flex: 1 }}>Engineering & Review</Typography>
      <Select size="small" value={run.id} onChange={e => { setSelected(e.target.value); setRound(null) }}>{runs.data.map((x, i) => <MenuItem key={x.id} value={x.id}>Lauf {runs.data!.length - i} · {x.status}</MenuItem>)}</Select>
      {result && <Button onClick={() => void download()}>Dokumentation herunterladen</Button>}
    </Stack>
    <Stack direction="row" sx={{gap:1,flexWrap:'wrap'}}>
      {(run.status === 'failed'||(run.status==='succeeded'&&quality?.status==='blocked')) && <Button variant={quality?.status==='blocked'?'outlined':'contained'} disabled={retry.isPending||inProgress} onClick={()=>retry.mutate('resume')}>{quality?.status==='blocked'?'Ohne neue Antworten automatisch fortsetzen':'Ab letztem Checkpoint fortsetzen'}</Button>}
      <Button variant="outlined" disabled={retry.isPending||inProgress} onClick={()=>{if(window.confirm('Neuen Lauf ohne Übernahme bisheriger Agentenergebnisse starten? Der bisherige Lauf bleibt gespeichert.'))retry.mutate('restart')}}>Komplett neu starten</Button>
    </Stack>
    <Typography variant="body2" color="text.secondary">Fortsetzen übernimmt gültige abgeschlossene Pakete. Geänderte Eingaben werden neu verarbeitet. Neu starten verwendet keine Ergebnisse früherer Läufe. Kosten und Termine werden anschließend aus dem aktuellen Plan berechnet.</Typography>
    {retry.error && <Alert severity="error">{String(retry.error)}</Alert>}
    {quality?.status==='blocked'&&<ReviewBlockers key={`responses-${run.id}`} runId={run.id} projectId={projectId} busy={!!inProgress||retry.isPending} onRechecked={onRechecked}/>}
    <AgentDiagnostics key={run.id} runId={run.id} />
    {!quality && <Alert severity="info">{run.status === 'queued' || run.status === 'running' ? 'Der Agentenstatus und die einzelnen Aufrufe stehen im Diagnoseprotokoll. Ergebnisse erscheinen nach Abschluss.' : 'Dieser ältere Lauf enthält noch keine vierstufige Engineering-Prüfung. Bitte neu analysieren.'}</Alert>}
    {quality && <>
      <Alert severity={quality.status === 'blocked' ? 'error' : quality.status === 'needs_human_review' ? 'warning' : 'success'}>
        <strong>{labels[quality.status]}</strong> · {quality.review_cycle?`Nachprüfung ${quality.review_cycle.completed}/${quality.review_cycle.limit} Runden · ${quality.rounds_completed} Runden insgesamt`:`${quality.rounds_completed}/${quality.max_rounds} Runden`} · {quality.engine === 'crewai' ? 'CrewAI · ' : ''} {quality.offline ? 'Regelbasierter Altstand ohne KI – keine gültige Ableitung' : `${run.provider} / ${run.model_id}`}<br />{quality.summary}
      </Alert>
      {run.status === 'succeeded' && canActivate && quality.status !== 'blocked' && <Button variant="contained" disabled={activate.isPending} onClick={() => {
        if (quality.status !== 'needs_human_review' || window.confirm('Die Ableitungen und Schätzungen enthalten ungeprüfte Annahmen. Als vorläufigen Arbeitsstand in Anforderungen und Planung übernehmen?')) activate.mutate()
      }}>{quality.status === 'needs_human_review' ? 'Annahmen bestätigen & Arbeitsstand übernehmen' : 'Geprüfte Ergebnisse übernehmen'}</Button>}
      {(activate.error || error) && <Alert severity="error">{String(activate.error ?? error)}</Alert>}
      <Typography variant="body2">Geschätzter Aufwand: {result.estimate_summary?.min_hours}–{result.estimate_summary?.max_hours} Personenstunden · wahrscheinlich {result.estimate_summary?.likely_hours} h. Kosten und Termine werden nach Übernahme unter Planung mit Rate Card und Kalendern berechnet.</Typography>
      {result.estimate_summary?.scenarios && <Box sx={{p:2,bgcolor:'action.hover',borderRadius:2}}>
        <Typography variant="subtitle2">Budget- und Terminszenarien (Arbeitsanteil)</Typography>
        {Object.entries(result.estimate_summary.scenarios).map(([key, value]) => { const x = value as any; return <Typography key={key} variant="body2">{{minimum:'Minimum',likely:'Wahrscheinlich',maximum:'Maximum'}[key]}: {x.hours} h · Kosten {x.labor_cost_eur ?? 'offen'} EUR · Verkauf {x.labor_sales_eur ?? 'offen'} EUR · Ende {x.project_finish ?? 'offen'} {x.schedule_error ? `(${x.schedule_error})` : ''}</Typography> })}
        <Typography variant="caption">{result.estimate_summary.start_basis} · {result.estimate_summary.excluded}</Typography>
      </Box>}
      <Stack direction="row" spacing={1}>{history.map((x: any) => <Button key={x.round} variant={snapshot?.round === x.round ? 'contained' : 'outlined'} onClick={() => setRound(x.round)}>Runde {x.round}</Button>)}</Stack>
      <Typography variant="subtitle1">Kundenanforderungen → Systemanforderungen → Arbeitspakete</Typography>
      {artifacts?.requirements?.map((req: any) => <Box key={req.key} id={`engineering-${req.key}`} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2 }}>
        <Typography sx={{ fontWeight: 600 }}>{req.key} · {req.title}</Typography><Typography>{req.text}</Typography><Typography variant="caption" color="text.secondary">Quelle: {req.source_section_id} · Kategorie: Anforderung</Typography>
        {artifacts.system_requirements?.filter((sys: any) => sys.parent_keys.includes(req.key)).map((sys: any) => <Box key={sys.key} id={`engineering-${sys.key}`} sx={{ mt: 2, pl: 2, borderLeft: '3px solid', borderColor: 'primary.light' }}>
          <Typography sx={{ fontWeight: 600 }}>{sys.key} · {sys.title}</Typography><Typography>{sys.text}</Typography>
          <Typography variant="body2">Ableitung aus {sys.parent_keys.join(', ')}: {sys.rationale}</Typography>
          <Typography variant="body2">Nachweis ({sys.verification_method}): {sys.verification_criterion}</Typography>
          {sys.assumptions.map((a: string, i: number) => <Typography key={i} variant="body2" color="warning.main">Annahme: {a}</Typography>)}
          {artifacts.work_packages?.filter((wp: any) => wp.system_requirement_keys.includes(sys.key)).map((wp: any) => <Box key={wp.key} id={`engineering-${wp.key}`} sx={{ mt: 1, p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
            <Typography variant="body2"><strong>{wp.key} · {wp.name}</strong> · {wp.role} · {wp.phase}</Typography><Typography variant="body2">{wp.description}</Typography>
            <Typography variant="body2">{wp.min_hours} / {wp.likely_hours} / {wp.max_hours} h · Vorgänger: {wp.depends_on.join(', ') || 'keine'}</Typography>
            <Typography variant="body2">Schätzgrundlage: {wp.estimate_basis}</Typography>
            <Typography variant="body2">Annahmen: {wp.assumptions.join('; ') || 'keine'} · Risiken: {wp.risks.join('; ') || 'keine'}</Typography>
          </Box>)}
        </Box>)}
      </Box>)}
      <Typography variant="subtitle1">Architektur</Typography>
      {artifacts?.architecture?.map((x: any) => <Box key={x.key} id={`engineering-${x.key}`}><Typography sx={{ fontWeight: 600 }}>{x.key} · {x.name}</Typography><Typography variant="body2">{x.description} · SYS: {x.covers.join(', ')}</Typography><Typography variant="body2">Schnittstellen: {x.interfaces.join('; ') || 'keine angegeben'}</Typography></Box>)}
      <Typography variant="subtitle1">Einzelprüfungen · Runde {snapshot?.round}</Typography>
      {snapshot?.review?.assessments?.map((x: any) => <Box component="details" key={x.target_key} sx={{ p: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box component="summary" sx={{ cursor: 'pointer' }}>{x.target_key} · {roles[x.owner]} <Chip size="small" label={labels[x.verdict] ?? x.verdict} sx={{ ml: 1 }} /></Box>
        {checks.map(k => <Typography key={k} variant="body2"><strong>{checkLabels[k]}:</strong> {x[k]}</Typography>)}
        {x.question && <Typography variant="body2">Rückfrage: {x.question}</Typography>}{x.required_change && <Typography variant="body2">Korrektur: {x.required_change}</Typography>}
        {quality.status==='blocked'&&quality.findings?.some((finding:any)=>finding.target_key===x.target_key)&&<Button component="a" href={`#review-responses-${run.id}`}>Befund beantworten & nachprüfen lassen</Button>}
      </Box>)}
    </>}
  </Stack></CardContent></Card>
}
