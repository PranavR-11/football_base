'use client'

import PlayerTimeSeriesChart from '@/components/PlayerTimeSeriesChart'
import PlayerRadarChart from '@/components/PlayerRadarChart'
import PlayerHeadToHeadBar from '@/components/PlayerHeadToHeadBar'
import {
  detectMetricFromText,
  detectPlayersFromText,
  isSinglePlayerQuery,
  PlayerIndexEntry,
  PlayerMetricsStore,
  DEFAULT_COMPARISON_METRICS,
  filterPlayersWithData,
  getMetricLabel
} from '@/lib/playerMetrics'

type Props = {
  aiText?: string
  generationKey: number
  store: PlayerMetricsStore
  index: PlayerIndexEntry[]
  loading: boolean
}

const PlayerInsightsPanel = ({ aiText, generationKey, store, index, loading }: Props) => {
  if (!aiText || loading || !index.length) {
    return null
  }

  const detectedPlayers = detectPlayersFromText(aiText, index, 3)
  const players = filterPlayersWithData(detectedPlayers, store).slice(0, 3)
  if (!players.length) {
    return null
  }

  const metric = detectMetricFromText(aiText)
  const singlePlayer = players.length === 1 || isSinglePlayerQuery(aiText)
  const comparedPlayers = players.slice(0, singlePlayer ? 1 : 2)
  const secondaryMetrics = DEFAULT_COMPARISON_METRICS.filter(
    (m) => m !== metric && m !== 'goals_assists_per_90'
  )
  const comparisonMetrics = [metric, ...secondaryMetrics].reduce<MetricKey[]>((acc, item) => {
    if (!acc.includes(item)) acc.push(item)
    return acc
  }, [])
  const chartsToShow = singlePlayer ? comparisonMetrics.slice(0, 1) : comparisonMetrics.slice(0, 2)

  return (
    <div className="mt-6 space-y-4 theme-default">
      <div
        className="bg-gradient-to-br from-gray-900/70 via-emerald-950/50 to-black/70 border border-emerald-400/25 rounded-2xl p-5 sm:p-6 shadow-2xl"
        style={{ backdropFilter: 'blur(20px) saturate(160%)' }}
      >
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="text-emerald-200/70 text-[10px] uppercase tracking-[0.5em]">
              Intelligent Graphs
            </p>
            <h3 className="text-emerald-200 text-lg sm:text-xl font-bold">
              {singlePlayer ? 'Player spotlight' : 'Comparison trendlines'}
            </h3>
            <p className="text-emerald-100/70 text-xs sm:text-sm mt-1 max-w-2xl">
              Charts refresh automatically using the AI response — every mention of a player or stat
              updates this panel instantly.
            </p>
          </div>
          <div className="text-emerald-200 text-xs font-semibold bg-emerald-900/60 border border-emerald-400/40 rounded-full px-4 py-1">
            Live data
          </div>
        </div>

        <div className="mt-5 space-y-4">
          <div className={`grid gap-4 ${singlePlayer ? '' : 'lg:grid-cols-2'}`}>
            {chartsToShow.map((chartMetric, index) => (
              <PlayerTimeSeriesChart
                key={`${chartMetric}-${index}`}
                players={comparedPlayers}
                metric={chartMetric}
                store={store}
                generationKey={generationKey}
                title={
                  singlePlayer && index === 0
                    ? `${players[0]} — ${getMetricLabel(chartMetric)}`
                    : `${chartMetric === metric ? 'Primary metric' : 'Secondary trend'}`
                }
                subtitle={chartMetric === metric ? 'AI-detected focus' : 'Context signal'}
              />
            ))}
          </div>

          <div className={`grid gap-4 ${singlePlayer ? 'lg:grid-cols-2' : 'lg:grid-cols-2'}`}>
            <PlayerRadarChart
              players={singlePlayer ? [players[0]] : comparedPlayers}
              store={store}
              generationKey={generationKey}
            />
            {singlePlayer ? (
              <div className="rounded-2xl border border-emerald-400/25 bg-black/30 p-4 text-sm text-emerald-100/80">
                Ask about another player (e.g., “compare {players[0]} and Haaland”) to unlock
                head-to-head charts and Bars.
              </div>
            ) : (
              <PlayerHeadToHeadBar
                players={comparedPlayers}
                metrics={DEFAULT_COMPARISON_METRICS}
                store={store}
                generationKey={generationKey}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default PlayerInsightsPanel
