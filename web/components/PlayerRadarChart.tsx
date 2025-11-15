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
import type { ChartOptions } from 'chart.js'
import { Radar } from 'react-chartjs-2'
import { buildRadarData, PlayerMetricsStore } from '@/lib/playerMetrics'

Chart.register(RadialLinearScale, LineElement, PointElement, Filler, Tooltip, Legend)

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
          display: false
        }
      },
      scales: {
        r: {
          angleLines: { color: 'rgba(255,255,255,0.1)' },
          grid: {
            color: 'rgba(255,255,255,0.1)'
          },
          pointLabels: {
            color: '#e8f5e9',
            font: {
              size: 12
            }
          },
          ticks: {
            display: false,
            beginAtZero: true,
            max: 100
          }
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
    <div className="h-60 sm:h-72 rounded-2xl border border-emerald-400/25 bg-black/30 p-3">
      <Radar key={`${players.join('-')}-radar-${generationKey}`} data={radarData} options={options} />
      <p className="text-emerald-100/70 text-[11px] mt-2 text-center">
        Normalized vs. elite thresholds — 100 = elite output
      </p>
    </div>
  )
}

export default PlayerRadarChart
