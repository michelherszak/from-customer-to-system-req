import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DndContext, DragEndEvent, useDraggable, useDroppable } from '@dnd-kit/core'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Container, CssBaseline, Dialog, DialogActions, LinearProgress,
  DialogContent, DialogTitle, FormControl, IconButton, InputLabel, MenuItem, Select, Stack,
  TextField, ThemeProvider, Typography, Table, TableBody, TableCell, TableHead, TableRow, Checkbox, Paper, createTheme
} from '@mui/material'
import { keyframes } from '@emotion/react'
import { api, artifactUrl, login, me, uploadDocument } from './api'
import { JobProgressProvider, useJobProgress } from './jobProgress'
import { EngineeringReview } from './EngineeringReview'
import { PlanningWorkspace as PlanningPage } from './PlanningWorkspace'
import { OffersWorkspace as OffersPage } from './OffersWorkspace'
import { AgentSettings } from './AgentSettings'
import { ProjectMembers } from './ProjectMembers'
import { DocumentPreparation } from './DocumentPreparation'

// KuSys visual language: ink for navigation and emphasis, paper for work surfaces,
// marker yellow for source highlights and the current step. Blue is reserved for primary actions.
const ink = { 900: '#15172E', 800: '#20234A', 700: '#262A52', 600: '#2B2F5C', line: '#3A3F72', soft: '#C9CCE3', muted: '#A4A9C9' }
const paper = { ground: '#F5F6F8', line: '#E2E4EB', lineStrong: '#D5D8E2', field: '#8A8FA3' }
const MARKER = '#FFE433'
const ACTION = '#2E3FE6'
const TEXT_MUTED = '#555A70'
const displayFont = '"Bricolage Grotesque", "Arial Narrow", system-ui, sans-serif'
const textFont = '"Instrument Sans", system-ui, -apple-system, "Segoe UI", sans-serif'
const serifFont = '"Source Serif 4", Georgia, serif'
// :where() keeps this at the specificity of the button's own styles, so sx and disabled styles still win.
const outlinedPrimary = '&:where(.MuiButton-outlined.MuiButton-colorPrimary)'

const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: 'light',
    primary: { main: ACTION, light: '#5866EC', dark: '#1B2AB8', contrastText: '#FFFFFF' },
    secondary: { main: ink[900], light: ink[600], dark: '#0C0D1C', contrastText: '#FFFFFF' },
    background: { default: paper.ground, paper: '#FFFFFF' },
    text: { primary: ink[900], secondary: TEXT_MUTED },
    divider: paper.line,
  },
  typography: {
    fontFamily: textFont,
    h4: { fontFamily: displayFont, fontWeight: 700, fontSize: '2.25rem', letterSpacing: '-0.02em', lineHeight: 1.1 },
    h5: { fontFamily: displayFont, fontWeight: 700, fontSize: '1.5rem', letterSpacing: '-0.015em', lineHeight: 1.2 },
    h6: { fontFamily: displayFont, fontWeight: 650, fontSize: '1.2rem', letterSpacing: '-0.01em', lineHeight: 1.3 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    overline: { textTransform: 'none', letterSpacing: 0, fontWeight: 600, fontSize: '0.8125rem', lineHeight: 1.5 },
    button: { textTransform: 'none', fontWeight: 600, letterSpacing: 0 },
    body2: { lineHeight: 1.55 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCssBaseline: { styleOverrides: {
      body: { backgroundColor: paper.ground, WebkitFontSmoothing: 'antialiased' },
      '::selection': { backgroundColor: MARKER, color: ink[900] },
      '*::-webkit-scrollbar': { width: 10, height: 10 },
      '*::-webkit-scrollbar-thumb': { backgroundColor: '#C5C8D6', border: `3px solid ${paper.ground}`, borderRadius: 8 },
      '@media (prefers-reduced-motion: reduce)': { '*, *::before, *::after': { animationDuration: '0.01ms !important', animationDelay: '0ms !important', transitionDuration: '0.01ms !important' } },
    } },
    MuiButtonBase: { styleOverrides: { root: { '&.Mui-focusVisible': { outline: `2px solid ${ACTION}`, outlineOffset: 2 } } } },
    MuiButton: { styleOverrides: {
      root: {
        borderRadius: 10, minHeight: 40, paddingInline: 16, transition: 'background-color 150ms ease, border-color 150ms ease, color 150ms ease',
        [outlinedPrimary]: { color: ink[900], borderColor: ink[900] },
        [`${outlinedPrimary}:hover`]: { borderColor: ink[900], backgroundColor: '#ECEEF6' },
      },
      sizeLarge: { minHeight: 48, fontSize: '1rem' },
      contained: { boxShadow: 'none', '&:hover': { boxShadow: 'none' } },
      outlined: { borderWidth: 1.5, '&:hover': { borderWidth: 1.5 } },
    } },
    MuiCard: { styleOverrides: { root: { border: `1px solid ${paper.line}`, borderRadius: 16, boxShadow: 'none' } } },
    MuiCardContent: { styleOverrides: { root: { padding: 24, '&:last-child': { paddingBottom: 24 } } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' }, elevation1: { boxShadow: 'none', border: `1px solid ${paper.line}` } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 8 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 48, color: TEXT_MUTED, '&.Mui-selected': { color: ink[900] } } } },
    MuiTabs: { styleOverrides: { indicator: { height: 3, borderRadius: 2, backgroundColor: ink[900] } } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 10, backgroundColor: '#FFFFFF', '& .MuiOutlinedInput-notchedOutline': { borderColor: paper.field }, '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: ink[900] }, '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: ACTION, borderWidth: 2 } } } },
    MuiTableCell: { styleOverrides: { head: { backgroundColor: '#FFFFFF', color: TEXT_MUTED, fontSize: '0.8125rem', fontWeight: 600 }, root: { borderColor: paper.line, fontVariantNumeric: 'tabular-nums' } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: 12 } } },
    MuiLinearProgress: { styleOverrides: { root: { borderRadius: 4 } } },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 18, boxShadow: '0 24px 72px rgba(21,23,46,0.22)' } } },
    MuiDialogTitle: { styleOverrides: { root: { fontFamily: displayFont, fontWeight: 700, fontSize: '1.375rem', letterSpacing: '-0.01em' } } },
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
const sidebarWidth = 264
const eur = (v: any) => v == null ? '–' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Number(v))

function ErrorBox({ error }: { error: unknown }) { return error ? <Alert severity="error" sx={{ my: 2 }}>{String((error as any)?.message ?? error)}</Alert> : null }
function Loading() { return <Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /><Typography sx={{ mt: 1 }}>Daten werden geladen…</Typography></Box> }

const markerSweep = keyframes`from { background-size: 0% 100%; } to { background-size: 100% 100%; }`

function Brand({ size = 28, label = 'KuSys' }: { size?: number; label?: string }) {
  return <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
    <Box aria-hidden="true" sx={{ width: size, height: size, flexShrink: 0, borderRadius: '8px', bgcolor: MARKER, color: ink[900], display: 'grid', placeItems: 'center', fontFamily: displayFont, fontWeight: 800, fontSize: size * 0.62, lineHeight: 1 }}>K</Box>
    <Box component="span" sx={{ fontFamily: displayFont, fontWeight: 700, fontSize: size * 0.72, letterSpacing: '-0.01em', lineHeight: 1.2 }}>{label}</Box>
  </Box>
}

type IconName = 'projects' | 'templates' | 'settings' | 'logout' | 'back'
const ICONS: Record<IconName, React.ReactNode> = {
  projects: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  templates: <><path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M14 3v5h5" /></>,
  settings: <><path d="M4 6h8" /><path d="M18 6h2" /><path d="M4 12h2" /><path d="M12 12h8" /><path d="M4 18h10" /><circle cx="15" cy="6" r="2.5" /><circle cx="9" cy="12" r="2.5" /><circle cx="17" cy="18" r="2.5" /></>,
  logout: <><path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" /><path d="M9 8l-4 4 4 4" /><path d="M5 12h10" /></>,
  back: <path d="M15 6l-6 6 6 6" />,
}
function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>{ICONS[name]}</svg>
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toUpperCase() ?? '').join('') || '?'
}

/** Marker highlight that sweeps in once on load (instant with reduced motion). */
function Highlight({ children, tone = 'marker', delay = 0 }: { children: React.ReactNode; tone?: 'marker' | 'open'; delay?: number }) {
  const color = tone === 'marker' ? MARKER : '#FFD3BD'
  return <Box component="mark" sx={{
    color: 'inherit', backgroundColor: 'transparent', backgroundImage: `linear-gradient(${color}, ${color})`, backgroundRepeat: 'no-repeat', backgroundSize: '100% 100%',
    boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone', px: '3px', borderRadius: '2px',
    animation: `${markerSweep} 650ms cubic-bezier(.3,.7,.2,1) ${delay}ms both`,
  }}>{children}</Box>
}

function LoginShowcase() {
  const rows: [string, string, string, boolean][] = [
    ['REQ-0001', 'Durchsatz 120 Packungen pro Minute', 'Muss', false],
    ['REQ-0003', 'Fernwartung mit Multi-Faktor-Authentifizierung', 'Muss', false],
    ['Klärung', 'Ausführung der kundenseitigen Firewall', 'offen', true],
  ]
  return <Box sx={{ display: 'flex', flexDirection: 'column', maxWidth: 600 }}>
    <Box sx={{ bgcolor: '#FFFFFF', color: ink[900], borderRadius: '6px', px: { xs: 2.5, sm: 3.75 }, pt: 3.25, pb: 5.75, mr: { sm: 7 }, fontFamily: serifFont, fontSize: 15, lineHeight: 1.75, transform: 'rotate(-1.2deg)', boxShadow: '0 24px 60px rgba(4,5,20,0.45)' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '4px 16px', mb: 1.25, fontFamily: textFont, fontSize: 12, lineHeight: 1.4, color: TEXT_MUTED }}>
        <span>Lastenheft_PX2400_v1.docx</span><span>Nordstern Verpackungstechnik GmbH</span>
      </Box>
      <Box component="p" sx={{ m: 0, mb: 0.75, fontWeight: 600, fontSize: 17, lineHeight: 1.4 }}>1. Zweck</Box>
      <Box component="p" sx={{ m: 0 }}>
        Die bestehende Verpackungslinie ist seit 2014 in Betrieb. <Highlight delay={500}>Das System muss 120 Packungen pro Minute verarbeiten.</Highlight> Das System soll eine REST-API zur Übergabe von Produktionsaufträgen bereitstellen. <Highlight delay={850}>Der Fernwartungszugang muss durch Multi-Faktor-Authentifizierung geschützt sein.</Highlight> <Highlight tone="open" delay={1200}>Die genaue Ausführung der kundenseitigen Firewall ist TBD.</Highlight>
      </Box>
    </Box>
    <Box sx={{ position: 'relative', alignSelf: 'flex-end', boxSizing: 'border-box', width: 'min(100%, 480px)', mt: '-28px', bgcolor: ink[700], border: `1px solid ${ink.line}`, borderRadius: '14px', px: 2, py: 0.5, fontSize: 14, lineHeight: 1.35, boxShadow: '0 16px 40px rgba(4,5,20,0.4)' }}>
      {rows.map(([key, title, status, open], index) => <Box key={key} sx={{ display: 'grid', gridTemplateColumns: '86px minmax(0, 1fr) auto', gap: 1.5, alignItems: 'center', py: 1.5, borderBottom: index < rows.length - 1 ? `1px solid ${ink.line}` : 'none' }}>
        <Box component="span" sx={{ color: open ? '#FFB995' : MARKER, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{key}</Box>
        <span>{title}</span>
        <Box component="span" sx={{ color: '#B9BDD8' }}>{status}</Box>
      </Box>)}
    </Box>
  </Box>
}

function LoginPage() {
  const nav = useNavigate(); const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const signIn = async (user: string, secret: string) => {
    setError(''); setBusy(true)
    try { await login(user, secret); const next = await me(); qc.setQueryData(['me'], next); nav('/') }
    catch (e: any) { setError(e.message) }
    finally { setBusy(false) }
  }
  const submit = (e: React.FormEvent) => { e.preventDefault(); void signIn(username.trim(), password) }
  return <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: { xs: 'column', md: 'row' }, bgcolor: 'background.default' }}>
    <Box component="main" sx={{ order: { xs: 1, md: 2 }, flex: { md: '1 1 0' }, minWidth: 0, px: { xs: 3, sm: 4 }, py: { xs: 5, md: 6 }, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <Box component="form" onSubmit={submit} sx={{ width: '100%', maxWidth: 380 }}>
        <Stack spacing={2.5}>
          <Box sx={{ display: { xs: 'block', md: 'none' } }}><Brand /></Box>
          <Typography variant="h4" component="h1">Anmelden</Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Benutzername" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" autoFocus disabled={busy} />
          <TextField type="password" label="Passwort" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" disabled={busy} />
          <Button type="submit" size="large" variant="contained" disabled={busy}>{busy ? 'Anmeldung läuft …' : 'Anmelden'}</Button>
          {DEMO_ENABLED && <>
            <Box aria-hidden="true" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, color: 'text.secondary', fontSize: '0.8125rem' }}>
              <Box sx={{ flex: 1, height: '1px', bgcolor: paper.lineStrong }} />oder<Box sx={{ flex: 1, height: '1px', bgcolor: paper.lineStrong }} />
            </Box>
            <Stack spacing={1}>
              <Button size="large" variant="outlined" disabled={busy} onClick={() => void signIn(DEMO_ACCOUNTS[0].username, DEMO_PASSWORD)}>Demo als Projektleitung öffnen</Button>
              <Typography variant="body2" color="text.secondary">Weitere Demo-Rollen wechselst du nach der Anmeldung in der Seitenleiste.</Typography>
            </Stack>
          </>}
          <Typography variant="body2" color="text.secondary" sx={{ pt: 2.5, borderTop: `1px solid ${paper.lineStrong}` }}>Noch kein Konto? Zugänge vergibt dein Firmen-Admin.</Typography>
        </Stack>
      </Box>
    </Box>
    <Box component="section" aria-label="Was KuSys macht" sx={{ order: { xs: 2, md: 1 }, flex: { md: '1.15 1 0' }, minWidth: 0, bgcolor: ink[900], color: '#FFFFFF', px: { xs: 3, sm: 6, lg: 7 }, py: { xs: 5, md: 6 }, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 5 }}>
      <Brand size={30} />
      <Stack spacing={2}>
        <Typography component="p" sx={{ fontFamily: displayFont, fontWeight: 700, fontSize: { xs: '2.25rem', lg: '3.25rem' }, lineHeight: 1.04, letterSpacing: '-0.02em', maxWidth: 600 }}>Jede Zahl im Angebot hat eine Fundstelle im Lastenheft.</Typography>
        <Typography sx={{ fontSize: '1.0625rem', lineHeight: 1.5, color: '#B9BDD8', maxWidth: 520 }}>KuSys macht aus Kundendokumenten prüfbare Anforderungen, Arbeitspakete, einen Terminplan und ein kalkuliertes Angebot.</Typography>
      </Stack>
      <LoginShowcase />
    </Box>
  </Box>
}

const DEMO_PASSWORD = 'KuSys-Demo-2026'
/** Demo shortcuts (login button, role switcher). Build with VITE_KUSYS_DEMO=false to hide them. */
const DEMO_ENABLED = import.meta.env.VITE_KUSYS_DEMO !== 'false'
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
    <FormControl size="small" fullWidth disabled={busy} sx={darkFieldSx}>
      <InputLabel id="demo-role-label">Demo-Rolle</InputLabel>
      <Select
        labelId="demo-role-label"
        label="Demo-Rolle"
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

const darkFieldSx = {
  '& .MuiInputLabel-root': { color: ink.soft },
  '& .MuiInputLabel-root.Mui-focused': { color: MARKER },
  '& .MuiOutlinedInput-root.MuiInputBase-root': { backgroundColor: 'transparent', color: '#FFFFFF' },
  '& .MuiOutlinedInput-root .MuiOutlinedInput-notchedOutline': { borderColor: '#6B70A0', borderStyle: 'dashed' },
  '& .MuiOutlinedInput-root:hover .MuiOutlinedInput-notchedOutline': { borderColor: ink.soft },
  '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: MARKER, borderStyle: 'solid' },
  '& .MuiSelect-icon': { color: ink.soft },
}

function SideLink({ to, active, icon, children }: { to: string; active?: boolean; icon?: IconName; children: React.ReactNode }) {
  return <Button component={Link} to={to} color="inherit" fullWidth aria-current={active ? 'page' : undefined} sx={{
    justifyContent: 'flex-start', textAlign: 'left', gap: 1.5, minHeight: 44, px: 1.5, py: 1, borderRadius: '10px', fontSize: '0.9375rem',
    fontWeight: active ? 600 : 500, color: active ? '#FFFFFF' : ink.soft, bgcolor: active ? ink[600] : 'transparent',
    '&:hover': { bgcolor: active ? ink[600] : ink[800], color: '#FFFFFF' }, '&.Mui-focusVisible': { outlineColor: MARKER },
  }}>{icon && <Icon name={icon} />}{children}</Button>
}

function UserBlock({ auth, roles, onLogout, divider = true }: { auth: any; roles: string; onLogout: () => Promise<void>; divider?: boolean }) {
  return <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 0.5, ...(divider ? { pt: 1.5, borderTop: `1px solid ${ink[600]}` } : {}) }}>
    <Box aria-hidden="true" sx={{ flex: '0 0 36px', height: 36, borderRadius: '50%', bgcolor: ink.line, color: '#FFFFFF', display: 'grid', placeItems: 'center', fontSize: '0.8125rem', fontWeight: 600 }}>{initials(auth.user.display_name ?? auth.user.username)}</Box>
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography noWrap sx={{ fontSize: '0.875rem', fontWeight: 600, lineHeight: 1.3, color: '#FFFFFF' }}>{auth.user.display_name}</Typography>
      <Typography noWrap title={roles} sx={{ fontSize: '0.75rem', lineHeight: 1.3, color: ink.muted }}>{roles}</Typography>
    </Box>
    <IconButton onClick={() => void onLogout()} aria-label="Abmelden" title="Abmelden" sx={{ width: 44, height: 44, borderRadius: '10px', color: ink.soft, '&:hover': { bgcolor: ink[800], color: '#FFFFFF' }, '&.Mui-focusVisible': { outlineColor: MARKER } }}><Icon name="logout" /></IconButton>
  </Box>
}

function Shell({ auth }: { auth: any }) {
  const loc = useLocation(); const nav = useNavigate(); const { clearJobs } = useJobProgress(); const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<any[]>('/projects') })
  const logout = async () => { await api('/auth/logout', { method: 'POST' }); sessionStorage.clear(); clearJobs(); await qc.cancelQueries(); qc.removeQueries({ predicate: query => query.queryKey[0] !== 'me' }); qc.setQueryData(['me'], null); nav('/login') }
  const roles = summarizeRoles(auth)
  const companyAdmin = (auth.tenant_roles ?? []).some((r: any) => r.role === 'company_admin')
  return <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, minHeight: '100vh', bgcolor: 'background.default' }}>
    <Box component="nav" aria-label="Hauptnavigation" sx={{
      width: { md: sidebarWidth }, flexShrink: 0, boxSizing: 'border-box', bgcolor: ink[900], color: '#FFFFFF',
      position: { md: 'sticky' }, top: 0, height: { md: '100vh' }, overflowY: { md: 'auto' },
      display: 'flex', flexDirection: 'column', gap: 3, px: 1.75, pt: 2.75, pb: 2,
    }}>
      <Box sx={{ px: 1.25 }}><Brand /></Box>
      <Stack spacing={0.25}>
        <SideLink to="/" icon="projects" active={loc.pathname === '/'}>Projekte</SideLink>
        <SideLink to="/admin/templates" icon="templates" active={loc.pathname.startsWith('/admin/templates')}>Vorlagen</SideLink>
        {companyAdmin && <SideLink to="/settings/agents" icon="settings" active={loc.pathname.startsWith('/settings')}>KI-Agenten</SideLink>}
      </Stack>
      {!!projects.data?.length && <Stack spacing={0.25} sx={{ display: { xs: 'none', md: 'flex' } }}>
        <Typography component="h2" sx={{ px: 1.5, pb: 0.75, fontSize: '0.8125rem', color: ink.muted }}>Zuletzt geöffnet</Typography>
        {projects.data.map(p => {
          const active = loc.pathname.includes(`/projects/${p.id}`)
          return <Button key={p.id} component={Link} to={`/projects/${p.id}/documents`} color="inherit" fullWidth aria-current={active ? 'page' : undefined} sx={{
            flexDirection: 'column', alignItems: 'flex-start', textAlign: 'left', gap: 0.25, px: 1.5, py: 1, borderRadius: '10px',
            bgcolor: active ? ink[600] : 'transparent', '&:hover': { bgcolor: active ? ink[600] : ink[800] }, '&.Mui-focusVisible': { outlineColor: MARKER },
          }}>
            <Box component="span" sx={{ fontSize: '0.75rem', fontWeight: 500, color: active ? '#B9BDD8' : ink.muted, fontVariantNumeric: 'tabular-nums' }}>{p.project_number}</Box>
            <Box component="span" sx={{ fontSize: '0.875rem', fontWeight: active ? 600 : 500, lineHeight: 1.3, color: '#FFFFFF' }}>{p.name}</Box>
          </Button>
        })}
      </Stack>}
      <Stack spacing={1.5} sx={{ mt: { md: 'auto' } }}>
        {DEMO_ENABLED && <DemoRoleSwitcher auth={auth} />}
        <UserBlock auth={auth} roles={roles} onLogout={logout} />
      </Stack>
    </Box>
    <Box component="main" sx={{ flexGrow: 1, minWidth: 0, px: { xs: 2, sm: 3, lg: 6 }, py: { xs: 3, lg: 5 } }}>
      <Routes>
        <Route path="/" element={<ProjectsPage />} /><Route path="/projects/:projectId/*" element={<ProjectWorkspace />} /><Route path="/admin/templates" element={<TemplatesPage />} /><Route path="/settings/agents" element={<AgentSettings />} /><Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Box>
  </Box>
}

const workflowSteps = ['Dokument', 'Prüfschritt', 'Anforderungen', 'Planung', 'Sachpositionen', 'Angebot']

function ProjectProgressCard({ project, canDelete, onDelete }: { project: any; canDelete: boolean; onDelete: () => void }) {
  const client = useQueryClient()
  const statusChange = useMutation({
    mutationFn: () => api(`/projects/${project.id}`, { method: 'PATCH', body: JSON.stringify({ expected_version: project.lock_version, status: project.status === 'inactive' ? 'active' : 'inactive' }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['projects'] }),
  })
  const docs = useQuery({ queryKey: ['docs', project.id], queryFn: () => api<any[]>(`/projects/${project.id}/documents`) })
  const review = useQuery({ queryKey: ['review', project.id], queryFn: () => api<any>(`/projects/${project.id}/review`) })
  const requirements = useQuery({ queryKey: ['requirements', project.id], queryFn: () => api<any[]>(`/projects/${project.id}/requirements`) })
  const packages = useQuery({ queryKey: ['workpackages', project.id], queryFn: () => api<any[]>(`/projects/${project.id}/work-packages`) })
  const materials = useQuery({ queryKey: ['materials', project.id], queryFn: () => api<any[]>(`/projects/${project.id}/materials`) })
  const offers = useQuery({ queryKey: ['offers', project.id], queryFn: () => api<any[]>(`/projects/${project.id}/offers`) })
  const docsReady = !!docs.data?.some((d: any) => d.versions?.some((v: any) => v.status === 'ready'))
  const hasRequirements = !!requirements.data?.length
  const hasPackages = !!packages.data?.length
  const latestOffer = offers.data?.flatMap((offer: any) => offer.versions ?? []).sort((a: any, b: any) => b.version - a.version)[0]
  const offerApproved = latestOffer?.status === 'freigegeben'
  const completed = [docsReady, review.data?.review?.status === 'approved', hasRequirements, hasPackages, !!materials.data?.length || offerApproved, offerApproved]
  const nextStep = completed.findIndex(done => !done)
  const progress = completed.filter(Boolean).length
  const pending = [docs, review, requirements, packages, materials, offers].some(query => query.isLoading)
  return <Card sx={{ overflow: 'hidden', height: '100%', transition: 'transform 160ms ease, box-shadow 160ms ease', '&:hover': { transform: 'translateY(-2px)', boxShadow: '0 12px 32px rgba(21,23,46,0.09)' } }}>
    <CardContent sx={{ p: { xs: 2.5, sm: 3 }, '&:last-child': { pb: { xs: 2.5, sm: 3 } } }}>
      <Stack spacing={2.25}>
        <Stack direction="row" spacing={2} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="overline" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>{project.project_number}</Typography>
            <Typography component="h2" variant="h6" sx={{ mt: 0.25 }}>{project.name}</Typography>
            {project.short_description && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{project.short_description}</Typography>}
          </Box>
          <Stack direction="row" spacing={0.75} sx={{ flexShrink: 0 }}>
            <Chip size="small" label={project.status === 'inactive' ? 'inaktiv' : 'aktiv'} sx={{ bgcolor: '#ECEEF6', color: ink[900] }} />
            {offerApproved && <Chip size="small" color="success" label="freigegeben" title="Das Angebot wurde im Vier-Augen-Prinzip freigegeben." />}
          </Stack>
        </Stack>
        <Box>
          <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.75 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>{pending ? 'Fortschritt wird geladen …' : `${progress} von 6 Schritten`}</Typography>
            {!offerApproved && <Typography variant="caption" color="text.secondary">{pending ? '—' : `${Math.round(progress / 6 * 100)}%`}</Typography>}
          </Stack>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 0.6 }} aria-label={`Projektfortschritt: ${progress} von 6 Schritten`}>
            {workflowSteps.map((step, i) => <Box key={step} title={step} sx={{ height: 6, borderRadius: 4, bgcolor: completed[i] ? ink[900] : i === nextStep ? MARKER : '#E6E8EF' }} />)}
          </Box>
          <Stack direction="row" spacing={0.5} sx={{ mt: 0.8, justifyContent: 'space-between' }}>
            {workflowSteps.map((step, i) => <Typography key={step} variant="caption" sx={{ color: i === nextStep ? ink[900] : 'text.secondary', fontWeight: i === nextStep ? 700 : 400, fontSize: { xs: '0.6rem', sm: '0.68rem' }, textAlign: 'center', flex: 1 }}>{step}</Typography>)}
          </Stack>
        </Box>
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 1, pt: 0.5, borderTop: `1px solid ${paper.line}` }}>
          <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }} noWrap>
            {latestOffer?.net_eur != null ? `Angebot · ${eur(latestOffer.net_eur)} netto` : hasRequirements ? `${requirements.data?.length} Anforderungen · ${packages.data?.length ?? 0} Arbeitspakete` : 'Noch keine Anforderungen'}
          </Typography>
          <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
            {canDelete && <Button color="error" onClick={onDelete} aria-label={`Projekt ${project.project_number} löschen`}>Löschen</Button>}
            {canDelete && <Button disabled={statusChange.isPending} onClick={() => statusChange.mutate()}>{statusChange.isPending ? '…' : project.status === 'inactive' ? 'Aktivieren' : 'Inaktiv stellen'}</Button>}
            {offerApproved && <Button component={Link} to={`/projects/${project.id}/offers`}>Angebot öffnen</Button>}
            <Button component={Link} to={`/projects/${project.id}/documents`} variant="contained">Öffnen</Button>
          </Stack>
        </Stack>
        {statusChange.isError && <Alert severity="error">Projektstatus konnte nicht geändert werden: {String(statusChange.error)}</Alert>}
      </Stack>
    </CardContent>
  </Card>
}

function ProjectsPage() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['projects'], queryFn: () => api<any[]>('/projects') })
  const auth = useQuery({ queryKey: ['me'], queryFn: me })
  const options = useQuery({ queryKey: ['project-creation-options'], queryFn: () => api<any[]>('/project-creation-options') })
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({tenant_id:'',project_number:'',name:'',short_description:''})
  const create = useMutation({
    mutationFn: () => api<any>('/projects', {method:'POST',body:JSON.stringify({...draft,tenant_id:draft.tenant_id || options.data?.[0]?.id})}),
    onSuccess: async project => {
      setCreating(false)
      await Promise.all([client.invalidateQueries({queryKey:['projects']}),client.invalidateQueries({queryKey:['me']})])
      navigate(`/projects/${project.id}/documents`)
    },
  })
  const [deleting, setDeleting] = useState<any>(null)
  const [reason, setReason] = useState('')
  const canDelete = (project: any) => (auth.data?.tenant_roles ?? []).some((role: any) => role.tenant_id === project.tenant_id && role.role === 'company_admin') || (auth.data?.project_roles ?? []).some((role: any) => role.project_id === project.id && role.role === 'project_lead')
  const remove = useMutation({
    mutationFn: () => api(`/projects/${deleting.id}?reason=${encodeURIComponent(reason.trim() || 'Auf Wunsch der Projektverantwortlichen gelöscht')}`, { method: 'DELETE' }),
    onSuccess: async () => {
      const id = deleting.id
      setDeleting(null); setReason('')
      client.removeQueries({ predicate: query => query.queryKey.includes(id) })
      await client.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const openDelete = (project: any) => { remove.reset(); setReason(''); setDeleting(project) }
  if (q.isLoading) return <Loading />
  const count = q.data?.length ?? 0
  const activeCount = q.data?.filter(project => project.status !== 'inactive').length ?? 0
  const inactiveCount = count - activeCount
  return <Container maxWidth="lg" disableGutters>
    <Stack direction="row" sx={{alignItems:'flex-end',justifyContent:'space-between',flexWrap:'wrap',mb:3.5,gap:2}}>
      <Box>
        <Typography variant="h4" component="h1" sx={{ fontSize: { xs: '2.25rem', md: '2.75rem' }, mb: 1 }}>Projekte</Typography>
        <Typography color="text.secondary">{activeCount === 1 ? '1 aktives Vorhaben' : `${activeCount} aktive Vorhaben`}{inactiveCount > 0 ? ` · ${inactiveCount} inaktiv` : ''}</Typography>
      </Box>
      {!!options.data?.length && <Button variant="contained" size="large" onClick={() => {create.reset();setDraft({tenant_id:options.data![0].id,project_number:'',name:'',short_description:''});setCreating(true)}}>Neues Projekt</Button>}
    </Stack>
    <ErrorBox error={q.error || options.error} />
    {count > 0 && <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'repeat(2, minmax(0, 1fr))' }, gap: 2 }}>{q.data?.map(p => <ProjectProgressCard key={p.id} project={p} canDelete={canDelete(p)} onDelete={() => openDelete(p)} />)}</Box>}
    {q.isSuccess && count === 0 && <Paper sx={{ borderRadius: '16px', px: 3.5, py: 5, textAlign: 'center' }}>
      <Typography sx={{ fontWeight: 600 }}>Noch keine aktiven Projekte</Typography>
      <Typography color="text.secondary" sx={{ mt: 0.5 }}>{options.data?.length ? 'Lege mit „Neues Projekt“ das erste Vorhaben an.' : 'Sobald du einem Projekt zugeordnet wirst, erscheint es hier.'}</Typography>
    </Paper>}
    <Dialog open={creating} onClose={() => {if(!create.isPending)setCreating(false)}} maxWidth="sm" fullWidth>
      <Box component="form" onSubmit={(event:React.FormEvent) => {event.preventDefault();if(!create.isPending)create.mutate()}}>
        <DialogTitle>Neues Projekt</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{pt:1}}>
          {(options.data?.length??0)>1 && <TextField select label="Firma" value={draft.tenant_id} onChange={e=>setDraft({...draft,tenant_id:e.target.value})} disabled={create.isPending} required>{options.data?.map(t=><MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}</TextField>}
          {(options.data?.length??0)===1 && <Typography color="text.secondary">Firma: {options.data?.[0].name}</Typography>}
          <TextField label="Projektnummer" placeholder="PRJ-2026-0002" value={draft.project_number} onChange={e=>setDraft({...draft,project_number:e.target.value})} slotProps={{htmlInput:{maxLength:80}}} required disabled={create.isPending}/>
          <TextField label="Projektname" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} slotProps={{htmlInput:{maxLength:240}}} required disabled={create.isPending}/>
          <TextField label="Kurzbeschreibung (optional)" value={draft.short_description} onChange={e=>setDraft({...draft,short_description:e.target.value})} multiline minRows={2} disabled={create.isPending}/>
          <Typography variant="body2" color="text.secondary">Du wirst automatisch als Projektleitung eingetragen.</Typography>
          <ErrorBox error={create.error}/>
        </Stack></DialogContent>
        <DialogActions><Button onClick={()=>setCreating(false)} disabled={create.isPending}>Abbrechen</Button><Button type="submit" variant="contained" disabled={create.isPending||!draft.project_number.trim()||!draft.name.trim()}>{create.isPending?'Wird erstellt …':'Projekt erstellen'}</Button></DialogActions>
      </Box>
    </Dialog>
    <Dialog open={!!deleting} onClose={() => { if (!remove.isPending) setDeleting(null) }} maxWidth="sm" fullWidth>
      <DialogTitle>Projekt löschen?</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{pt:1}}>
        <Typography><strong>{deleting?.project_number} · {deleting?.name}</strong></Typography>
        <Typography>Das Projekt wird aus der aktiven Projektübersicht entfernt. Zugehörige Daten und Dokumente bleiben für die Nachvollziehbarkeit gespeichert.</Typography>
        <TextField label="Löschgrund (optional)" value={reason} onChange={event => setReason(event.target.value)} disabled={remove.isPending} slotProps={{htmlInput:{maxLength:500}}} fullWidth multiline minRows={2}/>
        <ErrorBox error={remove.error}/>
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setDeleting(null)} disabled={remove.isPending}>Abbrechen</Button><Button color="error" variant="contained" onClick={() => remove.mutate()} disabled={remove.isPending}>{remove.isPending ? 'Wird gelöscht …' : 'Projekt löschen'}</Button></DialogActions>
    </Dialog>
  </Container>
}

function ProjectWorkspace() {
  const { projectId = '' } = useParams(); const loc = useLocation(); const navigate = useNavigate(); const p = useQuery({ queryKey: ['project', projectId], queryFn: () => api<any>(`/projects/${projectId}`) })
  const steps = [
    { key: 'documents', label: 'Dokumente' }, { key: 'review', label: 'Prüfschritt' }, { key: 'requirements', label: 'Anforderungen' },
    { key: 'planning', label: 'Planung' }, { key: 'commercial', label: 'Sachpositionen' }, { key: 'offers', label: 'Angebote' },
  ]
  const tabs = [...steps.map(step => step.key), 'audit']
  const current = tabs.find(x => loc.pathname.includes(`/${x}`)) ?? 'documents'
  const offers = useQuery({ queryKey: ['offers', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/offers`), enabled: p.isSuccess && current === 'offers' })
  const offerVersions = offers.data?.flatMap(offer => offer.versions.map((version:any) => ({...version, offer_number:offer.offer_number, variant_name:offer.variant_name}))) ?? []
  const selectedOfferId = new URLSearchParams(loc.search).get('offer') || offerVersions[0]?.id || ''
  if (p.isLoading) return <Loading />
  if (p.isError) return <Alert severity="error">Projekt konnte nicht geöffnet werden: {String(p.error)}<Box sx={{mt:1}}><Button component={Link} to="/">Zur Projektübersicht</Button></Box></Alert>
  return <Container maxWidth="xl" disableGutters>
    <Button component={Link} to="/" size="small" startIcon={<Icon name="back" size={16} />} sx={{ mb: 1.5, ml: -1 }}>Projekte</Button>
    <Box sx={{ mb: 2.5, minWidth: 0 }}>
      <Typography color="text.secondary" sx={{ fontSize: '0.875rem', fontVariantNumeric: 'tabular-nums', mb: 0.75 }}>{p.data?.project_number}{p.data?.customer_contact ? `, Kontakt: ${p.data.customer_contact}` : ''}</Typography>
      <Typography variant="h4" component="h1">{p.data?.name}</Typography>
    </Box>
    <ProjectMembers projectId={projectId} tenantId={p.data.tenant_id}/>
    <Box component="nav" aria-label="Projektschritte" sx={{ position: 'sticky', top: { xs: 8, md: 20 }, zIndex: 10, display: 'flex', alignItems: 'center', gap: 0.5, bgcolor: '#FFFFFF', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', px: { xs: 2, sm: 3, lg: 6 }, py: 1, mx: { xs: -2, sm: -3, lg: -6 }, width: { xs: 'calc(100% + 32px)', sm: 'calc(100% + 48px)', lg: 'calc(100% + 96px)' }, mb: 3, overflowX: 'auto', boxShadow: '0 10px 28px rgba(21,23,46,0.10)' }}>
      {steps.map((step, index) => {
        const active = current === step.key
        return <Button key={step.key} component={Link} to={`/projects/${projectId}/${step.key}`} color="inherit" aria-current={active ? 'page' : undefined} sx={{
          flexShrink: 0, gap: 1.1, minHeight: 44, pl: 1, pr: 2, borderRadius: '10px', fontSize: '0.875rem', fontWeight: active ? 600 : 500,
          color: active ? '#FFFFFF' : 'text.secondary', bgcolor: active ? ink[900] : 'transparent',
          '&:hover': { bgcolor: active ? ink[900] : '#EEF0F6', color: active ? '#FFFFFF' : 'text.primary' },
        }}>
          <Box component="span" aria-hidden="true" sx={{ width: 28, height: 28, boxSizing: 'border-box', borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: '0.8125rem', fontWeight: 700, bgcolor: active ? MARKER : 'transparent', color: active ? ink[900] : 'inherit', border: active ? 'none' : `1.5px solid ${paper.field}` }}>{index + 1}</Box>
          {step.label}
        </Button>
      })}
      {current === 'offers' && !!offerVersions.length && <TextField select size="small" label="Angebot" value={selectedOfferId} onChange={event => navigate(`/projects/${projectId}/offers?offer=${encodeURIComponent(event.target.value)}`)} sx={{ flexShrink: 0, minWidth: { xs: 230, md: 300 }, ml: { md: 1 }, '& .MuiOutlinedInput-root': { bgcolor: '#F7F8FC' } }}>
        {offerVersions.map(version => <MenuItem key={version.id} value={version.id}>{version.offer_number} · {version.variant_name} · V{version.version} · {version.status}</MenuItem>)}
      </TextField>}
      <Button component={Link} to={`/projects/${projectId}/audit`} color="inherit" aria-current={current === 'audit' ? 'page' : undefined} sx={{
        flexShrink: 0, ml: 'auto', minHeight: 44, px: 2, borderRadius: '10px', fontSize: '0.875rem', fontWeight: current === 'audit' ? 600 : 500,
        color: current === 'audit' ? '#FFFFFF' : 'text.secondary', bgcolor: current === 'audit' ? ink[900] : 'transparent',
        '&:hover': { bgcolor: current === 'audit' ? ink[900] : '#EEF0F6', color: current === 'audit' ? '#FFFFFF' : 'text.primary' },
      }}>Audit</Button>
    </Box>
    <Routes><Route path="documents" element={<DocumentsPage projectId={projectId} />} /><Route path="review" element={<ReviewPage projectId={projectId} />} /><Route path="requirements" element={<RequirementsPage projectId={projectId} />} /><Route path="planning" element={<PlanningPage projectId={projectId} />} /><Route path="commercial" element={<CommercialPage projectId={projectId} />} /><Route path="offers" element={<OffersPage projectId={projectId} />} /><Route path="audit" element={<AuditPage projectId={projectId} />} /><Route path="*" element={<Navigate to="documents" replace />} /></Routes>
  </Container>
}

function DocumentsPage({ projectId }: { projectId: string }) {
  const navigate = useNavigate()
  const client = useQueryClient(); const { trackJob } = useJobProgress(); const auth = useQuery({ queryKey: ['me'], queryFn: me })
  const q = useQuery({ queryKey: ['docs', projectId], queryFn: () => api<any[]>(`/projects/${projectId}/documents`) }); const [file, setFile] = useState<File | null>(null); const [uploadPercent, setUploadPercent] = useState<number | null>(null)
  const canDelete = isProjectLead(auth.data, projectId)
  const upload = useMutation({ mutationFn: () => uploadDocument(projectId, file!, setUploadPercent), onSuccess: data => { trackJob({ id: data.job_id, kind: 'document_extract', label: data.version.filename, projectId }); setFile(null); setUploadPercent(null); client.invalidateQueries({ queryKey: ['docs', projectId] }) }, onError: () => setUploadPercent(null) })
  const openReview = useMutation({
    mutationFn: async () => {
      const current = await api<any>(`/projects/${projectId}/review`)
      if (current.review) return
      const documents = await api<any[]>(`/projects/${projectId}/documents`)
      if (!documents.some(document => document.versions.some((version: any) => version.status === 'ready'))) {
        throw new Error('Bitte zuerst ein Dokument hochladen und die Extraktion abwarten.')
      }
      await api(`/projects/${projectId}/review/rebuild`, { method: 'POST', body: JSON.stringify({ source_selection: {} }) })
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['review', projectId] })
      navigate(`/projects/${projectId}/review`)
    },
  })
  const remove = useMutation({
    mutationFn: (documentId: string) => api(`/documents/${documentId}?reason=${encodeURIComponent('Über UI gelöscht')}`, { method: 'DELETE' }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['docs', projectId] }); void client.invalidateQueries({ queryKey: ['review', projectId] }) },
  })
  return <Stack spacing={2}><Card><CardContent><Typography variant="h6">Kundendokument hochladen</Typography><Stack direction={{xs:'column',md:'row'}} spacing={2} sx={{ mt: 2 }}><Button component="label" variant="outlined">Datei wählen<input hidden type="file" accept=".pdf,.docx,.png" onChange={e => setFile(e.target.files?.[0] ?? null)} /></Button><Typography sx={{ alignSelf:'center' }}>{file?.name ?? 'PDF, DOCX oder PNG'}</Typography><Button variant="contained" disabled={!file || upload.isPending} onClick={() => { setUploadPercent(0); upload.mutate() }}>{upload.isPending ? 'Upload läuft…' : 'Hochladen & extrahieren'}</Button><Button variant="contained" color="secondary" disabled={openReview.isPending} onClick={() => openReview.mutate()}>{openReview.isPending ? 'Prüfschritt wird geöffnet…' : 'Zum Prüfschritt'}</Button></Stack>{upload.isPending && <Box sx={{ mt: 2 }}><Typography variant="body2">{uploadPercent === null ? 'Upload wird vorbereitet…' : uploadPercent < 100 ? `Datei wird übertragen: ${uploadPercent} %` : 'Datei übertragen; Server bestätigt den Auftrag…'}</Typography><LinearProgress variant={uploadPercent === null ? 'indeterminate' : 'determinate'} value={uploadPercent ?? 0} sx={{ mt: 1 }} /></Box>}{openReview.isPending && <Box sx={{ mt: 2 }}><Typography variant="body2">Prüfschritt wird vorbereitet und geöffnet…</Typography><LinearProgress sx={{ mt: 1 }} /></Box>}<ErrorBox error={upload.error || openReview.error || remove.error} /></CardContent></Card>
    <DocumentPreparation projectId={projectId} documents={q.data ?? []}/>
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
  const location=useLocation(); const [highlightedSection,setHighlightedSection]=useState('')
  const options=useQuery({queryKey:['analysis-options',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/analysis-options`)})
  const provider=options.data?.[0]
  const client=useQueryClient(); const { jobs, trackJob }=useJobProgress(); const analysisRunning=jobs.some(job=>job.kind==='analysis' && job.projectId===projectId && ['queued','running','activating'].includes(job.status)); const q=useQuery({queryKey:['review',projectId],queryFn:()=>api<any>(`/projects/${projectId}/review`)})
  const approve=useMutation({mutationFn:()=>api(`/review-revisions/${q.data.review.id}/approve`,{method:'POST'}),onSuccess:()=>client.invalidateQueries({queryKey:['review',projectId]})})
  const analyze=useMutation({mutationFn:()=>api<any>(`/projects/${projectId}/analysis-runs`,{method:'POST',body:JSON.stringify({provider_config_id:provider?.id,model_id:provider?.models[0]})}),onSuccess:data=>trackJob({id:data.job_id,kind:'analysis',label:'Anforderungsanalyse',projectId,runId:data.analysis_run.id})})
  useEffect(()=>{const sectionId=location.hash.startsWith('#section-')?decodeURIComponent(location.hash.slice('#section-'.length)):'';if(!sectionId||!q.data?.sections?.some((section:any)=>section.id===sectionId))return;setHighlightedSection(sectionId);const scrollTimer=window.setTimeout(()=>document.getElementById(`section-${sectionId}`)?.scrollIntoView({behavior:'smooth',block:'center'}),100);const clearTimer=window.setTimeout(()=>setHighlightedSection(current=>current===sectionId?'':current),7000);return()=>{window.clearTimeout(scrollTimer);window.clearTimeout(clearTimer)}},[location.hash,q.data?.sections])
  if(q.isLoading)return <Loading/>; if(!q.data?.review)return <Alert severity="info">Noch kein Prüfschritt. Bitte unter „Dokumente“ auf „Zum Prüfschritt“ klicken.</Alert>
  const update=async(s:any,patch:any)=>{await api(`/review-revisions/${q.data.review.id}/sections/${s.id}`,{method:'PATCH',body:JSON.stringify({expected_version:s.lock_version,...patch})});await client.invalidateQueries({queryKey:['review',projectId]})}
  return <Stack spacing={2}><Card><CardContent>
    <Stack direction={{xs:'column',md:'row'}} sx={{justifyContent:'space-between',alignItems:{xs:'flex-start',md:'center'},gap:2}}>
      <Typography variant="h6">Prüfschritt Revision {q.data.review.revision_no}</Typography>
      <Stack direction="row" sx={{alignItems:'center',gap:1,flexWrap:'wrap'}}>
        <Chip label={q.data.review.status} color={q.data.review.status==='approved'?'success':'warning'} />
        <Button variant="outlined" onClick={()=>approve.mutate()} disabled={q.data.review.status==='approved'||approve.isPending}>Freigeben</Button>
        <Button variant="contained" onClick={()=>analyze.mutate()} disabled={!provider||q.data.review.status!=='approved'||analyze.isPending||analysisRunning}>{analyze.isPending||analysisRunning?'Analyse läuft…':'Engineering-Analyse starten'}</Button>
      </Stack>
    </Stack>
    {!options.isPending&&!options.isError&&!provider&&<Alert severity="warning" sx={{mt:2}}>Bitte ein Cloud-Modell unter Einstellungen · Agenten konfigurieren.</Alert>}
    <ErrorBox error={approve.error||analyze.error||options.error}/>
    {analysisRunning&&<Alert severity="info" sx={{mt:2}}>Die Analyse läuft. Den Fortschritt siehst Du unter „Aktivitäten“.</Alert>}
  </CardContent></Card>
  <Paper><Table size="small"><TableHead><TableRow><TableCell>#</TableCell><TableCell>Typ</TableCell><TableCell>Text</TableCell><TableCell>Kategorie</TableCell><TableCell>Ausgeschlossen</TableCell></TableRow></TableHead><TableBody>{q.data.sections.map((s:any)=>{const highlighted=highlightedSection===s.id;return <TableRow id={`section-${s.id}`} key={s.id} sx={{opacity:s.excluded?.5:1,scrollMarginTop:120,transition:'background-color 250ms ease',...(highlighted?{'& > td':{backgroundColor:'#FFF6B8 !important',borderTop:`2px solid ${ink[900]}`,borderBottom:`2px solid ${ink[900]}`},'& > td:first-of-type':{borderLeft:`6px solid ${MARKER}`,fontWeight:700},'& > td:last-of-type':{borderRight:`2px solid ${ink[900]}`}}:{})}}><TableCell>{s.order_index+1}{highlighted&&<Chip size="small" label="Fundstelle" sx={{ml:1,fontWeight:700,bgcolor:ink[900],color:MARKER}}/>}</TableCell><TableCell>{s.section_type}</TableCell><TableCell sx={{minWidth:500}}><TextField size="small" fullWidth multiline value={s.edited_text} onChange={()=>{}} onBlur={e=>{if(e.target.value!==s.edited_text)update(s,{edited_text:e.target.value})}} sx={highlighted?{bgcolor:'#FFFFFF',boxShadow:`0 0 0 3px ${MARKER}`,borderRadius:'10px'}:undefined}/></TableCell><TableCell><Select size="small" value={s.category} onChange={e=>update(s,{category:e.target.value})}><MenuItem value="requirement">Anforderung</MenuItem><MenuItem value="context">Kontext</MenuItem></Select></TableCell><TableCell><Checkbox checked={s.excluded} onChange={e=>update(s,{excluded:e.target.checked})}/></TableCell></TableRow>})}</TableBody></Table></Paper></Stack>
}

function RequirementsPage({projectId}:{projectId:string}){
  const client=useQueryClient();const q=useQuery({queryKey:['requirements',projectId],queryFn:()=>api<any[]>(`/projects/${projectId}/requirements`)});const review=useQuery({queryKey:['review',projectId],queryFn:()=>api<any>(`/projects/${projectId}/review`)});const [impact,setImpact]=useState<any>(null);const [focusedId,setFocusedId]=useState<string|null>(null);const [selected,setSelected]=useState<any>(null)
  const [createOpen,setCreateOpen]=useState(false);const [createDraft,setCreateDraft]=useState({title:'',text:'',priority:'soll'});const [splitSource,setSplitSource]=useState<any>(null);const [splitParts,setSplitParts]=useState([{title:'',text:'',priority:'soll'},{title:'',text:'',priority:'soll'}])
  const create=useMutation({mutationFn:()=>api(`/projects/${projectId}/requirements`,{method:'POST',body:JSON.stringify({...createDraft,budget_source:'manual'})}),onSuccess:()=>{setCreateOpen(false);setCreateDraft({title:'',text:'',priority:'soll'});void client.invalidateQueries({queryKey:['requirements',projectId]})}})
  const split=useMutation({mutationFn:()=>api(`/requirements/${splitSource.id}/split`,{method:'POST',body:JSON.stringify({expected_version:splitSource.lock_version,parts:splitParts})}),onSuccess:()=>{setSplitSource(null);void client.invalidateQueries({queryKey:['requirements',projectId]})}})
  if(q.isLoading)return <Loading/>;const focused=q.data?.find(r=>r.id===focusedId)??q.data?.[0];const sourceRefs=Array.isArray(focused?.source_refs)?focused.source_refs:[];const sections=review.data?.sections??[];const sourceSections=sourceRefs.map((ref:any)=>({ref,section:sections.find((s:any)=>String(s.id)===String(ref.section_id))}));return <Stack spacing={2}><EngineeringReview projectId={projectId}/><Stack direction={{xs:'column',sm:'row'}} spacing={1} sx={{alignItems:{sm:'center'}}}><Box sx={{flex:1}}><Typography variant="h6">Anforderungen im Projekt</Typography><Typography variant="body2" color="text.secondary">Quelle, Ableitung und Auswirkung direkt im Zusammenhang prüfen.</Typography></Box><Button variant="contained" onClick={()=>setCreateOpen(true)}>Anforderung hinzufügen</Button></Stack><Box sx={{display:'grid',gridTemplateColumns:{xs:'minmax(0,1fr)',xl:'minmax(0,1.8fr) minmax(300px,0.8fr)'},alignItems:'start',gap:2}}><Paper sx={{overflowX:'auto',minWidth:0}}><Table size="small"><TableHead><TableRow><TableCell>ID</TableCell><TableCell>Anforderung</TableCell><TableCell>Prio.</TableCell><TableCell>Budget</TableCell><TableCell>Aktionen</TableCell></TableRow></TableHead><TableBody>{q.data?.map(r=><TableRow key={r.id} hover selected={focused?.id===r.id} onClick={()=>{setFocusedId(r.id);setImpact(null)}} sx={{opacity:r.replacement_status?0.68:1,cursor:'pointer',...(focused?.id===r.id?{'& > td':{bgcolor:'#FFF9D6'},'& > td:first-of-type':{borderLeft:`4px solid ${MARKER}`}}:{})}}><TableCell sx={{fontWeight:700,whiteSpace:'nowrap'}}>{r.key}</TableCell><TableCell sx={{minWidth:240}}><Stack spacing={0.5}><Typography variant="body2" sx={{fontWeight:600}}>{r.title}</Typography><Typography variant="caption" color="text.secondary" sx={{display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{r.text}</Typography>{r.replacement_status&&<Chip size="small" sx={{alignSelf:'flex-start'}} label={r.replacement_status} />}{r.relations?.some((x:any)=>x.relation_type==='split_from')&&<Typography variant="caption" color="text.secondary">Aufgegliedert aus {r.relations.filter((x:any)=>x.relation_type==='split_from').map((x:any)=>q.data?.find(parent=>parent.id===x.target_id)?.key).filter(Boolean).join(', ')}</Typography>}</Stack></TableCell><TableCell>{r.priority}</TableCell><TableCell sx={{whiteSpace:'nowrap'}}>{eur(r.budget_eur)}</TableCell><TableCell onClick={e=>e.stopPropagation()}><Stack direction={{xs:'column',sm:'row'}} spacing={0.25}><Button size="small" onClick={()=>setSelected(r)}>Bearbeiten</Button>{!r.replacement_status&&<Button size="small" onClick={()=>{setSplitSource(r);setSplitParts([{title:'',text:'',priority:r.priority??'soll'},{title:'',text:'',priority:r.priority??'soll'}])}}>Aufgliedern</Button>}</Stack></TableCell></TableRow>)}</TableBody></Table>{!q.data?.length&&<Box sx={{p:4,textAlign:'center'}}><Typography sx={{fontWeight:600}}>Noch keine Anforderungen</Typography><Typography variant="body2" color="text.secondary" sx={{mt:0.5}}>Nach dem Prüfschritt kannst du Anforderungen übernehmen oder hier manuell erfassen.</Typography></Box>}</Paper><Stack spacing={2} sx={{position:{xl:'sticky'},top:24}}><Card sx={{borderTop:`4px solid ${MARKER}`}}><CardContent><Stack spacing={1.5}><Box><Typography variant="overline" color="text.secondary">AUSGEWÄHLTE ANFORDERUNG</Typography><Typography variant="h6">{focused?.key??'Noch keine REQ'}</Typography></Box>{focused?<><Typography variant="body2" sx={{fontWeight:600}}>{focused.title}</Typography><Typography variant="body2" color="text.secondary">{focused.text}</Typography><Box sx={{height:1,bgcolor:paper.line}}/><Typography variant="subtitle2">Herkunft im Prüfschritt</Typography>{sourceRefs.length?sourceSections.map(({ref,section}:any,index:number)=><Box key={`${ref.section_id??ref.analysis_key??index}`} sx={{p:1.5,bgcolor:'#F7F7FA',borderRadius:2,borderLeft:`3px solid ${MARKER}`}}><Typography variant="caption" color="text.secondary">{section?`Abschnitt ${section.order_index+1}`:ref.analysis_key??ref.section_id??`Quelle ${index+1}`}</Typography><Typography variant="body2" sx={{mt:0.5}}>{section?.edited_text??section?.source_text??'Quellverknüpfung vorhanden; der zugehörige Prüfschritt-Abschnitt ist in dieser Fassung nicht verfügbar.'}</Typography>{section&&<Button component={Link} to={`/projects/${projectId}/review#section-${section.id}`} size="small" sx={{mt:0.5,ml:-1}}>Im Prüfschritt öffnen</Button>}</Box>):<Typography variant="body2" color="text.secondary">Für diese Anforderung sind keine Fundstellen hinterlegt.</Typography>}</>:<Typography variant="body2" color="text.secondary">Wähle eine Anforderung in der Tabelle aus.</Typography>}</Stack></CardContent></Card><Card sx={{bgcolor:ink[900],color:'#FFFFFF'}}><CardContent><Stack spacing={1.5}><Box><Typography variant="overline" sx={{color:'#B9BDD8'}}>AUSWIRKUNG</Typography><Typography variant="h6" sx={{color:'#FFFFFF'}}>Was ändert sich?</Typography></Box>{impact?.requirement_key===focused?.key?<><Box sx={{display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',gap:1}}>{([['Stunden',`${impact.hours_delta} h`],['Netto',eur(impact.net_delta_eur)],['Termin',`${impact.finish_delta_days} T`]] as const).map(([label,value])=><Box key={label}><Typography variant="caption" sx={{color:'#B9BDD8'}}>{label}</Typography><Typography sx={{fontFamily:displayFont,fontSize:'1.1rem',fontWeight:700,whiteSpace:'nowrap'}}>{value}</Typography></Box>)}</Box><Typography variant="caption" sx={{color:'#B9BDD8'}}>Abhängige Anforderungen: {impact.dependent_requirement_ids.join(', ')||'keine'}</Typography></>:<Typography variant="body2" sx={{color:'#B9BDD8'}}>Berechne den Einfluss auf Aufwand, Kosten und Termin, ohne das Projekt zu verändern.</Typography>}<Button variant="contained" onClick={async()=>{if(focused)setImpact({...(await api<any>(`/requirements/${focused.id}/impact`)),requirement_key:focused.key})}} disabled={!focused} sx={{alignSelf:'flex-start',bgcolor:MARKER,color:ink[900],'&:hover':{bgcolor:'#F2D91D'}}}>Auswirkung berechnen</Button></Stack></CardContent></Card></Stack></Box>
    <Dialog open={createOpen} onClose={()=>setCreateOpen(false)} fullWidth maxWidth="sm"><DialogTitle>Manuelle Anforderung</DialogTitle><DialogContent><Typography variant="body2" color="text.secondary" sx={{mb:1}}>Die Anforderung wird direkt als REQ in die Tabelle übernommen.</Typography><TextField sx={{mt:1}} fullWidth label="Titel" value={createDraft.title} onChange={e=>setCreateDraft({...createDraft,title:e.target.value})}/><TextField sx={{mt:2}} fullWidth multiline minRows={3} label="Anforderungstext" value={createDraft.text} onChange={e=>setCreateDraft({...createDraft,text:e.target.value})}/><TextField select sx={{mt:2}} fullWidth label="Priorität" value={createDraft.priority} onChange={e=>setCreateDraft({...createDraft,priority:e.target.value})}><MenuItem value="muss">Muss</MenuItem><MenuItem value="soll">Sollte</MenuItem><MenuItem value="kann">Kann</MenuItem></TextField>{create.error&&<Alert severity="error" sx={{mt:2}}>{String(create.error)}</Alert>}</DialogContent><DialogActions><Button onClick={()=>setCreateOpen(false)}>Abbrechen</Button><Button variant="contained" disabled={create.isPending||!createDraft.title.trim()||!createDraft.text.trim()} onClick={()=>create.mutate()}>{create.isPending?'Wird gespeichert …':'REQ speichern'}</Button></DialogActions></Dialog>
    <Dialog open={!!splitSource} onClose={()=>setSplitSource(null)} fullWidth maxWidth="md"><DialogTitle>{splitSource?.key} aufgliedern</DialogTitle><DialogContent><Alert severity="info" sx={{mb:2}}>Die ursprüngliche REQ bleibt als abgelöst markiert. Die neuen REQs werden mit ihr verknüpft und erscheinen in dieser Tabelle.</Alert><Alert severity="warning" sx={{mb:2}}>Vorhandene Verknüpfungen zu Arbeitspaketen werden nicht automatisch auf die neuen Teilanforderungen übertragen.</Alert><Stack spacing={2}>{splitParts.map((part,index)=><Paper key={index} variant="outlined" sx={{p:2}}><Stack spacing={1.5}><Typography variant="subtitle2">Teilanforderung {index+1}</Typography><TextField fullWidth label="Titel" value={part.title} onChange={e=>setSplitParts(splitParts.map((x,i)=>i===index?{...x,title:e.target.value}:x))}/><TextField fullWidth multiline minRows={2} label="Anforderungstext" value={part.text} onChange={e=>setSplitParts(splitParts.map((x,i)=>i===index?{...x,text:e.target.value}:x))}/><TextField select fullWidth label="Priorität" value={part.priority} onChange={e=>setSplitParts(splitParts.map((x,i)=>i===index?{...x,priority:e.target.value}:x))}><MenuItem value="muss">Muss</MenuItem><MenuItem value="soll">Sollte</MenuItem><MenuItem value="kann">Kann</MenuItem></TextField></Stack></Paper>)}<Stack direction="row" spacing={1}><Button onClick={()=>setSplitParts([...splitParts,{title:'',text:'',priority:splitSource?.priority??'soll'}])}>Weiteren Teil hinzufügen</Button>{splitParts.length>2&&<Button color="error" onClick={()=>setSplitParts(splitParts.slice(0,-1))}>Letzten Teil entfernen</Button>}</Stack>{split.error&&<Alert severity="error">{String(split.error)}</Alert>}</Stack></DialogContent><DialogActions><Button onClick={()=>setSplitSource(null)}>Abbrechen</Button><Button variant="contained" disabled={split.isPending||splitParts.some(x=>!x.title.trim()||!x.text.trim())} onClick={()=>split.mutate()}>{split.isPending?'Wird aufgegliedert …':'Teilanforderungen speichern'}</Button></DialogActions></Dialog>
    <Dialog open={!!selected} onClose={()=>setSelected(null)} fullWidth><DialogTitle>{selected?.key}</DialogTitle><DialogContent><TextField sx={{mt:1}} fullWidth label="Titel" defaultValue={selected?.title} id="req-title"/><TextField sx={{mt:2}} fullWidth multiline label="Text" defaultValue={selected?.text} id="req-text"/><TextField sx={{mt:2}} fullWidth label="Budget EUR" defaultValue={selected?.budget_eur??''} id="req-budget"/></DialogContent><DialogActions><Button onClick={()=>setSelected(null)}>Abbrechen</Button><Button variant="contained" onClick={async()=>{const title=(document.getElementById('req-title') as HTMLInputElement).value;const text=(document.getElementById('req-text') as HTMLInputElement).value;const budget=(document.getElementById('req-budget') as HTMLInputElement).value;await api(`/requirements/${selected.id}`,{method:'PATCH',body:JSON.stringify({expected_version:selected.lock_version,title,text,budget_eur:budget?Number(budget):null})});setSelected(null);client.invalidateQueries({queryKey:['requirements',projectId]})}}>Speichern</Button></DialogActions></Dialog>
  </Stack>
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

function CustomerPortalShell({auth}:{auth:any}){const nav=useNavigate();const {clearJobs}=useJobProgress();const projects=useQuery({queryKey:['projects'],queryFn:()=>api<any[]>('/projects')});const logout=async()=>{await api('/auth/logout',{method:'POST'});sessionStorage.clear();clearJobs();await qc.cancelQueries();qc.removeQueries({predicate:query=>query.queryKey[0]!=='me'});qc.setQueryData(['me'],null);nav('/login')};const roles=summarizeRoles(auth);return <Box sx={{minHeight:'100vh',bgcolor:'background.default'}}><Box component="header" sx={{bgcolor:ink[900],color:'#FFFFFF'}}><Container maxWidth="lg" sx={{display:'flex',flexWrap:'wrap',alignItems:'center',gap:2,py:1.5,px:{xs:2,md:3}}}><Box sx={{flexGrow:1}}><Brand label="KuSys Kundenportal"/></Box>{DEMO_ENABLED&&<Box sx={{width:220}}><DemoRoleSwitcher auth={auth}/></Box>}<Box sx={{flex:'0 1 280px',minWidth:200}}><UserBlock auth={auth} roles={roles} onLogout={logout} divider={false}/></Box></Container></Box><Container maxWidth="lg" sx={{py:{xs:2.5,md:4},px:{xs:2,md:3}}}><Routes><Route path="/" element={<Stack spacing={2}><Typography variant="h4" component="h1">Veröffentlichte Projekte</Typography>{projects.data?.map((p:any)=><Card key={p.id}><CardContent><Stack direction="row" sx={{justifyContent:'space-between',alignItems:'center',gap:2}}><Box><Typography variant="h6">{p.project_number} · {p.name}</Typography><Typography color="text.secondary">{p.status}</Typography></Box><Button component={Link} to={`/portal/${p.id}`} variant="contained">Öffnen</Button></Stack></CardContent></Card>)}</Stack>}/><Route path="/portal/:projectId" element={<CustomerProjectPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></Container></Box>}

function CustomerProjectPage(){
  const {projectId=''}=useParams();const client=useQueryClient()
  const q=useQuery({queryKey:['portal',projectId],queryFn:()=>api<any>(`/portal/projects/${projectId}`)})
  const [answers,setAnswers]=useState<Record<string,string>>({})
  const [offerReplies,setOfferReplies]=useState<Record<string,string>>({})
  const [replyError,setReplyError]=useState('')
  if(q.isLoading)return <Loading/>
  const answerClarification=async(c:any)=>{await api(`/portal/clarifications/${c.id}/answer`,{method:'POST',body:JSON.stringify({answer:answers[c.id]??''})});setAnswers({...answers,[c.id]:''});await client.invalidateQueries({queryKey:['portal',projectId]})}
  const answerOffer=async(offer:any)=>{
    setReplyError('')
    try{await api(`/portal/offer-versions/${offer.id}/responses`,{method:'POST',body:JSON.stringify({body:offerReplies[offer.id]??''})});setOfferReplies({...offerReplies,[offer.id]:''});await client.invalidateQueries({queryKey:['portal',projectId]})}
    catch(error){setReplyError(String(error))}
  }
  return <Stack spacing={3}>
    <Button component={Link} to="/" size="small" startIcon={<Icon name="back" size={16}/>} sx={{alignSelf:'flex-start',ml:-1}}>Projekte</Button>
    <Box><Typography variant="h4">{q.data?.project_number} · {q.data?.name}</Typography><Typography color="text.secondary">Status: {q.data?.status}</Typography></Box>
    <Card><CardContent><Typography variant="h6">Freigegebene Dokumente</Typography><Stack spacing={1} sx={{mt:1}}>{q.data?.published_artifacts.length?q.data.published_artifacts.map((a:any)=><Button key={a.artifact_id} component="a" href={artifactUrl(a.artifact_id)} target="_blank" rel="noreferrer" variant="outlined" sx={{alignSelf:'flex-start'}}>{a.kind} ({a.language}) herunterladen</Button>):<Typography color="text.secondary">Noch keine veröffentlichten Dokumente.</Typography>}</Stack></CardContent></Card>
    {!!q.data?.offers?.length&&<Card><CardContent><Typography variant="h6">Angebote & Rückmeldung</Typography><Stack spacing={2} sx={{mt:2}}>{q.data.offers.map((offer:any)=><Box key={offer.id} sx={{borderBottom:'1px solid',borderColor:'divider',pb:2}}>
      <Stack direction="row" spacing={1} sx={{alignItems:'center',flexWrap:'wrap'}}><Typography sx={{fontWeight:600}}>{offer.offer_number} · {offer.variant_name} · V{offer.version}</Typography><Chip size="small" color="success" label="freigegeben"/><Button size="small" component="a" href={artifactUrl(offer.artifact_id)} target="_blank" rel="noreferrer">Angebot laden</Button></Stack>
      {!!offer.responses?.length&&<Stack spacing={1} sx={{mt:1}}>{offer.responses.map((response:any)=><Alert key={response.id} severity="info"><strong>{response.author_name}</strong> · {new Date(response.created_at).toLocaleString('de-DE')}<br/>{response.body}</Alert>)}</Stack>}
      <Stack direction={{xs:'column',md:'row'}} spacing={1} sx={{mt:1}}><TextField size="small" fullWidth multiline minRows={2} label="Ihre Rückmeldung zum Angebot" value={offerReplies[offer.id]??''} onChange={event=>setOfferReplies({...offerReplies,[offer.id]:event.target.value})}/><Button variant="contained" onClick={()=>void answerOffer(offer)} disabled={!offerReplies[offer.id]?.trim()}>Rückmeldung senden</Button></Stack>
    </Box>)}</Stack>{replyError&&<Alert severity="error" sx={{mt:2}}>{replyError}</Alert>}</CardContent></Card>}
    <Card><CardContent><Typography variant="h6">Klärungspunkte</Typography><Stack spacing={2} sx={{mt:2}}>{q.data?.clarifications.map((c:any)=><Box key={c.id}><Typography sx={{fontWeight:600}}>{c.key} · {c.text}</Typography><Typography variant="body2" color="text.secondary">{c.status}</Typography>{c.answer?<Alert severity="info" sx={{mt:1}}>{c.answer}</Alert>:<Stack direction={{xs:'column',md:'row'}} spacing={1} sx={{mt:1}}><TextField size="small" fullWidth label="Ihre Antwort" value={answers[c.id]??''} onChange={e=>setAnswers({...answers,[c.id]:e.target.value})}/><Button variant="contained" onClick={()=>void answerClarification(c)}>Antworten</Button></Stack>}</Box>)}</Stack></CardContent></Card>
  </Stack>
}

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
