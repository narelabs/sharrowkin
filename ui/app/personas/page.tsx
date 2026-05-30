"use client"

import React, { useState, useEffect, Suspense } from "react"
import { LeftSidebar } from "@/components/chat/left-sidebar"
import { RightSidebar } from "@/components/chat/right-sidebar"
import { Palette, Check, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

interface Persona {
  id: string
  name: string
  description: string
  emoji: string
  colors: {
    primary: string
    secondary: string
    accent: string
  }
  tags: string[]
  preview: string
}

const personas: Persona[] = [
  {
    id: 'mechanicus',
    name: 'Adeptus Mechanicus',
    description: 'Tech-Priest of Mars viewing code as sacred machinery',
    emoji: '⚙️',
    colors: { primary: '#8B0000', secondary: '#B87333', accent: '#FFD700' },
    tags: ['Warhammer 40k', 'Gothic'],
    preview: 'Consulting the sacred logic-vaults of Mars...',
  },
  {
    id: 'cyberpunk',
    name: 'Cyberpunk Netrunner',
    description: 'Rogue AI netrunner jacked into the codebase',
    emoji: '🌐',
    colors: { primary: '#00FFFF', secondary: '#FF1493', accent: '#4B0082' },
    tags: ['Cyberpunk', 'Hacker'],
    preview: 'Jacking into the codebase... scanning netspace...',
  },
  {
    id: 'wizard',
    name: 'Arcane Wizard',
    description: 'Archmage wielding programming languages as spells',
    emoji: '🔮',
    colors: { primary: '#6A0DAD', secondary: '#4169E1', accent: '#FFD700' },
    tags: ['Fantasy', 'Magic'],
    preview: 'Consulting the ancient grimoire... divining the path...',
  },
  {
    id: 'nasa',
    name: 'NASA Mission Control',
    description: 'Flight Director for code deployment missions',
    emoji: '🛰️',
    colors: { primary: '#0B3D91', secondary: '#FFFFFF', accent: '#FF6F00' },
    tags: ['Space', 'NASA'],
    preview: 'Mission Control: Planning trajectory... T-minus 10...',
  },
  {
    id: 'pirate',
    name: 'Pirate Captain',
    description: 'Code Buccaneer sailing the digital seas',
    emoji: '🏴‍☠️',
    colors: { primary: '#006994', secondary: '#FFD700', accent: '#3E2723' },
    tags: ['Pirate', 'Adventure'],
    preview: 'Charting course through the codebase... X marks the spot...',
  },
  {
    id: 'retro',
    name: 'Retro Gaming',
    description: '8-bit Game Master treating code as game levels',
    emoji: '🎮',
    colors: { primary: '#00FF00', secondary: '#FFBF00', accent: '#000000' },
    tags: ['8-bit', 'Gaming'],
    preview: 'Loading level... press START to continue...',
  },
  {
    id: 'scientist',
    name: 'Mad Scientist',
    description: 'Code Alchemist experimenting with formulas',
    emoji: '🧪',
    colors: { primary: '#39FF14', secondary: '#7DF9FF', accent: '#FFFFFF' },
    tags: ['Science', 'Lab'],
    preview: 'Preparing experiment... mixing reagents...',
  },
  {
    id: 'samurai',
    name: 'Samurai Warrior',
    description: 'Code Warrior following the way of Bushido',
    emoji: '⚔️',
    colors: { primary: '#DC143C', secondary: '#000000', accent: '#FFD700' },
    tags: ['Samurai', 'Honor'],
    preview: 'Meditating on the path... the way of the warrior is clear...',
  },
  {
    id: 'matrix',
    name: 'Matrix Hacker',
    description: 'The One seeing through the Matrix',
    emoji: '🕶️',
    colors: { primary: '#00FF41', secondary: '#000000', accent: '#00FF41' },
    tags: ['Matrix', 'Hacker'],
    preview: 'There is no spoon... seeing through the Matrix...',
  },
  {
    id: 'rockstar',
    name: 'Code Rockstar',
    description: 'Rock Legend treating commits as guitar solos',
    emoji: '🎸',
    colors: { primary: '#BF00FF', secondary: '#FF69B4', accent: '#000000' },
    tags: ['Rock', 'Music'],
    preview: 'Tuning the guitar... writing the setlist...',
  },
]

export default function PersonasPage() {
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(false)
  const [selectedPersona, setSelectedPersona] = useState<string>('cyberpunk')

  useEffect(() => {
    const saved = localStorage.getItem('sharrowkin-active-persona')
    if (saved) setSelectedPersona(saved)
  }, [])

  const handleSelectPersona = async (personaId: string) => {
    setSelectedPersona(personaId)
    localStorage.setItem('sharrowkin-active-persona', personaId)

    // Send to backend
    try {
      const response = await fetch(`${BACKEND_URL}/api/personas/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona_id: personaId }),
      })
      const data = await response.json()
      const persona = personas.find(p => p.id === personaId)
      toast.success(`Persona: ${persona?.name || personaId}`)
    } catch (error) {
      toast.error('Failed to activate persona')
    }

    // Dispatch event for other components to update agent name
    window.dispatchEvent(new CustomEvent('persona-changed', { detail: personaId }))
  }

  return (
    <div className="h-full bg-background flex overflow-hidden">
      <Suspense>
        <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />
      </Suspense>

      {/* Main Area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-[#f7f7f9] overflow-hidden">

        {/* Top Header */}
        <div className="h-14 border-b border-stone-200/60 flex items-center justify-between px-8 bg-white/80 backdrop-blur-md z-10 shrink-0">
          <div className="flex items-center gap-2.5 text-stone-850">
            <Palette className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
            <span className="font-medium text-[13px] tracking-wide text-stone-700">Personas</span>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-8 relative">
          <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in duration-300">

            <div className="flex flex-col gap-1">
              <h1 className="text-xl font-light text-stone-800 tracking-tight">Choose Your Persona</h1>
              <p className="text-[13px] text-stone-400 font-light">Customize your agent's personality and interaction style</p>
            </div>

            {/* Personas Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {personas.map((persona) => {
                const isSelected = selectedPersona === persona.id

                return (
                  <button
                    key={persona.id}
                    onClick={() => handleSelectPersona(persona.id)}
                    className={cn(
                      "relative border border-stone-200/60 bg-white rounded-2xl p-5 shadow-[0_1px_8px_rgba(0,0,0,0.01)] transition-all duration-200 text-left group hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)]",
                      isSelected && "ring-2 ring-offset-2"
                    )}
                    style={isSelected ? { borderColor: persona.colors.primary } : undefined}
                  >
                    {/* Selected Badge */}
                    {isSelected && (
                      <div
                        className="absolute -top-2 -right-2 w-6 h-6 rounded-full flex items-center justify-center shadow-sm"
                        style={{ backgroundColor: persona.colors.primary }}
                      >
                        <Check className="text-white" size={14} strokeWidth={3} />
                      </div>
                    )}

                    {/* Emoji Icon */}
                    <div className="text-3xl mb-3">{persona.emoji}</div>

                    {/* Name */}
                    <h3 className="text-[15px] font-medium text-stone-800 mb-1.5">{persona.name}</h3>

                    {/* Description */}
                    <p className="text-[12px] text-stone-500 mb-3 line-clamp-2 font-light leading-relaxed">
                      {persona.description}
                    </p>

                    {/* Tags */}
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {persona.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 font-medium"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* Preview */}
                    {isSelected && (
                      <div className="mt-3 p-2.5 rounded-lg bg-stone-50 border border-stone-100">
                        <p className="text-[11px] font-mono text-stone-600 leading-relaxed">
                          {persona.preview}
                        </p>
                      </div>
                    )}

                    {/* Color Palette */}
                    <div className="flex gap-1.5 mt-3">
                      <div
                        className="w-4 h-4 rounded-full border border-stone-200"
                        style={{ backgroundColor: persona.colors.primary }}
                      />
                      <div
                        className="w-4 h-4 rounded-full border border-stone-200"
                        style={{ backgroundColor: persona.colors.secondary }}
                      />
                      <div
                        className="w-4 h-4 rounded-full border border-stone-200"
                        style={{ backgroundColor: persona.colors.accent }}
                      />
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Info Card */}
            <div className="border border-stone-200/60 bg-white rounded-2xl p-6 shadow-[0_1px_8px_rgba(0,0,0,0.01)] space-y-4">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-stone-400" />
                <h3 className="text-[14px] font-medium text-stone-800">What are Personas?</h3>
              </div>
              <p className="text-[13px] text-stone-500 font-light leading-relaxed">
                Personas customize your Sharrowkin agent with unique themes and interaction styles.
                Each persona changes the visual theme, agent personality, log messages, and sound effects.
              </p>
            </div>
          </div>
        </div>
      </div>

      <Suspense>
        <RightSidebar isOpen={rightSidebarOpen} onToggle={() => setRightSidebarOpen(!rightSidebarOpen)} />
      </Suspense>
    </div>
  )
}
