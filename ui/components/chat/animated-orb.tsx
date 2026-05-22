"use client"

import type React from "react"

export function AnimatedOrb({
  className,
  variant = "default",
  size = 32,
}: { className?: string; variant?: "default" | "red"; size?: number }) {
  const colors =
    variant === "red"
      ? {
          bg: "#fef2f2",
          circle1: "#ef4444",
          circle2: "#f87171",
          circle3: "#dc2626",
          circle4: "#fca5a5",
          circle5: "#fb7185",
        }
      : {
          bg: "#F7F7F7",
          circle1: "#786EF1",
          circle2: "#5588FB",
          circle3: "#F7B2FB",
          circle4: "#ccd4f2",
          circle5: "#9e9fef",
        }

  const blurAmount = Math.max(8, size * 0.2)
  const circle1Size = size * 0.45
  const circle2Size = size * 0.35
  const circle3Size = size * 0.5
  const circle4Size = size * 0.25
  const circle5Size = size * 0.3

  return (
    <div
      className={`relative rounded-full overflow-hidden ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: colors.bg,
        animation: "floatSlow 5s ease-in-out infinite",
        boxShadow: "0 2px 12px rgba(0,0,0,0.04)",
      }}
      aria-hidden="true"
    >
      {/* Blur container */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={
          {
            "--orb-blur": `${blurAmount}px`,
            filter: `blur(${blurAmount}px)`,
          } as React.CSSProperties
        }
      >
        {/* Circle 1 */}
        <div
          className="orb-circle-1 absolute rounded-full"
          style={{
            width: circle1Size,
            height: circle1Size,
            opacity: 0.85,
            backgroundColor: colors.circle1,
            animation: "floatSlow 4s ease-in-out infinite",
            animationDelay: "0.2s"
          }}
        />
        {/* Circle 2 */}
        <div
          className="orb-circle-2 absolute rounded-full"
          style={{
            width: circle2Size,
            height: circle2Size,
            opacity: 0.8,
            backgroundColor: colors.circle2,
            animation: "floatSlow 4.5s ease-in-out infinite",
            animationDelay: "0.5s"
          }}
        />
        {/* Circle 3 */}
        <div
          className="orb-circle-3 absolute rounded-full"
          style={{
            width: circle3Size,
            height: circle3Size,
            opacity: 0.75,
            backgroundColor: colors.circle3,
            animation: "floatSlow 5.5s ease-in-out infinite",
            animationDelay: "1s"
          }}
        />
        {/* Circle 4 */}
        <div
          className="orb-circle-4 absolute rounded-full"
          style={{
            width: circle4Size,
            height: circle4Size,
            opacity: 0.7,
            backgroundColor: colors.circle4,
            animation: "floatSlow 3.5s ease-in-out infinite",
            animationDelay: "0.8s"
          }}
        />
        {/* Circle 5 */}
        <div
          className="orb-circle-5 absolute rounded-full"
          style={{
            width: circle5Size,
            height: circle5Size,
            opacity: 0.8,
            backgroundColor: colors.circle5,
            animation: "floatSlow 4.2s ease-in-out infinite",
            animationDelay: "0.3s"
          }}
        />
      </div>

      {/* Subtle gradient overlay */}
      <div
        className="absolute inset-0 rounded-full pointer-events-none"
        style={{
          background: "linear-gradient(to bottom, rgba(255, 255, 255, 0.3) 0%, transparent 100%)",
        }}
      />
    </div>
  )
}

