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

const convertAllCapsToHeaders = (text: string) => {
  // Split by lines and detect all-caps headings
  const lines = text.split('\n')
  const processed = lines.map(line => {
    const trimmed = line.trim()
    // Check if line is all caps (allowing spaces, numbers, and common punctuation)
    // Must be at least 3 chars and mostly uppercase letters
    if (trimmed.length >= 3 && /^[A-Z0-9\s\-:&]+$/.test(trimmed) && /[A-Z]{3,}/.test(trimmed)) {
      // Don't convert if it's part of a sentence (has lowercase after it in the same line)
      // Convert to markdown heading
      return `## ${trimmed}`
    }
    return line
  })
  return processed.join('\n')
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
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          h1: ({ children, ...props }) => (
            <h1 className="text-emerald-300 font-extrabold text-2xl mt-4 mb-2" {...props}>
              {children}
            </h1>
          ),
          h2: ({ children, ...props }) => (
            <h2 className="text-emerald-300 font-extrabold text-xl mt-4 mb-2" {...props}>
              {children}
            </h2>
          ),
          h3: ({ children, ...props }) => (
            <h3 className="text-emerald-300 font-extrabold text-lg mt-3 mb-1" {...props}>
              {children}
            </h3>
          ),
          p: ({ children, ...props }) => (
            <p className="text-gray-100 text-sm sm:text-base leading-relaxed mb-3" {...props}>
              {children}
            </p>
          ),
          ul: ({ children, ...props }) => (
            <ul className="list-disc list-inside space-y-1 text-sm sm:text-base text-gray-100 mb-3" {...props}>
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol className="list-decimal list-inside space-y-1 text-sm sm:text-base text-gray-100 mb-3" {...props}>
              {children}
            </ol>
          ),
          li: ({ children, ...props }) => (
            <li className="pl-1" {...props}>
              {children}
            </li>
          ),
          strong: ({ children, ...props }) => (
            <strong className="text-white font-semibold" {...props}>
              {children}
            </strong>
          ),
          em: ({ children, ...props }) => (
            <em className="text-gray-200 italic" {...props}>
              {children}
            </em>
          )
        }}
      >
        {unescapeMarkdown(convertAllCapsToHeaders(message ?? ''))}
      </ReactMarkdown>
    </div>
  )
}

export default MessageViewer
