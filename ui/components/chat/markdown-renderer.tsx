"use client"

import { cn } from "@/lib/utils"
import type React from "react"
import { useState, useEffect, useRef } from "react"
import { AnalysisWordSpan } from "./analysis-word-span"

interface MarkdownRendererProps {
  content: string
  className?: string
  isStreaming?: boolean
}

export function MarkdownRenderer({ content, className, isStreaming = false }: MarkdownRendererProps) {
  const [staticContent, setStaticContent] = useState("")
  const [animatingContent, setAnimatingContent] = useState("")
  const staticLengthRef = useRef(0)

  useEffect(() => {
    if (!isStreaming) {
      setStaticContent(content)
      staticLengthRef.current = content.length
      setAnimatingContent("")
      return
    }

    const currentStaticLength = staticLengthRef.current
    const rawAnimating = content.slice(currentStaticLength)

    if (rawAnimating.length > 200) {
      // Move first 150 chars to static (finding a word boundary)
      const cutPoint = rawAnimating.lastIndexOf(" ", 150)
      if (cutPoint > 50) {
        const nextStaticChunk = rawAnimating.slice(0, cutPoint + 1)
        const nextAnimating = rawAnimating.slice(cutPoint + 1)
        
        setStaticContent((prev) => prev + nextStaticChunk)
        staticLengthRef.current = currentStaticLength + nextStaticChunk.length
        setAnimatingContent(nextAnimating)
        return
      }
    }

    setAnimatingContent(rawAnimating)
  }, [content, isStreaming])

  const renderPlainInlineMarkdown = (text: string) => {
    const elements: (string | React.ReactNode)[] = []
    let remaining = text
    let keyIndex = 0

    while (remaining.length > 0) {
      // Check for inline code
      const codeMatch = remaining.match(/^`([^`]+)`/)
      if (codeMatch) {
        elements.push(
          <code key={keyIndex++} className="px-1.5 py-0.5 bg-stone-100 text-stone-700 rounded text-sm font-mono">
            {codeMatch[1]}
          </code>,
        )
        remaining = remaining.slice(codeMatch[0].length)
        continue
      }

      // Check for bold
      const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/)
      if (boldMatch) {
        elements.push(<strong key={keyIndex++}>{boldMatch[1]}</strong>)
        remaining = remaining.slice(boldMatch[0].length)
        continue
      }

      // Check for italic
      const italicMatch = remaining.match(/^\*([^*]+)\*/)
      if (italicMatch) {
        elements.push(<em key={keyIndex++}>{italicMatch[1]}</em>)
        remaining = remaining.slice(italicMatch[0].length)
        continue
      }

      // Check for links
      const linkMatch = remaining.match(/^\[([^\]]+)\]$$([^)]+)$$/)
      if (linkMatch) {
        elements.push(
          <a
            key={keyIndex++}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-600 hover:text-emerald-700 underline underline-offset-2 transition-colors"
          >
            {linkMatch[1]}
          </a>,
        )
        remaining = remaining.slice(linkMatch[0].length)
        continue
      }

      // Find next special character or add remaining text
      const nextSpecial = remaining.search(/[`*[\]()]/)
      if (nextSpecial === -1) {
        elements.push(remaining)
        break
      } else if (nextSpecial === 0) {
        elements.push(remaining[0])
        remaining = remaining.slice(1)
      } else {
        elements.push(remaining.slice(0, nextSpecial))
        remaining = remaining.slice(nextSpecial)
      }
    }

    return elements
  }

  const renderAnimatedInlineMarkdown = (text: string) => {
    const elements: (string | React.ReactNode)[] = []
    let remaining = text
    let keyIndex = 0

    while (remaining.length > 0) {
      // Check for inline code
      const codeMatch = remaining.match(/^`([^`]+)`/)
      if (codeMatch) {
        elements.push(
          <code key={keyIndex++} className="px-1.5 py-0.5 bg-stone-100 text-stone-700 rounded text-sm font-mono">
            {codeMatch[1]}
          </code>,
        )
        remaining = remaining.slice(codeMatch[0].length)
        continue
      }

      // Check for bold
      const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/)
      if (boldMatch) {
        const words = boldMatch[1].split(/(\s+)/)
        elements.push(
          <strong key={keyIndex++}>
            {words.map((word, i) => {
              if (word.match(/\s+/)) return word
              if (!word) return null
              return <AnalysisWordSpan key={`b-${keyIndex}-${i}`} word={word} />
            })}
          </strong>,
        )
        remaining = remaining.slice(boldMatch[0].length)
        continue
      }

      // Check for italic
      const italicMatch = remaining.match(/^\*([^*]+)\*/)
      if (italicMatch) {
        const words = italicMatch[1].split(/(\s+)/)
        elements.push(
          <em key={keyIndex++}>
            {words.map((word, i) => {
              if (word.match(/\s+/)) return word
              if (!word) return null
              return <AnalysisWordSpan key={`i-${keyIndex}-${i}`} word={word} />
            })}
          </em>,
        )
        remaining = remaining.slice(italicMatch[0].length)
        continue
      }

      // Check for links
      const linkMatch = remaining.match(/^\[([^\]]+)\]$$([^)]+)$$/)
      if (linkMatch) {
        elements.push(
          <a
            key={keyIndex++}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-600 hover:text-emerald-700 underline underline-offset-2 transition-colors"
          >
            {linkMatch[1]}
          </a>,
        )
        remaining = remaining.slice(linkMatch[0].length)
        continue
      }

      // Find next special character or add remaining text
      const nextSpecial = remaining.search(/[`*[\]()]/)
      if (nextSpecial === -1) {
        const words = remaining.split(/(\s+)/)
        elements.push(
          ...words.map((word, i) => {
            if (word.match(/\s+/)) return word
            if (!word) return null
            return <AnalysisWordSpan key={`w-${keyIndex++}-${i}`} word={word} />
          }),
        )
        break
      } else if (nextSpecial === 0) {
        elements.push(remaining[0])
        remaining = remaining.slice(1)
      } else {
        const textPart = remaining.slice(0, nextSpecial)
        const words = textPart.split(/(\s+)/)
        elements.push(
          ...words.map((word, i) => {
            if (word.match(/\s+/)) return word
            if (!word) return null
            return <AnalysisWordSpan key={`t-${keyIndex++}-${i}`} word={word} />
          }),
        )
        remaining = remaining.slice(nextSpecial)
      }
    }

    return elements
  }

  const renderCodeBlock = (part: string, partIndex: number) => {
    const codeContent = part.slice(3, -3)
    const firstNewline = codeContent.indexOf("\n")
    const language = firstNewline > 0 ? codeContent.slice(0, firstNewline).trim() : ""
    const code = firstNewline > 0 ? codeContent.slice(firstNewline + 1) : codeContent

    const isDiff = language.toLowerCase() === "diff"

    return (
      <pre
        key={partIndex}
        className="my-3 p-4 bg-stone-50 border border-stone-200/60 rounded-2xl overflow-x-auto text-[13px] font-mono shadow-[0_1px_3px_rgba(0,0,0,0.01)] text-stone-600 leading-relaxed"
      >
        {language && (
          <span className="text-[11px] font-medium text-stone-400 font-sans block mb-2.5">
            {language === "diff" ? "Diff Output" : language}
          </span>
        )}
        <code>
          {isDiff ? (
            code.split("\n").map((line, i) => {
              const isAdded = line.startsWith("+")
              const isRemoved = line.startsWith("-")
              const isHeader = line.startsWith("@@") || line.startsWith("diff")

              return (
                <div
                  key={i}
                  className={cn(
                    "px-2 py-0.5 rounded my-0.5 font-mono",
                    isAdded && "text-emerald-700 bg-emerald-50/70 font-medium",
                    isRemoved && "text-red-600 bg-red-50/45 line-through decoration-red-200",
                    isHeader && "text-blue-500 font-semibold bg-blue-50/30"
                  )}
                >
                  {line}
                </div>
              )
            })
          ) : (
            code
          )}
        </code>
      </pre>
    )
  }

  const renderContent = (text: string, animated: boolean) => {
    if (!text) return null

    // Split by code blocks first
    const parts = text.split(/(```[\s\S]*?```)/g)

    return parts.map((part, partIndex) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        return renderCodeBlock(part, partIndex)
      }

      if (animated) {
        return <span key={partIndex}>{renderAnimatedInlineMarkdown(part)}</span>
      }

      return <span key={partIndex}>{renderPlainInlineMarkdown(part)}</span>
    })
  }

  return (
    <div className={cn("text-sm whitespace-pre-wrap break-words", className)}>
      {renderContent(staticContent, false)}
      {renderContent(animatingContent, true)}
    </div>
  )
}
