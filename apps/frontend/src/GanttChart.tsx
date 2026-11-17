import { useEffect, useRef, useState } from 'react'
import { Box, Card, CardContent, Chip, Stack, Typography } from '@mui/material'

type WorkPackage = {
  id: string
  key: string
  name: string
}

type ScheduledPackage = {
  id: string
  start: string
  finish: string
  duration_days: number
  total_float_days: number
  critical: boolean
}

type Schedule = {
  project_start: string
  project_finish: string
  critical_path: string[]
  packages: ScheduledPackage[]
}

const DAY_MS = 24 * 60 * 60 * 1000
const utcDay = (value: string) => {
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return Date.UTC(year, month - 1, day)
}
const fullDate = (day: number) => new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(day))
const monthName = (day: number) => new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(day))

export function GanttChart({ workPackages, schedule }: { workPackages: WorkPackage[]; schedule: Schedule }) {
  const calendarRef = useRef<HTMLDivElement | null>(null)
  const [calendarViewportWidth, setCalendarViewportWidth] = useState(0)
  useEffect(() => {
    const element = calendarRef.current
    if (!element) return
    const observer = new ResizeObserver(entries => setCalendarViewportWidth(entries[0]?.contentRect.width ?? 0))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const packagesById = new Map(workPackages.map(item => [item.id, item]))
  const rows = schedule.packages.flatMap(item => {
    const workPackage = packagesById.get(item.id)
    return workPackage ? [{ ...item, workPackage }] : []
  })
  if (!rows.length) return null

  const projectStart = utcDay(schedule.project_start)
  const projectFinish = utcDay(schedule.project_finish)
  const mondayOffset = (new Date(projectStart).getUTCDay() + 6) % 7
  const firstMonday = projectStart - mondayOffset * DAY_MS
  const weekCount = Math.floor((projectFinish - firstMonday) / (7 * DAY_MS)) + 1
  const cellWidth = Math.max(120, calendarViewportWidth > 0 ? calendarViewportWidth / 7 : 154)
  const calendarWidth = cellWidth * 7
  const headerHeight = 46
  const packageBarHeight = 24
  const laneGap = 5
  const weekGap = 8
  const weekdayNames = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

  const weeks = Array.from({ length: weekCount }, (_, weekIndex) => {
    const weekStart = firstMonday + weekIndex * 7 * DAY_MS
    const segments = rows.flatMap(item => {
      const start = utcDay(item.start)
      const finish = utcDay(item.finish)
      const firstWeek = Math.floor((start - firstMonday) / (7 * DAY_MS))
      const lastWeek = Math.floor((finish - firstMonday) / (7 * DAY_MS))
      if (weekIndex < firstWeek || weekIndex > lastWeek) return []
      const startColumn = Math.max(0, Math.floor((start - weekStart) / DAY_MS))
      const finishColumn = Math.min(6, Math.floor((finish - weekStart) / DAY_MS))
      return [{ item, startColumn, finishColumn }]
    }).sort((a, b) => a.startColumn - b.startColumn || a.finishColumn - b.finishColumn)

    const laneEnds: number[] = []
    const placed = segments.map(segment => {
      let lane = laneEnds.findIndex(endColumn => endColumn < segment.startColumn)
      if (lane < 0) lane = laneEnds.length
      laneEnds[lane] = segment.finishColumn
      return { ...segment, lane }
    })
    const laneCount = Math.max(1, laneEnds.length)
    const weekHeight = headerHeight + laneCount * (packageBarHeight + laneGap) + 8
    return { weekStart, placed, weekHeight, laneCount }
  })

  let cursorY = 42
  const positionedWeeks = weeks.map(week => {
    const positioned = { ...week, y: cursorY }
    cursorY += week.weekHeight + weekGap
    return positioned
  })
  const svgHeight = cursorY + 4
  const criticalPath = schedule.critical_path.flatMap(id => {
    const item = rows.find(row => row.id === id)
    return item ? [item.workPackage.key] : []
  })
  const criticalSet = new Set(schedule.critical_path)

  return <Card sx={{ overflow: 'hidden', border: '1px solid', borderColor: 'divider' }}>
    <CardContent sx={{ pb: '16px !important' }}>
      <Stack direction={{ xs: 'column', md: 'row' }} sx={{ justifyContent: 'space-between', alignItems: { md: 'center' }, gap: 1.5, mb: 1.5 }}>
        <Box>
          <Typography variant="h6">Terminplan · Kalender</Typography>
          <Typography variant="body2" color="text.secondary">{fullDate(projectStart)} – {fullDate(projectFinish)} · {rows.length} Arbeitspakete im Kalender</Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip size="small" label="Arbeitspaket" sx={{ bgcolor: '#3A3F72', color: '#fff', fontWeight: 600 }} />
          <Chip size="small" label="Kritischer Pfad" sx={{ bgcolor: '#C2410C', color: '#fff', fontWeight: 600 }} />
        </Stack>
      </Stack>

      {criticalPath.length > 0 && <Box sx={{ mb: 1.5, p: 1.5, borderRadius: 1.5, bgcolor: '#FFF1E8', border: '1px solid #FFCBAE' }}>
        <Typography variant="caption" sx={{ display: 'block', color: '#8A2F0B', fontWeight: 700, mb: 0.5 }}>Kritischer Pfad</Typography>
        <Typography variant="body2" sx={{ color: '#5F1F05', fontWeight: 650 }}>{criticalPath.join('  →  ')}</Typography>
      </Box>}

      <Box ref={calendarRef} sx={{ width: '100%', overflowX: 'auto', borderRadius: 1.5, border: '1px solid', borderColor: 'divider', bgcolor: '#FFFFFF' }}>
        <svg width={calendarWidth} height={svgHeight} role="img" aria-label={`Projektkalender mit ${rows.length} Arbeitspaketen vom ${fullDate(projectStart)} bis ${fullDate(projectFinish)}`} style={{ display: 'block', fontFamily: 'inherit' }}>
          <defs>
            <filter id="critical-glow" x="-10%" y="-30%" width="120%" height="160%">
              <feDropShadow dx="0" dy="1" stdDeviation="2" floodColor="#15172E" floodOpacity="0.25" />
            </filter>
          </defs>
          {weekdayNames.map((name, column) => <g key={name}>
            <rect x={column * cellWidth} y="0" width={cellWidth} height="34" fill={column >= 5 ? '#EAECF2' : '#E4E6EE'} />
            <text x={column * cellWidth + 10} y="22" fill="#3A3E55" fontSize="12" fontWeight="700">{name}</text>
          </g>)}
          {positionedWeeks.map((week, weekIndex) => <g key={`week-${weekIndex}`}>
            <rect x="0" y={week.y} width={calendarWidth} height={week.weekHeight} rx="3" fill="#F7F8FA" stroke="#DDE0E8" />
            {Array.from({ length: 7 }, (_, column) => {
              const day = week.weekStart + column * DAY_MS
              const inProject = day >= projectStart && day <= projectFinish
              const isWeekend = column >= 5
              const isNewMonth = new Date(day).getUTCDate() === 1
              return <g key={`day-${weekIndex}-${column}`}>
                <rect x={column * cellWidth} y={week.y} width={cellWidth} height={week.weekHeight} fill={!inProject ? '#EEF0F4' : isWeekend ? '#FAFBFC' : '#FFFFFF'} />
                <line x1={column * cellWidth} y1={week.y} x2={column * cellWidth} y2={week.y + week.weekHeight} stroke="#E2E4EB" />
                <text x={column * cellWidth + 9} y={week.y + 20} fill={inProject ? '#15172E' : '#A2A9B1'} fontSize="12" fontWeight={isNewMonth || !inProject ? 500 : 700}>{new Date(day).getUTCDate()}</text>
                {isNewMonth && <text x={column * cellWidth + 30} y={week.y + 20} fill="#555A70" fontSize="10" fontWeight="600">{monthName(day)}</text>}
              </g>
            })}
            <line x1={calendarWidth - 1} y1={week.y} x2={calendarWidth - 1} y2={week.y + week.weekHeight} stroke="#E2E4EB" />
            {week.placed.map(({ item, startColumn, finishColumn, lane }) => {
              const critical = criticalSet.has(item.id) || item.critical
              const x = startColumn * cellWidth + 5
              const width = (finishColumn - startColumn + 1) * cellWidth - 10
              const y = week.y + 29 + lane * (packageBarHeight + laneGap)
              const color = critical ? '#C2410C' : '#3A3F72'
              const label = width > 245 ? `${item.workPackage.key} · ${item.workPackage.name}` : item.workPackage.key
              return <g key={`${item.id}-${weekIndex}`}>
                <title>{`${item.workPackage.key} · ${item.workPackage.name} · ${fullDate(utcDay(item.start))} bis ${fullDate(utcDay(item.finish))} · ${item.duration_days} Arbeitstage${critical ? ' · Kritischer Pfad' : ` · Puffer ${item.total_float_days} Tage`}`}</title>
                <rect x={x} y={y} width={width} height={packageBarHeight} rx="7" fill={color} filter={critical ? 'url(#critical-glow)' : undefined} />
                <text x={x + 8} y={y + 16} fill="#FFFFFF" fontSize="10.5" fontWeight="700">{label}</text>
              </g>
            })}
          </g>)}
        </svg>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>Kalenderwochen beginnen am Montag. Pakete erstrecken sich über ihren geplanten Zeitraum; kritische Pakete sind orange markiert.</Typography>
    </CardContent>
  </Card>
}
