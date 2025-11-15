'use client'

import {
  Chart,
  BarElement,
  BarController,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend
} from 'chart.js'
import type { ChartOptions, TooltipItem } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { buildHeadToHeadBarData, MetricKey, PlayerMetricsStore } from '@/lib/playerMetrics'
import { useMemo } from 'react'

Chart.register(BarElement, BarController, CategoryScale, LinearScale, Tooltip, Legend)

type Props = {
  players: string[]
  metrics: MetricKey[]
  store: PlayerMetricsStore
  generationKey: number
}

const PlayerHeadToHeadBar = ({ players, metrics, store, generationKey }: Props) => {
  const barData = useMemo(
    () => buildHeadToHeadBarData(players, metrics, store),
    [players, metrics, store, generationKey]
  )

  const options = useMemo<ChartOptions<'bar'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#e3f6e4'
          }
        },
        tooltip: {
          callbacks: {
            label: (ctx: TooltipItem<'bar'>) => `${ctx.dataset.label}: ${ctx.formattedValue}`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#d8f5da' },
          grid: { display: false }
        },
        y: {
          ticks: { color: '#d8f5da' },
          grid: { color: 'rgba(255,255,255,0.05)' }
        }
      }
    }),
    []
  )

  if (!barData) {
    return (
      <div className="h-60 rounded-2xl border border-emerald-400/25 bg-black/30 flex items-center justify-center text-emerald-100/70 text-xs text-center px-4">
        Need two players with recent data to show a head-to-head bar chart.
      </div>
    )
  }

  return (
    <div className="h-60 sm:h-72 rounded-2xl border border-emerald-400/25 bg-black/30 p-3 space-y-2">
      <p className="text-white font-semibold text-sm">Head-to-head snapshot</p>
      <Bar key={`${players.join('-')}-bars-${generationKey}`} data={barData} options={options} />
    </div>
  )
}

export default PlayerHeadToHeadBar
