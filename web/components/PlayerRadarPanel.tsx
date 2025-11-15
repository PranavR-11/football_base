'use client'

import PlayerRadarChart from '@/components/PlayerRadarChart'
import {
  detectPlayersFromText,
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

const PlayerRadarPanel = ({ aiText, generationKey, store, index, loading }: Props) => {
  if (loading || !aiText || !index.length) {
    return null
  }

  const detectedPlayers = detectPlayersFromText(aiText, index, 1)
  const playerName = detectedPlayers[0]
  const hasData = playerName && (store[playerName] || []).length > 0

  return (
    <div className="bg-gradient-to-br from-gray-900/70 via-emerald-950/50 to-black/70 border border-emerald-400/25 rounded-2xl p-4 sm:p-6 shadow-2xl" style={{ backdropFilter: 'blur(16px) saturate(160%)' }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-emerald-200/70 text-[10px] uppercase tracking-[0.4em]">Performance radar</p>
          <h3 className="text-white text-lg font-bold">
            {playerName ? `${playerName} — Season percentiles` : 'Waiting for player context'}
          </h3>
        </div>
      </div>
      {playerName && hasData ? (
        <PlayerRadarChart players={[playerName]} store={store} generationKey={generationKey} />
      ) : (
        <div className="text-emerald-100/70 text-sm">
          Mention a player in your prompt (e.g., "Tell me about Bellingham") to load the radar chart.
        </div>
      )}
    </div>
  )
}

export default PlayerRadarPanel
