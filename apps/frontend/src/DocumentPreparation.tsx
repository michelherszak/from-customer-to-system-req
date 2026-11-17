import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material'
import { useNavigate } from 'react-router'
import { api } from './api'
import { useJobProgress } from './jobProgress'

export function DocumentPreparation({ projectId, documents }: { projectId: string; documents: any[] }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { trackJob } = useJobProgress()
  const [versionId, setVersionId] = useState('')
  const [providerId, setProviderId] = useState('')
  const [model, setModel] = useState('')
  const [selectedJob, setSelectedJob] = useState('')
  const options = useQuery({ queryKey: ['analysis-options', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/analysis-options`) })
  const previews = useQuery({ queryKey: ['document-preparations', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/document-preparations`), refetchInterval: query => query.state.data?.some(x => ['queued', 'running'].includes(x.status)) ? 1500 : false })
  const review = useQuery({ queryKey: ['review', projectId], queryFn: () => api<any>(`/projects/${projectId}/review`) })
  const versions = documents.flatMap(doc => doc.versions.filter((v: any) => v.status === 'ready').map((v: any) => ({ ...v, name: doc.name })))
  const selectedVersion = versionId || versions[0]?.id || ''
  const provider = options.data?.find(x => x.id === providerId)
  const preview = previews.data?.find(x => x.id === selectedJob) ?? previews.data?.[0]
  const result = preview?.result
  const start = useMutation({
    mutationFn: () => api<any>(`/projects/${projectId}/document-preparations`, { method: 'POST', body: JSON.stringify({ document_version_id: selectedVersion, provider_config_id: providerId || null, model_id: providerId ? model || provider?.models[0] : null }) }),
    onSuccess: data => { setSelectedJob(data.job_id); trackJob({ id: data.job_id, kind: 'document_prepare', label: 'Dokumentaufbereitung', projectId }); void client.invalidateQueries({ queryKey: ['document-preparations', projectId] }) },
  })
  const apply = useMutation({
    mutationFn: () => api<any>(`/projects/${projectId}/review/rebuild`, { method: 'POST', body: JSON.stringify({ preparation_job_id: preview.id, expected_review_id: review.data?.review?.id ?? null }) }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['review', projectId] }); navigate(`/projects/${projectId}/review`) },
  })
  if (!versions.length) return null
  return <Card><CardContent><Stack spacing={2}>
    <Box><Typography variant="h6">Dokumentaufbereitung</Typography><Typography variant="body2" color="text.secondary">Zusammengehörige Absätze und Tabellenzeilen rekonstruieren. Zuerst vergleichen; dein bestehender Prüfschritt bleibt erhalten.</Typography></Box>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
      <FormControl size="small" sx={{ minWidth: 220, flex: 1 }}><InputLabel>Dokument</InputLabel><Select label="Dokument" value={selectedVersion} onChange={e => setVersionId(e.target.value)}>{versions.map(v => <MenuItem key={v.id} value={v.id}>{v.name} · v{v.version}</MenuItem>)}</Select></FormControl>
      <FormControl size="small" sx={{ minWidth: 210 }}><InputLabel>Aufbereitung</InputLabel><Select label="Aufbereitung" value={providerId} onChange={e => { setProviderId(e.target.value); setModel('') }}><MenuItem value="">Layoutbasiert · lokal</MenuItem>{options.data?.map(p => <MenuItem key={p.id} value={p.id}>{p.provider} · KI-Modell</MenuItem>)}</Select></FormControl>
      {provider && <FormControl size="small" sx={{ minWidth: 180 }}><InputLabel>Modell</InputLabel><Select label="Modell" value={model || provider.models[0]} onChange={e => setModel(e.target.value)}>{provider.models.map((m: string) => <MenuItem key={m} value={m}>{m}</MenuItem>)}</Select></FormControl>}
      <Button variant="outlined" disabled={start.isPending || previews.data?.some(x => ['queued', 'running'].includes(x.status))} onClick={() => start.mutate()}>Aufbereiten & vergleichen</Button>
    </Stack>
    {options.data?.length === 0 && <Typography variant="caption" color="text.secondary">Für die KI-Aufbereitung muss ein KI-Anbieter mit Modell konfiguriert sein. Die lokale Aufbereitung funktioniert ohne API-Schlüssel.</Typography>}
    {(start.error || apply.error || previews.error) && <Alert severity="error">{String(start.error ?? apply.error ?? previews.error)}</Alert>}
    {preview && ['queued', 'running'].includes(preview.status) && <Alert severity="info">Dokument wird aufbereitet. Den Fortschritt siehst du unter Aktivitäten.</Alert>}
    {preview?.status === 'failed' && <Alert severity="error">{preview.message}</Alert>}
    {result?.groups && <>
      {previews.data!.filter(x => x.status === 'succeeded').length > 1 && <Select size="small" value={preview.id} onChange={e => setSelectedJob(e.target.value)}>{previews.data!.filter(x => x.status === 'succeeded').map(x => <MenuItem key={x.id} value={x.id}>{x.result.filename} · {x.result.method === 'model' ? 'KI' : 'Layout'} · {x.result.metrics.prepared_sections} Abschnitte</MenuItem>)}</Select>}
      <Alert severity="info">{result.filename}: {result.metrics.original_blocks} Originalblöcke → {result.metrics.prepared_sections} Abschnitte · {result.metrics.joined_groups} Zusammenführungen · Quellenabdeckung {result.metrics.source_coverage} · {result.metrics.uncertain_groups} unsichere Gruppen. {result.method === 'model' ? `KI: ${result.provider} / ${result.model}` : 'Lokal anhand von Layout und Anforderungs-IDs.'}</Alert>
      <Box component="details"><Box component="summary" sx={{ cursor: 'pointer', fontWeight: 600 }}>Original und Aufbereitung vergleichen</Box><Stack spacing={1} sx={{ mt: 1, maxHeight: 480, overflow: 'auto' }}>{result.groups.map((g: any, i: number) => <Box component="details" key={i} sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
        <Box component="summary" sx={{ cursor: 'pointer' }}>Abschnitt {i + 1} · Seite {g.pages.join(', ') || '–'} · {g.source_ids.length} Originalblöcke{g.uncertain ? ' · bitte prüfen' : ''}: {g.text.slice(0, 100)}</Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 1 }}><Box sx={{ flex: 1 }}><Typography variant="subtitle2">Originalfragmente</Typography>{g.source_ids.map((id: string) => <Typography key={id} variant="body2" sx={{ whiteSpace: 'pre-wrap', borderBottom: '1px dashed', borderColor: 'divider', py: 0.5 }}>{result.original_blocks.find((b: any) => b.id === id)?.text}</Typography>)}</Box><Box sx={{ flex: 1 }}><Typography variant="subtitle2">Zusammengehöriger Abschnitt</Typography><Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{g.text}</Typography><Typography variant="caption">{g.reason}</Typography></Box></Stack>
      </Box>)}</Stack></Box>
      <Button variant="contained" disabled={apply.isPending || review.isPending || review.isError} onClick={() => {
        if (window.confirm('Neue Prüfschritt-Revision aus dieser Vorschau erstellen? Die bisherige Revision bleibt erhalten. Manuelle Korrekturen unveränderter Quellen werden übernommen; geschützte Abschnitte bleiben getrennt.')) apply.mutate()
      }}>{apply.isPending ? 'Neue Revision wird erstellt…' : 'Als neue Prüfschritt-Revision übernehmen'}</Button>
    </>}
  </Stack></CardContent></Card>
}
