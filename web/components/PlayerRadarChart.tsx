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
  actual_values_array?: Record<string, number[]>  // Optional for backward compatibility
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
    ctx.font = 'bold 11px Inter, system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex)
      const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2
      const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2

      meta.data.forEach((point, index) => {
        const rawValue = dataset.data[index]
        const numericValue = typeof rawValue === 'number' ? rawValue : Number(rawValue)
        if (!Number.isFinite(numericValue)) return

        const { x, y } = point.tooltipPosition(false) as { x: number; y: number }

        // Calculate angle and distance from center to push labels outward
        const dx = x - centerX
        const dy = y - centerY
        const distance = Math.sqrt(dx * dx + dy * dy)

        // Push labels outward by 15-25 pixels depending on dataset index to avoid overlap
        const pushDistance = 15 + (datasetIndex * 12)
        const offsetX = distance > 0 ? (dx / distance) * pushDistance : 0
        const offsetY = distance > 0 ? (dy / distance) * pushDistance : 0

        const labelX = x + offsetX
        const labelY = y + offsetY

        // Draw background for better visibility
        const text = `${Math.round(numericValue)}`
        const textWidth = ctx.measureText(text).width
        const color = (dataset.borderColor as string) || '#FF6B6B'

        ctx.fillStyle = 'rgba(0,0,0,0.8)'
        ctx.fillRect(labelX - textWidth / 2 - 4, labelY - 10, textWidth + 8, 18)

        // Draw text with dataset color
        ctx.fillStyle = color
        ctx.fillText(text, labelX, labelY)
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
        // Fallback: if actual_values_array is missing (old backend), use percentiles
        const actualValues = payload.actual_values_array?.[player] || payload.percentiles[player] || payload.metrics.map(() => 0)
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
    // If actual_values_array exists, use it; otherwise fall back to percentile scale
    const actualValuesArray = payload.actual_values_array
    if (actualValuesArray) {
      const allValues = payload.players.flatMap(
        (player) => actualValuesArray[player] || []
      )
      const max = Math.max(...allValues.filter(Number.isFinite), 1)
      return Math.ceil(max * 1.2) // Add 20% padding
    }
    return 120 // Fallback to percentile scale (0-100)
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
          angleLines: { color: 'rgba(255,255,255,0.2)' },
          grid: { color: 'rgba(255,255,255,0.12)' },
          pointLabels: {
            color: '#e0f2fe',
            font: { size: 13, weight: 700 },
            padding: 8
          },
          ticks: {
            display: true,
            beginAtZero: true,
            max: maxValue,
            color: 'rgba(186, 230, 253, 0.8)',
            backdropColor: 'rgba(0,0,0,0.5)',
            backdropPadding: 2,
            font: { size: 10, weight: 600 }
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
    <div className="w-full flex flex-col">
      <div className="w-full" style={{ height: '400px' }}>
        <Radar key={`radar-${generationKey}`} data={chartData} options={options} />
      </div>
      <p className="text-emerald-100/70 text-xs mt-4 text-center font-semibold">
        Raw stat values — {deriveSeason(payload.seasons)}
      </p>
    </div>
  )
}

function deriveSeason(seasons: Record<string, string | null>) {
  const values = Object.values(seasons || {}).filter((v): v is string => Boolean(v))
  if (!values.length) return 'Latest Season'
  const unique = Array.from(new Set(values))
  if (unique.length === 1) {
    // Format single season as "24-25" style
    const season = unique[0]
    if (/^\d{4}$/.test(season)) {
      const year = Number(season)
      if (!Number.isNaN(year)) {
        const start = (year - 1).toString().slice(-2)
        const end = year.toString().slice(-2)
        return `${start}-${end}`
      }
    }
    return season
  }
  return 'Recent Seasons'
}

function formatPlayerLabel(player: string, season?: string | null) {
  if (!season) return player
  if (/^\d{4}$/.test(season)) {
    const year = Number(season)
    if (!Number.isNaN(year)) {
      const start = (year - 1).toString().slice(-2)
      const end = year.toString().slice(-2)
      return `${player} (${start}-${end})`
    }
  }
  return `${player} (${season})`
}

export default PlayerRadarChart
