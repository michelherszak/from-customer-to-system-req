import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, LinearProgress, Stack, Typography } from '@mui/material'
import { api } from './api'

type JobKind = 'document_extract' | 'analysis'
type JobStatus = 'queued' | 'running' | 'activating' | 'succeeded' | 'failed' | 'cancelled'
type TrackedJob = {
  id: string
  kind: JobKind
  label: string
  projectId: string
  runId?: string
  status: JobStatus
  progress: number
  message: string
  finishedAt?: number
}
type JobSnapshot = { status: string; progress: number; message: string | null; error_code: string | null }
type JobContextValue = {
  jobs: TrackedJob[]
  trackJob: (job: Pick<TrackedJob, 'id' | 'kind' | 'label' | 'projectId' | 'runId'>) => void
  dismissJob: (id: string) => void
  clearJobs: () => void
}

const storageKey = 'kusys_progress_jobs'
/** Abgeschlossene/fehlgeschlagene Aktivitäten nach dieser Zeit ausblenden. */
const FINISHED_TTL_MS = 12_000
const JobContext = createContext<JobContextValue | null>(null)
const active = (job: TrackedJob) => ['queued', 'running', 'activating'].includes(job.status)

function restoredJobs(): TrackedJob[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? '[]')
    const now = Date.now()
    return Array.isArray(saved)
      ? saved.filter((job: TrackedJob) => {
          if (!job?.id || !job?.projectId || !job?.kind) return false
          if (active(job)) return true
          const finishedAt = job.finishedAt ?? now
          return now - finishedAt < FINISHED_TTL_MS
        })
      : []
  } catch {
    return []
  }
}

export function useJobProgress(): JobContextValue {
  const value = useContext(JobContext)
  if (!value) throw new Error('JobProgressProvider fehlt')
  return value
}

export function JobProgressProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<TrackedJob[]>(restoredJobs)
  const jobsRef = useRef(jobs)
  useEffect(() => {
    jobsRef.current = jobs
    sessionStorage.setItem(storageKey, JSON.stringify(jobs))
  }, [jobs])

  const updateJob = useCallback((id: string, patch: Partial<TrackedJob>) => {
    setJobs(previous => previous.map(job => {
      if (job.id !== id) return job
      const next = { ...job, ...patch }
      const becameFinished = !active(next) && active(job)
      if (becameFinished && !next.finishedAt) next.finishedAt = Date.now()
      if (!active(next) && !next.finishedAt) next.finishedAt = Date.now()
      return next
    }))
  }, [])
  const trackJob = useCallback((job: Pick<TrackedJob, 'id' | 'kind' | 'label' | 'projectId' | 'runId'>) => {
    setJobs(previous => previous.some(item => item.id === job.id) ? previous : [...previous, {
      ...job, status: 'queued', progress: 0, message: 'Wartet auf Verarbeitung'
    }])
  }, [])
  const dismissJob = useCallback((id: string) => setJobs(previous => previous.filter(job => job.id !== id)), [])
  const clearJobs = useCallback(() => setJobs([]), [])

  // Fertige Aktivitäten nach TTL entfernen
  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now()
      setJobs(previous => {
        const next = previous.filter(job => active(job) || !job.finishedAt || now - job.finishedAt < FINISHED_TTL_MS)
        return next.length === previous.length ? previous : next
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let stopped = false
    let polling = false
    const poll = async () => {
      if (polling) return
      polling = true
      try {
        for (const job of jobsRef.current.filter(active)) {
          try {
            const snapshot = await api<JobSnapshot>(`/jobs/${job.id}`)
            if (stopped) return
            if (snapshot.status === 'succeeded' && job.kind === 'analysis' && job.runId) {
              updateJob(job.id, { status: 'activating', progress: 99, message: 'Ergebnisse werden übernommen' })
              try {
                await api(`/analysis-runs/${job.runId}/activate`, { method: 'POST' })
              } catch (error) {
                const runs = await api<Array<{ id: string; status: string }>>(`/projects/${job.projectId}/analysis-runs`)
                if (!runs.some(run => run.id === job.runId && run.status === 'activated')) {
                  updateJob(job.id, { status: 'failed', message: `Analyse abgeschlossen, aber Aktivierung fehlgeschlagen: ${String(error)}`, finishedAt: Date.now() })
                  continue
                }
              }
              updateJob(job.id, { status: 'succeeded', progress: 100, message: 'Analyse abgeschlossen; Anforderungen sind bereit', finishedAt: Date.now() })
              window.dispatchEvent(new CustomEvent('kusys-job-finished', { detail: { projectId: job.projectId, kind: job.kind } }))
            } else if (snapshot.status === 'succeeded') {
              updateJob(job.id, { status: 'succeeded', progress: 100, message: snapshot.message || 'Verarbeitung abgeschlossen', finishedAt: Date.now() })
              window.dispatchEvent(new CustomEvent('kusys-job-finished', { detail: { projectId: job.projectId, kind: job.kind } }))
            } else if (snapshot.status === 'failed' || snapshot.status === 'cancelled' || snapshot.status === 'unknown') {
              updateJob(job.id, { status: snapshot.status === 'cancelled' ? 'cancelled' : 'failed', message: snapshot.message || snapshot.error_code || 'Verarbeitung fehlgeschlagen', finishedAt: Date.now() })
            } else {
              updateJob(job.id, {
                status: snapshot.status === 'running' ? 'running' : 'queued',
                progress: snapshot.progress ?? 0,
                message: snapshot.message || (snapshot.status === 'queued' ? 'Wartet auf freien Worker' : 'Wird verarbeitet')
              })
            }
          } catch (error) {
            if (!stopped) updateJob(job.id, { message: `Status vorübergehend nicht erreichbar: ${String(error)}` })
          }
        }
      } finally {
        polling = false
      }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 1500)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [updateJob])

  return <JobContext.Provider value={{ jobs, trackJob, dismissJob, clearJobs }}>
    {children}
    {jobs.length > 0 && <Box role="status" aria-live="polite" sx={{ position: 'fixed', right: 16, bottom: 16, width: 360, maxWidth: 'calc(100vw - 32px)', maxHeight: '60vh', overflowY: 'auto', zIndex: 1500 }}>
      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider', boxShadow: '0 16px 40px rgba(15,23,42,0.12)', borderRadius: 3 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 1 }}>Aktivitäten</Typography>
          <Stack spacing={1.5}>
            {jobs.map(job => <Box key={job.id} sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
              <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}><Typography sx={{ fontWeight: 600 }}>{job.label}</Typography>{!active(job) && <Button size="small" onClick={() => dismissJob(job.id)}>Schließen</Button>}</Stack>
              {job.status === 'failed' || job.status === 'cancelled' ? <Alert severity="error" sx={{ mt: 1 }}>{job.message}</Alert> : <Typography variant="body2" color="text.secondary">{job.status === 'queued' ? 'In Warteschlange · ' : ''}{job.message}</Typography>}
              {active(job) && <LinearProgress variant={job.status === 'running' && job.progress > 1 ? 'determinate' : 'indeterminate'} value={job.progress} sx={{ mt: 1, borderRadius: 1 }} />}
              {active(job) && job.status === 'running' && job.progress > 1 && <Typography variant="caption">{job.progress} %</Typography>}
              {job.status === 'succeeded' && <Typography variant="caption" color="success.main">Abgeschlossen · verschwindet gleich</Typography>}
            </Box>)}
          </Stack>
        </CardContent>
      </Card>
    </Box>}
  </JobContext.Provider>
}
