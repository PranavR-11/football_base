'use client'

export type PlayerSeasonEntry = {
  season: string
  squad?: string
  pos?: string
  comp?: string
  goals?: number
  assists?: number
  goals_assists?: number
  goals_no_pk?: number
  performance_pk?: number
  penalties_taken?: number
  yellow_cards?: number
  red_cards?: number
  xg?: number
  npxg?: number
  xag?: number
  npxg_xag?: number
  progressive_carries?: number
  progressive_passes?: number
  progressive_received?: number
  goals_per_90?: number
  assists_per_90?: number
  goals_assists_per_90?: number
  goals_no_pk_per_90?: number
  goals_assists_no_pk_per_90?: number
  xg_per_90?: number
  xag_per_90?: number
  xg_xag_per_90?: number
  npxg_per_90?: number
  npxg_xag_per_90?: number
}

export type PlayerMetricsStore = Record<string, PlayerSeasonEntry[]>

export type MetricKey =
  | 'goals'
  | 'assists'
  | 'goals_no_pk'
  | 'goals_assists'
  | 'xg'
  | 'npxg'
  | 'xag'
  | 'npxg_xag'
  | 'progressive_carries'
  | 'progressive_passes'
  | 'progressive_received'
  | 'goals_per_90'
  | 'assists_per_90'
  | 'goals_assists_per_90'
  | 'goals_no_pk_per_90'
  | 'xg_per_90'
  | 'xag_per_90'
  | 'npxg_per_90'

export type PlayerIndexEntry = {
  name: string
  normalized: string
  tokens: string[]
}

const normalizeText = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

const metricLabels: Record<MetricKey, string> = {
  goals: 'Goals',
  assists: 'Assists',
  goals_no_pk: 'Goals (No PK)',
  goals_assists: 'Goals + Assists',
  xg: 'xG',
  npxg: 'NP xG',
  xag: 'xAG',
  npxg_xag: 'NP xG + xAG',
  progressive_carries: 'Prog. Carries',
  progressive_passes: 'Prog. Passes',
  progressive_received: 'Prog. Received',
  goals_per_90: 'Goals / 90',
  assists_per_90: 'Assists / 90',
  goals_assists_per_90: 'G+A / 90',
  goals_no_pk_per_90: 'Goals (NP) / 90',
  xg_per_90: 'xG / 90',
  xag_per_90: 'xAG / 90',
  npxg_per_90: 'NP xG / 90'
}

const metricAliases: Record<string, MetricKey> = {
  goals: 'goals',
  goal: 'goals',
  scoring: 'goals',
  assists: 'assists',
  assist: 'assists',
  'goals + assists': 'goals_assists',
  'ga': 'goals_assists',
  xg: 'xg',
  'expected goals': 'xg',
  'expected-goals': 'xg',
  npxg: 'npxg',
  'np xg': 'npxg',
  'non penalty xg': 'npxg',
  xag: 'xag',
  'expected assists': 'xag',
  'np xg + xag': 'npxg_xag',
  'npxg+xag': 'npxg_xag',
  'progressive carries': 'progressive_carries',
  'progressive carries per 90': 'progressive_carries',
  'progressive passes': 'progressive_passes',
  'progressive received': 'progressive_received',
  'goals per 90': 'goals_per_90',
  'assists per 90': 'assists_per_90',
  'goals + assists per 90': 'goals_assists_per_90',
  'non penalty goals per 90': 'goals_no_pk_per_90',
  'xg per 90': 'xg_per_90',
  'xag per 90': 'xag_per_90',
  'npxg per 90': 'npxg_per_90'
}

const multiPlayerIndicators = [' vs ', ' vs. ', 'versus', 'compare', 'comparison']

export const createPlayerIndex = (store: PlayerMetricsStore): PlayerIndexEntry[] => {
  return Object.keys(store).map((name) => ({
    name,
    normalized: normalizeText(name),
    tokens: name
      .split(/\s+/)
      .map((token) => normalizeText(token))
      .filter(Boolean)
  }))
}

const seasonToNumber = (season: string) => {
  if (!season) return 0
  if (season.includes('-')) {
    const [start] = season.split('-')
    const numeric = parseInt(start, 10)
    if (Number.isNaN(numeric)) return 0
    return numeric < 50 ? 2000 + numeric : 1900 + numeric
  }
  const numeric = parseInt(season, 10)
  if (Number.isNaN(numeric)) return 0
  return numeric < 100 ? (numeric < 50 ? 2000 + numeric : 1900 + numeric) : numeric
}

export const sortSeasons = (entries: PlayerSeasonEntry[]) => {
  return [...entries].sort((a, b) => seasonToNumber(a.season) - seasonToNumber(b.season))
}

export const detectMetricFromText = (text: string): MetricKey => {
  const normalized = normalizeText(text || '')
  for (const [alias, metric] of Object.entries(metricAliases)) {
    if (normalized.includes(alias)) {
      return metric
    }
  }
  return 'goals'
}

export const detectPlayersFromText = (text: string, index: PlayerIndexEntry[], limit = 2) => {
  if (!text) return []
  const normalized = normalizeText(text)
  const matches: string[] = []

  for (const entry of index) {
    if (normalized.includes(entry.normalized)) {
      matches.push(entry.name)
    } else if (entry.tokens.some((token) => token.length > 2 && normalized.includes(token))) {
      matches.push(entry.name)
    }
    if (matches.length >= limit) break
  }

  return matches
}

export const isSinglePlayerQuery = (text: string) => {
  const normalized = normalizeText(text || '')
  return !multiPlayerIndicators.some((indicator) => normalized.includes(indicator))
}

export const getMetricLabel = (metric: MetricKey) => metricLabels[metric] || metric

export const buildLineChartData = (
  players: string[],
  metric: MetricKey,
  store: PlayerMetricsStore
) => {
  const seasonSet = new Set<string>()
  players.forEach((player) => {
    store[player]?.forEach((entry) => {
      if (entry.season) seasonSet.add(entry.season)
    })
  })

  const labels = Array.from(seasonSet).sort((a, b) => seasonToNumber(a) - seasonToNumber(b))

  const colors = ['#34d399', '#f472b6', '#60a5fa', '#facc15']

  const datasets = players.map((player, index) => {
    const playerEntries = sortSeasons(store[player] || [])
    const valueMap = new Map(playerEntries.map((entry) => [entry.season, entry[metric] ?? null]))
    return {
      label: `${player} — ${getMetricLabel(metric)}`,
      data: labels.map((label) => (valueMap.get(label) as number | null) ?? null),
      borderColor: colors[index % colors.length],
      backgroundColor: `${colors[index % colors.length]}33`,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.25
    }
  })

  return { labels, datasets }
}

const radarFields: { key: keyof PlayerSeasonEntry; label: string; cap: number }[] = [
  { key: 'goals', label: 'Goals', cap: 40 },
  { key: 'assists', label: 'Assists', cap: 20 },
  { key: 'xg', label: 'xG', cap: 35 },
  { key: 'npxg', label: 'NP xG', cap: 30 },
  { key: 'progressive_carries', label: 'Prog. Carries', cap: 250 },
  { key: 'progressive_passes', label: 'Prog. Passes', cap: 300 },
  { key: 'progressive_received', label: 'Prog. Received', cap: 300 }
]

export const buildRadarData = (player: string, store: PlayerMetricsStore) => {
  const rows = sortSeasons(store[player] || [])
  if (!rows.length) return null
  const latest = rows[rows.length - 1]

  const labels = radarFields.map((field) => field.label)
  const data = radarFields.map((field) => {
    const raw = (latest[field.key] ?? 0) as number
    const normalized = Math.min(100, Math.round((raw / field.cap) * 100))
    return Number.isFinite(normalized) ? normalized : 0
  })

  return {
    labels,
    datasets: [
      {
        label: player,
        data,
        backgroundColor: 'rgba(52, 211, 153, 0.15)',
        borderColor: '#34d399',
        borderWidth: 2,
        pointBackgroundColor: '#34d399'
      }
    ]
  }
}
