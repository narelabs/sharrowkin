"use client"

import { useEffect, useRef } from "react"

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  opacity: number
  hue: number
}

export function AgentAuraBackground({
  isActive = false,
  intensity = "medium"
}: {
  isActive?: boolean
  intensity?: "low" | "medium" | "high"
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const animationFrameRef = useRef<number>()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Set canvas size
    const updateSize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    updateSize()
    window.addEventListener("resize", updateSize)

    // Particle count based on intensity
    const particleCount = intensity === "high" ? 80 : intensity === "medium" ? 50 : 30

    // Initialize particles
    particlesRef.current = Array.from({ length: particleCount }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      size: Math.random() * 2 + 1,
      opacity: Math.random() * 0.5 + 0.3,
      hue: Math.random() * 60 + 200, // Blue-purple range
    }))

    // Animation loop
    const animate = () => {
      ctx.fillStyle = "rgba(0, 0, 0, 0.05)"
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      particlesRef.current.forEach((particle, i) => {
        // Update position
        particle.x += particle.vx
        particle.y += particle.vy

        // Bounce off edges
        if (particle.x < 0 || particle.x > canvas.width) particle.vx *= -1
        if (particle.y < 0 || particle.y > canvas.height) particle.vy *= -1

        // Draw particle with glow
        const gradient = ctx.createRadialGradient(
          particle.x, particle.y, 0,
          particle.x, particle.y, particle.size * 4
        )
        gradient.addColorStop(0, `hsla(${particle.hue}, 80%, 60%, ${particle.opacity})`)
        gradient.addColorStop(0.5, `hsla(${particle.hue}, 70%, 50%, ${particle.opacity * 0.5})`)
        gradient.addColorStop(1, `hsla(${particle.hue}, 60%, 40%, 0)`)

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(particle.x, particle.y, particle.size * 4, 0, Math.PI * 2)
        ctx.fill()

        // Draw connections to nearby particles
        if (isActive) {
          particlesRef.current.slice(i + 1).forEach(other => {
            const dx = other.x - particle.x
            const dy = other.y - particle.y
            const distance = Math.sqrt(dx * dx + dy * dy)

            if (distance < 150) {
              const opacity = (1 - distance / 150) * 0.3
              ctx.strokeStyle = `hsla(${particle.hue}, 70%, 60%, ${opacity})`
              ctx.lineWidth = 0.5
              ctx.beginPath()
              ctx.moveTo(particle.x, particle.y)
              ctx.lineTo(other.x, other.y)
              ctx.stroke()
            }
          })
        }
      })

      animationFrameRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      window.removeEventListener("resize", updateSize)
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [isActive, intensity])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0"
      style={{ opacity: 0.4 }}
    />
  )
}
