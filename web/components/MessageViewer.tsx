'use client'

import { useEffect, useRef } from 'react'
import clsx from 'clsx'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'

type MessageViewerProps = {
  message?: string
  scrollKey?: string | number | null
  forceScrollToStart?: boolean
  preserveIfUserScrolledUp?: boolean
  className?: string
}

const unescapeMarkdown = (text: string) =>
  text
    .replace(/\\\*/g, '*')
    .replace(/\\_/g, '_')
    .replace(/\\#/g, '#')

const MessageViewer = ({
  message = '',
  scrollKey,
  forceScrollToStart = true,
  preserveIfUserScrolledUp = false,
  className
}: MessageViewerProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const topAnchorRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!forceScrollToStart || !scrollKey) return
    const container = containerRef.current
    if (!container) return

    if (preserveIfUserScrolledUp && container.scrollTop > 40) {
      return
    }

    if (topAnchorRef.current) {
      topAnchorRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else {
      container.scrollTop = 0
    }
  }, [scrollKey, forceScrollToStart, preserveIfUserScrolledUp])

  return (
    <div
      ref={containerRef}
      className={clsx('modal-markdown-container', className)}
      role="article"
      aria-live="polite"
    >
      <div ref={topAnchorRef} style={{ position: 'relative', top: '-8px', height: 1 }} />
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {unescapeMarkdown(message ?? '')}
      </ReactMarkdown>
    </div>
  )
}

export default MessageViewer
