'use client'

import PlayerTimeSeriesChart from '@/components/PlayerTimeSeriesChart'
import PlayerRadarChart from '@/components/PlayerRadarChart'
import {
  detectMetricFromText,
  detectPlayersFromText,
  isSinglePlayerQuery,
  PlayerIndexEntry,
  PlayerMetricsStore
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

  const players = detectPlayersFromText(aiText, index, 2)
  if (!players.length) {
    return null
  }

  const metric = detectMetricFromText(aiText)
  const singlePlayer = isSinglePlayerQuery(aiText)

  return (
    <div className="mt-6 space-y-4">
      <div className="bg-gradient-to-br from-gray-900/85 via-emerald-900/70 to-black/70 border border-emerald-400/25 rounded-2xl p-5 sm:p-6 shadow-2xl">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="text-emerald-300/70 text-[10px] uppercase tracking-[0.5em]">
              Intelligent Graphs
            </p>
            <h3 className="text-white text-lg sm:text-xl font-bold">
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

        <div className="mt-5 grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <PlayerTimeSeriesChart
              players={players}
              metric={metric}
              store={store}
              generationKey={generationKey}
            />
          </div>
          <div className="lg:col-span-2">
            {singlePlayer ? (
              <PlayerRadarChart player={players[0]} store={store} generationKey={generationKey} />
            ) : (
              <div className="h-full rounded-2xl border border-emerald-400/20 flex items-center justify-center text-emerald-100/70 text-xs text-center px-4">
                Radar view available for single-player insights. Ask about one player to unlock a
                positional radar.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default PlayerInsightsPanel
'
