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
import { buildRadarData, PlayerMetricsStore } from '@/lib/playerMetrics'

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
        const numericValue = Number(rawValue)
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

type Props = {
  players: string[]
  store: PlayerMetricsStore
  generationKey: number
}

const PlayerRadarChart = ({ players, store, generationKey }: Props) => {
  const radarData = useMemo(
    () => buildRadarData(players, store),
    [players, store, generationKey]
  )

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
          text: 'Performance Radar (Percentiles + Actual)',
          color: '#e3fce8',
          font: { size: 14, weight: 'bold' }
        }
      },
      scales: {
        r: {
          angleLines: { color: 'rgba(255,255,255,0.15)' },
          grid: {
            color: 'rgba(255,255,255,0.08)'
          },
          pointLabels: {
            color: '#bae6fd',
            font: {
              size: 12,
              weight: 600
            }
          },
          ticks: {
            display: false,
            beginAtZero: true,
            max: 100
          }
        }
      },
      elements: {
        line: {
          borderWidth: 3
        },
        point: {
          radius: 5,
          hoverRadius: 7
        }
      }
    }),
    []
  )

  if (!radarData) {
    return (
      <div className="h-60 rounded-2xl border border-emerald-400/25 bg-black/30 flex items-center justify-center text-emerald-100/70 text-xs text-center px-4">
        Need at least one recent season of data for these players to show radar metrics.
      </div>
    )
  }

  return (
    <div className="h-60 sm:h-72 rounded-2xl border border-emerald-400/25 bg-black/30 p-3 flex flex-col">
      <div className="flex-1">
        <Radar
          key={`${players.join('-')}-radar-${generationKey}`}
          data={radarData}
          options={options}
        />
      </div>
      <p className="text-emerald-100/70 text-[11px] mt-3 text-center">
        Normalized vs. elite thresholds — 100 = elite output
      </p>
    </div>
  )
}

export default PlayerRadarChart
