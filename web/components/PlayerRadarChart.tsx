'use client'

import { useMemo } from 'react'
import {
  Chart,
  RadialLinearScale,
  LineElement,
  PointElement,
  Filler,
  Tooltip,
  Legend
} from 'chart.js'
import type { ChartOptions, Plugin } from 'chart.js'
import { Radar } from 'react-chartjs-2'

export type RadarPayload = {
  metrics: string[]
  players: string[]
  percentiles: Record<string, number[]>
  actual_values: Record<string, Record<string, number>>
  actual_values_array: Record<string, number[]>
  seasons: Record<string, string | null>
}

type Props = {
  payload: RadarPayload
  generationKey: number
}

const radarLabelsPlugin: Plugin<'radar'> = {
  id: 'radarValueLabels',
  afterDatasetsDraw(chart) {
    const { ctx } = chart
    ctx.save()
    ctx.font = '600 10px Inter, system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex)
      meta.data.forEach((point, index) => {
        const rawValue = dataset.data[index]
        const numericValue = typeof rawValue === 'number' ? rawValue : Number(rawValue)
        if (!Number.isFinite(numericValue)) return
        const { x, y } = point.tooltipPosition(false) as { x: number; y: number }
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.fillText(`${Math.round(numericValue)}`, x, y - 6)
      })
    })
    ctx.restore()
  }
}

Chart.register(RadialLinearScale, LineElement, PointElement, Filler, Tooltip, Legend, radarLabelsPlugin)

const metricLabel = (metric: string) => metric.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())

const chartColors = ['#FF6B6B', '#4ECDC4', '#FFD93D', '#A78BFA']

const PlayerRadarChart = ({ payload, generationKey }: Props) => {
  const chartData = useMemo(() => {
    const labels = payload.metrics.map(metricLabel)
    return {
      labels,
      datasets: payload.players.map((player, index) => {
        const actualValues = payload.actual_values_array[player] || payload.metrics.map(() => 0)
        const color = chartColors[index % chartColors.length]
        return {
          label: formatPlayerLabel(player, payload.seasons?.[player]),
          data: actualValues,
          borderColor: color,
          backgroundColor: `${color}40`,
          borderWidth: 3.5,
          fill: true,
          pointBackgroundColor: color,
          pointBorderColor: '#fff',
          pointRadius: 5,
          pointHoverRadius: 7
        }
      })
    }
  }, [payload, generationKey])

  const maxValue = useMemo(() => {
    const allValues = payload.players.flatMap(
      (player) => payload.actual_values_array[player] || []
    )
    const max = Math.max(...allValues.filter(Number.isFinite), 1)
    return Math.ceil(max * 1.2) // Add 20% padding
  }, [payload])

  const options = useMemo<ChartOptions<'radar'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#e8f5e9', usePointStyle: true, pointStyle: 'circle' }
        },
        title: {
          display: true,
          text: `Performance Radar — ${deriveSeason(payload.seasons)}`,
          color: '#e3fce8',
          font: { size: 14, weight: 'bold' }
        }
      },
      scales: {
        r: {
          angleLines: { color: 'rgba(255,255,255,0.15)' },
          grid: { color: 'rgba(255,255,255,0.08)' },
          pointLabels: {
            color: '#bae6fd',
            font: { size: 12, weight: 600 }
          },
          ticks: {
            display: true,
            beginAtZero: true,
            max: maxValue,
            color: 'rgba(186, 230, 253, 0.6)',
            backdropColor: 'transparent',
            font: { size: 10 }
          }
        }
      },
      elements: {
        line: { borderWidth: 3 },
        point: { radius: 5, hoverRadius: 7 }
      }
    }),
    [payload, maxValue]
  )

  return (
    <div className="h-60 sm:h-72 rounded-2xl border border-emerald-400/25 bg-black/30 p-3 flex flex-col">
      <div className="flex-1">
        <Radar key={`radar-${generationKey}`} data={chartData} options={options} />
      </div>
      <p className="text-emerald-100/70 text-[11px] mt-3 text-center">
        Raw stat values — {deriveSeason(payload.seasons)}
      </p>
    </div>
  )
}

function deriveSeason(seasons: Record<string, string | null>) {
  const values = Object.values(seasons || {}).filter(Boolean)
  if (!values.length) return 'Recent Seasons'
  const unique = Array.from(new Set(values))
  return unique.length === 1 ? unique[0] : 'Recent Seasons'
}

function formatPlayerLabel(player: string, season?: string | null) {
  if (!season) return player
  if (/^\d{4}$/.test(season)) {
    const year = Number(season)
    if (!Number.isNaN(year)) {
      const next = (year + 1).toString().slice(-2)
      return `${player} (${season.slice(-2)}-${next})`
    }
  }
  return `${player} (${season})`
}

export default PlayerRadarChart
