'use client'

export type PlayerMetricRow = {
  season: number
  goals: number
  assists: number
  xg: number
  npxg?: number
}

export type PlayerMetricsStore = Record<string, PlayerMetricRow[]>

export const playerMetrics: PlayerMetricsStore = {
  'Kylian Mbappe': [
    { season: 2020, goals: 27, assists: 7, xg: 24.1, npxg: 22.4 },
    { season: 2021, goals: 39, assists: 19, xg: 30.2, npxg: 29.1 },
    { season: 2022, goals: 41, assists: 10, xg: 33.4, npxg: 31.7 },
    { season: 2023, goals: 44, assists: 11, xg: 36.8, npxg: 35.4 }
  ],
  'Erling Haaland': [
    { season: 2020, goals: 27, assists: 6, xg: 22.5, npxg: 21.9 },
    { season: 2021, goals: 30, assists: 8, xg: 25.7, npxg: 24.3 },
    { season: 2022, goals: 52, assists: 9, xg: 34.9, npxg: 33.1 },
    { season: 2023, goals: 44, assists: 6, xg: 31.3, npxg: 30.4 }
  ],
  'Lionel Messi': [
    { season: 2020, goals: 31, assists: 26, xg: 28.4, npxg: 26.3 },
    { season: 2021, goals: 38, assists: 21, xg: 30.1, npxg: 28.7 },
    { season: 2022, goals: 21, assists: 21, xg: 18.6, npxg: 17.5 },
    { season: 2023, goals: 26, assists: 20, xg: 20.9, npxg: 19.3 }
  ],
  'Cristiano Ronaldo': [
    { season: 2020, goals: 37, assists: 7, xg: 31.4, npxg: 30.7 },
    { season: 2021, goals: 36, assists: 4, xg: 28.7, npxg: 27.5 },
    { season: 2022, goals: 24, assists: 3, xg: 21.3, npxg: 20.6 },
    { season: 2023, goals: 26, assists: 6, xg: 23.8, npxg: 22.1 }
  ],
  'Jude Bellingham': [
    { season: 2020, goals: 4, assists: 4, xg: 3.2, npxg: 3.1 },
    { season: 2021, goals: 6, assists: 14, xg: 6.5, npxg: 6.1 },
    { season: 2022, goals: 14, assists: 10, xg: 11.7, npxg: 11.2 },
    { season: 2023, goals: 22, assists: 10, xg: 16.4, npxg: 15.2 }
  ]
}

export const defaultPlayer = Object.keys(playerMetrics)[0]
