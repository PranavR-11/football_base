'use client'

import { useMemo } from 'react'
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'
import type { TooltipItem } from 'chart.js'
import { Line } from 'react-chartjs-2'
import { defaultPlayer, playerMetrics, PlayerMetricRow } from '@/data/playerMetrics'

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

type PlayerTimeSeriesChartProps = {
  responseText?: string
  generationKey: number
}

const metricAliases: Record<string, keyof PlayerMetricRow> = {
  goals: 'goals',
  assists: 'assists',
  xg: 'xg',
  'expected goals': 'xg',
  expectedgoals: 'xg',
  'np xg': 'npxg',
  npxg: 'npxg',
  'non penalty xg': 'npxg',
  'non-penalty xg': 'npxg'
}

const metricLabels: Record<string, string> = {
  goals: 'Goals',
  assists: 'Assists',
  xg: 'xG',
  npxg: 'NP xG'
}

const normalizeForSearch = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')

const normalizeMetric = (text: string): keyof PlayerMetricRow => {
  const lower = text.toLowerCase()
  for (const key of Object.keys(metricAliases)) {
    if (lower.includes(key)) {
      return metricAliases[key as keyof typeof metricAliases]
    }
  }
  return 'goals'
}

const findPlayer = (text: string | undefined) => {
  if (!text) return defaultPlayer
  const lower = normalizeForSearch(text).toLowerCase()
  return (
    Object.keys(playerMetrics).find(player =>
      lower.includes(normalizeForSearch(player).toLowerCase())
    ) || defaultPlayer
  )
}

const PlayerTimeSeriesChart = ({ responseText, generationKey }: PlayerTimeSeriesChartProps) => {
  const playerName = useMemo(() => findPlayer(responseText), [responseText])

  const metricKey = useMemo(() => normalizeMetric(responseText || ''), [responseText])

  const rows = playerMetrics[playerName] || []

  const chartData = useMemo(() => {
    if (!rows.length) {
      return {
        labels: [],
        datasets: []
      }
    }

    const ordered = [...rows].sort((a, b) => a.season - b.season)
    const labels = ordered.map(entry => entry.season.toString())
    const metricValues = ordered.map(entry => entry[metricKey] ?? 0)

    return {
      labels,
      datasets: [
        {
          label: `${playerName} — ${metricLabels[metricKey] ?? metricKey}`,
          data: metricValues,
          fill: {
            target: 'origin',
            above: 'rgba(34,197,94,0.18)'
          },
          borderColor: '#34d399',
          backgroundColor: 'rgba(34,197,94,0.4)',
          pointBackgroundColor: '#10b981',
          pointBorderColor: '#ecfccb',
          pointRadius: 5,
          pointHoverRadius: 7,
          tension: 0.25,
          borderWidth: 2
        }
      ]
    }
  }, [rows, metricKey, playerName, generationKey])

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#c9e6d3' }
        },
        y: {
          ticks: { color: '#c9e6d3' },
          grid: {
            color: 'rgba(255,255,255,0.05)'
          }
        }
      },
      plugins: {
        legend: {
          labels: {
            color: '#e9f3ea',
            boxWidth: 18,
            boxHeight: 18,
            padding: 20
          }
        },
        tooltip: {
          callbacks: {
            label: (ctx: TooltipItem<'line'>) => `${ctx.dataset.label}: ${ctx.formattedValue}`
          }
        }
      }
    }),
    []
  )

  if (!rows.length) {
    return (
      <div className="h-64 rounded-2xl border border-emerald-400/20 flex items-center justify-center text-emerald-100/70 text-sm">
        Select a prompt mentioning a supported player to see trend data.
      </div>
    )
  }

  return (
    <div className="h-72 sm:h-80">
      <Line
        key={`${playerName}-${metricKey}-${generationKey}`}
        data={chartData}
        options={options}
      />
    </div>
  )
}

export default PlayerTimeSeriesChart
