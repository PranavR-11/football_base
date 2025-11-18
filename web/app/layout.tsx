import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Football Analytics AI',
  description: 'AI-powered football analytics and player comparisons',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <script async src="https://plausible.io/js/pa-TKCowpKpDmj6Q5pX1UTQy.js"></script>
        <script dangerouslySetInnerHTML={{ __html: `
          window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};
          plausible.init()
        `}} />
      </head>
      <body>{children}</body>
    </html>
  )
}
