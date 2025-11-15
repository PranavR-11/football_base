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
  Legend
} from 'chart.js'
import type { ChartOptions, TooltipItem } from 'chart.js'
import { Line } from 'react-chartjs-2'
import {
  buildLineChartData,
  getMetricLabel,
  MetricKey,
  PlayerMetricsStore
} from '@/lib/playerMetrics'

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend)

type Props = {
  players: string[]
  metric: MetricKey
  store: PlayerMetricsStore
  generationKey: number
  title?: string
  subtitle?: string
}

const PlayerTimeSeriesChart = ({ players, metric, store, generationKey, title, subtitle }: Props) => {
  const hasData = players.some((player) => (store[player] || []).length > 0)

  const chartData = useMemo(() => {
    if (!hasData) {
      return { labels: [], datasets: [] }
    }
    return buildLineChartData(players, metric, store)
  }, [players, metric, store, hasData, generationKey])

  const options = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#cfe8d8' }
        },
        y: {
          ticks: { color: '#cfe8d8' },
          grid: {
            color: 'rgba(255,255,255,0.06)'
          }
        }
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: '#f0fff4',
            boxWidth: 16,
            padding: 12
          }
        },
        tooltip: {
          callbacks: {
            label: (ctx: TooltipItem<'line'>) =>
              `${ctx.dataset.label}: ${ctx.formattedValue}`.trim()
          }
        }
      }
    }),
    []
  )

  if (!hasData) {
    return (
      <div className="h-72 rounded-2xl border border-emerald-400/25 bg-black/30 flex items-center justify-center text-emerald-100/70 text-sm text-center px-4">
        Mention a player included in the dataset to see trend lines for any stat.
      </div>
    )
  }

  return (
    <div className="h-72 sm:h-80 rounded-2xl border border-emerald-400/25 bg-black/30 p-3 space-y-2">
      {title && (
        <div>
          <p className="text-emerald-200/70 text-[10px] uppercase tracking-[0.4em]">{subtitle}</p>
          <h4 className="text-white font-bold text-base sm:text-lg">{title}</h4>
        </div>
      )}
      <Line
        key={`${players.join('-')}-${metric}-${generationKey}`}
        data={chartData}
        options={options}
      />
      <p className="text-emerald-100/70 text-xs mt-2 text-right">
        Showing {getMetricLabel(metric)} across seasons
      </p>
    </div>
  )
}

export default PlayerTimeSeriesChart
