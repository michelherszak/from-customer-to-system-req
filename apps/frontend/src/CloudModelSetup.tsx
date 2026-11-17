import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Autocomplete, Button, Stack, TextField, Typography } from '@mui/material'
import { api, me } from './api'

type Model = { id: string; provider: string; provider_label: string; model: string; label: string }
type Props = { tenantId: string; selectedProviderId?: string; selectedModel?: string; onConfigured?: (providerId: string, model: string) => void }

export function CloudModelSetup({ tenantId, selectedProviderId, selectedModel, onConfigured }: Props) {
  const client = useQueryClient()
  const auth = useQuery({ queryKey: ['me'], queryFn: me })
  const [modelId, setModelId] = useState('')
  const [key, setKey] = useState('')
  const canConfigure = (auth.data?.tenant_roles ?? []).some((r: any) => r.tenant_id === tenantId && r.role === 'company_admin')
  const catalog = useQuery({ queryKey: ['ai-model-catalog'], queryFn: () => api<Model[]>('/ai-model-catalog'), enabled: canConfigure })
  const profiles = useQuery({ queryKey: ['ai-provider-profiles', tenantId], queryFn: () => api<any[]>(`/tenants/${tenantId}/ai-providers`), enabled: canConfigure })
  const selectedProvider = profiles.data?.find(x => x.id === selectedProviderId)?.provider
  const model = catalog.data?.find(x => x.id === modelId) ?? catalog.data?.find(x => x.model === selectedModel && x.provider === selectedProvider) ?? catalog.data?.[0] ?? null
  const profile = profiles.data?.find(x => x.provider === model?.provider)
  const save = useMutation({
    mutationFn: () => api<any>('/ai-model-selection', { method: 'POST', body: JSON.stringify({ tenant_id: tenantId, catalog_id: model?.id, api_key: key.trim() || null, expected_version: profile?.lock_version ?? null }) }),
    onSuccess: async data => {
      setKey('')
      onConfigured?.(data.id, data.selected_model)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['analysis-options'] }),
        client.invalidateQueries({ queryKey: ['ai-provider-profiles', tenantId] }),
      ])
    },
  })
  if (auth.isPending) return <Typography>Modellverbindung wird geladen …</Typography>
  if (!canConfigure) return <Alert severity="info">Ein Firmen-Admin kann das Cloud-Modell auswählen und den API-Schlüssel hinterlegen.</Alert>
  const loading = catalog.isPending || profiles.isPending
  return <Stack spacing={2}>
    <Autocomplete options={catalog.data ?? []} value={model} loading={loading} groupBy={x => x.provider_label} disabled={loading || save.isPending}
      getOptionLabel={x => x.label} isOptionEqualToValue={(a, b) => a.id === b.id}
      onChange={(_, next) => { save.reset(); if (next?.provider !== model?.provider) setKey(''); setModelId(next?.id ?? '') }}
      renderInput={params => <TextField {...params} label="Cloud-Modell" />} />
    <TextField label={profile?.has_api_key ? `API-Schlüssel für ${model?.provider_label} ersetzen (optional)` : `API-Schlüssel für ${model?.provider_label ?? 'den Anbieter'}`} type="password" value={key}
      onChange={e => {save.reset();setKey(e.target.value)}} autoComplete="new-password" disabled={loading || save.isPending}
      helperText={profile?.has_api_key ? `API-Schlüssel hinterlegt (${model?.provider_label}). Leer lassen, um ihn weiterzuverwenden.` : `Noch kein API-Schlüssel für ${model?.provider_label ?? 'diesen Anbieter'} hinterlegt. Der Schlüssel wird verschlüsselt gespeichert.`} />
    <Button variant="outlined" sx={{alignSelf:'flex-start'}} disabled={!model || loading || catalog.isError || profiles.isError || (!key.trim() && !profile?.has_api_key) || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Wird gespeichert …' : 'Modell & API-Schlüssel speichern'}</Button>
    {save.isSuccess && <Alert severity="success">Modellverbindung gespeichert. Zum Übernehmen des Standardmodells unten „Agenteneinstellungen speichern“ wählen.</Alert>}
    <Typography variant="caption" color="text.secondary">Projektdaten werden erst beim Start einer Analyse oder Modellaufbereitung an den ausgewählten Anbieter übermittelt.</Typography>
    {(save.error || catalog.error || profiles.error) && <Alert severity="error">{String(save.error ?? catalog.error ?? profiles.error)}</Alert>}
  </Stack>
}
