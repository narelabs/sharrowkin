"use client"

import type React from "react"
import { useState, useRef, useCallback, type KeyboardEvent, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Square, Mic, MicOff, X, Sparkles, Plus, Rocket, Check, ChevronDown, ArrowRight, Search, Plug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuPortal,
} from "@/components/ui/dropdown-menu"
import Image from "next/image"
import { AudioWaveform } from "./audio-waveform"
import { WorkspaceSelector } from "./workspace-selector"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

// Map a provider-prefixed model id (e.g. "google/gemini-2.5-flash") to the
// provider key returned by /api/keys ({ providers: { google: true, ... } }).
function modelProvider(modelId: string): string {
  return modelId.split("/")[0] || ""
}

export type AIModel =
  | "google/gemini-2.5-flash"
  | "google/gemini-2.5-pro"
  | "openai/gpt-4o"
  | "openai/o3-mini"
  | "anthropic/claude-sonnet-4"

export const AI_MODELS: { id: AIModel; name: string; icon: string }[] = [
  { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash", icon: "/images/google.webp" },
  { id: "google/gemini-2.5-pro", name: "Gemini 2.5 Pro", icon: "/images/google.webp" },
  { id: "openai/gpt-4o", name: "GPT-4o", icon: "/images/gpt.png" },
  { id: "openai/o3-mini", name: "o3-mini Reasoning", icon: "/images/gpt.png" },
  { id: "anthropic/claude-sonnet-4", name: "Claude Sonnet 4", icon: "/images/claude.svg" },
]

interface ComposerProps {
  onSend: (content: string, imageData?: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
  selectedModel: AIModel
  onModelChange: (model: AIModel) => void
  bottomOffset?: number
  planMode: PlanMode
  onPlanModeChange: (mode: PlanMode) => void
  workspace: string | null
  onWorkspaceChange: (path: string) => void
}

const PLAN_MODES = [
  {
    id: "autonomous" as const,
    title: "Autonomous",
    description: "Scan, plan, write, and heal code with zero manual oversight.",
    icon: Rocket,
  },
  {
    id: "interactive" as const,
    title: "Interactive",
    description: "Collaborative plan generation, feedback, and interactive approval.",
    icon: Sparkles,
  },
  {
    id: "analyze" as const,
    title: "Analyze Only",
    description: "Read the codebase, explain architecture, and answer without editing files.",
    icon: Search,
  },
]

type PlanMode = "autonomous" | "interactive" | "analyze"

const QUICK_ACTIONS: Array<{ label: string; prompt: string; mode?: PlanMode }> = [
  { label: "Autonomous fix", prompt: "Найди и исправь проблему автономно: изучи код, внеси минимальный патч и запусти проверку." },
  { label: "Improve UI", prompt: "Улучши UI: найди слабые места интерфейса, добавь полезную фичу и проверь сборку." },
  { label: "Explain project", prompt: "Изучи проект и кратко объясни архитектуру, ключевые модули и что улучшить дальше.", mode: "analyze" as const },
]

const AUTONOMY_SIGNALS = ["infer defaults", "edit directly", "run checks"]

export function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  selectedModel,
  onModelChange,
  bottomOffset,
  planMode,
  onPlanModeChange,
  workspace,
  onWorkspaceChange,
}: ComposerProps) {
  const router = useRouter()
  const [value, setValue] = useState("")
  const [isRecording, setIsRecording] = useState(false)
  const [uploadedImage, setUploadedImage] = useState<string | null>(null)
  const [showImageBounce, setShowImageBounce] = useState(false)
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)
  const [providers, setProviders] = useState<Record<string, boolean>>({})
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<any>(null)
  const baseTextRef = useRef("")
  const finalTranscriptsRef = useRef("")

  // Which LLM providers have an API key configured (from /api/keys).
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/keys`)
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setProviders(data.providers || {})
      } catch {}
    }
    load()
    // Refresh when returning from the settings page.
    const onFocus = () => load()
    window.addEventListener("focus", onFocus)
    return () => {
      cancelled = true
      window.removeEventListener("focus", onFocus)
    }
  }, [])

  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SpeechRecognition) {
        recognitionRef.current = new SpeechRecognition()
        recognitionRef.current.continuous = true
        recognitionRef.current.interimResults = true
        recognitionRef.current.lang = "en-US"

        recognitionRef.current.onresult = (event: any) => {
          let newFinalText = ""

          for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
              const transcript = event.results[i][0].transcript
              newFinalText += transcript + " "
            }
          }

          if (newFinalText) {
            finalTranscriptsRef.current += newFinalText
            setValue(baseTextRef.current + finalTranscriptsRef.current)
            setTimeout(() => handleInput(), 0)
          }
        }

        recognitionRef.current.onerror = (event: any) => {
          console.error("[v0] Speech recognition error:", event.error)
          setIsRecording(false)
        }

        recognitionRef.current.onend = () => {
          setIsRecording(false)
        }
      }
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop()
      }
    }
  }, [])

  const playClickSound = useCallback(() => {
    // Interface sounds are intentionally disabled for a calm professional workspace.
  }, [])

  const toggleRecording = useCallback(() => {
    playClickSound()

    if (!recognitionRef.current) {
      alert("Speech recognition is not supported in your browser")
      return
    }

    if (isRecording) {
      recognitionRef.current.stop()
      setIsRecording(false)
      if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop())
        setMediaStream(null)
      }
    } else {
      baseTextRef.current = value
      finalTranscriptsRef.current = ""
      recognitionRef.current.start()
      setIsRecording(true)

      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
          setMediaStream(stream)
        })
        .catch((err) => {
          console.error("Error getting microphone stream:", err)
        })
    }
  }, [isRecording, value, playClickSound, mediaStream])

  const handleInput = useCallback(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = "auto"
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [])

  useEffect(() => {
    const handleInsertPrompt = (e: Event) => {
      const customEvent = e as CustomEvent<string>
      if (customEvent.detail) {
        setValue((prev) => (prev ? prev + "\n\n" + customEvent.detail : customEvent.detail))
        setTimeout(() => handleInput(), 0)
      }
    }
    // Submit a prompt straight into the chat (same flow as pressing send), so
    // features like the preview "Copy" action actually start the agent with
    // the normal thinking/streaming UI instead of just pre-filling the box.
    const handleSubmitPrompt = (e: Event) => {
      const customEvent = e as CustomEvent<string>
      const text = customEvent.detail?.trim()
      if (!text) return
      if (isStreaming || disabled || !workspace) {
        // Can't send right now — fall back to inserting so nothing is lost.
        setValue((prev) => (prev ? prev + "\n\n" + text : text))
        setTimeout(() => handleInput(), 0)
        return
      }
      playClickSound()
      onSend(text)
      setValue("")
      baseTextRef.current = ""
      finalTranscriptsRef.current = ""
      if (textareaRef.current) textareaRef.current.style.height = "auto"
    }
    window.addEventListener("sharrowkin-insert-prompt", handleInsertPrompt)
    window.addEventListener("sharrowkin-submit-prompt", handleSubmitPrompt)
    return () => {
      window.removeEventListener("sharrowkin-insert-prompt", handleInsertPrompt)
      window.removeEventListener("sharrowkin-submit-prompt", handleSubmitPrompt)
    }
  }, [handleInput, isStreaming, disabled, workspace, onSend, playClickSound])

  const handleSend = useCallback(() => {
    if ((!value.trim() && !uploadedImage) || isStreaming || disabled) return
    if (!workspace) return
    playClickSound()

    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop()
      setIsRecording(false)
    }
    onSend(value || "Describe this image", uploadedImage || undefined)
    setValue("")
    setUploadedImage(null)
    baseTextRef.current = ""
    finalTranscriptsRef.current = ""
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }, [value, uploadedImage, isStreaming, disabled, onSend, isRecording, playClickSound, workspace])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      playClickSound()

      const file = e.target.files?.[0]
      if (file && file.type.startsWith("image/")) {
        const reader = new FileReader()
        reader.onload = (event) => {
          setUploadedImage(event.target?.result as string)
          setShowImageBounce(true)
          setTimeout(() => setShowImageBounce(false), 400)
        }
        reader.readAsDataURL(file)
      }
      e.target.value = ""
    },
    [playClickSound],
  )

  const removeImage = useCallback(() => {
    setUploadedImage(null)
  }, [])

  const currentModel = AI_MODELS.find((m) => m.id === selectedModel) || AI_MODELS[0]
  // True once we've loaded /api/keys and the selected model's provider has a key.
  const keysLoaded = Object.keys(providers).length > 0
  const currentModelConnected = providers[modelProvider(currentModel.id)] === true
  const selectedModeObj = PLAN_MODES.find((m) => m.id === planMode) || PLAN_MODES[0]
  const SelectedIcon = selectedModeObj.icon
  const modePlaceholder = planMode === "autonomous"
    ? "Describe the goal — the agent will decide, edit, and verify..."
    : planMode === "analyze"
      ? "Ask for architecture, code review, or repository analysis..."
      : "Ask the agent to build, fix, or analyze..."

  return (
    <div
      className="absolute left-0 right-0 px-4 pointer-events-none z-10 transition-all duration-300"
      style={{ bottom: bottomOffset !== undefined ? `${bottomOffset}px` : "24px" }}
    >
      <div className="relative max-w-3xl mx-auto pointer-events-auto">
        <div
          className={cn(
            "flex flex-col bg-white/95 backdrop-blur-sm border border-stone-200/40 transition-all duration-300 relative rounded-[28px] overflow-hidden",
            "focus-within:border-stone-300/60 focus-within:shadow-[0_4px_24px_rgba(0,0,0,0.06)]",
            "shadow-[0_2px_12px_rgba(0,0,0,0.03)]"
          )}
        >
          {/* Uploaded Image Preview */}
          {uploadedImage && (
            <div className={cn("px-4 pt-4 pb-0 transition-all", showImageBounce && "image-bounce")}>
              <div className="relative inline-block">
                <div className="w-16 h-16 rounded-xl overflow-hidden">
                  <Image
                    src={uploadedImage || "/placeholder.svg"}
                    alt="Uploaded image"
                    width={64}
                    height={64}
                    className="w-full h-full object-cover"
                  />
                </div>
                <button
                  onClick={removeImage}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-stone-100/90 text-stone-500 hover:bg-stone-200 rounded-full flex items-center justify-center transition-colors"
                  aria-label="Remove image"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}

          {/* Autonomy signals removed */}

          {!value.trim() && !uploadedImage && !isStreaming && !disabled && (
            <div className="px-4 pt-3 pb-0 flex flex-wrap gap-1.5">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => {
                    playClickSound()
                    if (action.mode) onPlanModeChange(action.mode)
                    setValue(action.prompt)
                    setTimeout(() => handleInput(), 0)
                  }}
                  className="rounded-full bg-stone-100/60 px-3.5 py-1.5 text-[12.5px] font-normal text-stone-500 transition-all duration-200 hover:bg-stone-100 hover:text-stone-800 hover:-translate-y-[1px] hover:shadow-[0_2px_8px_rgba(0,0,0,0.06)] active:scale-[0.98]"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

          {/* Text Input Area */}
          <div className="flex px-4 pt-3 pb-1">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => {
                setValue(e.target.value)
                handleInput()
              }}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? "Listening..." : modePlaceholder}
              disabled={isStreaming || disabled}
              rows={1}
              className={cn(
                "flex-1 resize-none bg-transparent py-1.5 text-[15px] font-normal text-stone-800 placeholder:text-stone-400/80 leading-relaxed",
                "focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed",
                "max-h-[200px] overflow-y-auto no-scrollbar",
              )}
              aria-label="Message input"
            />
          </div>

          {/* Bottom Toolbar */}
          <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
            <div className="flex min-w-0 items-center gap-1">

              {/* Attachment Button */}
              <Button
                onClick={() => {
                  playClickSound()
                  fileInputRef.current?.click()
                }}
                disabled={isStreaming || disabled}
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-full text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-colors"
                aria-label="Attach file"
              >
                <Plus strokeWidth={2} className="w-[18px] h-[18px]" />
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
                aria-label="Upload image"
              />

              {/* Model Dropdown — or "Connect API" when the provider has no key */}
              {keysLoaded && !currentModelConnected ? (
                <Button
                  variant="ghost"
                  disabled={isStreaming || disabled}
                  onClick={() => {
                    playClickSound()
                    router.push("/settings?tab=general")
                  }}
                  title="No API key for this provider — open settings to connect"
                  className="h-8 px-2.5 rounded-full text-amber-700 bg-amber-50 hover:bg-amber-100 hover:text-amber-800 transition-colors flex items-center gap-1.5 font-medium text-[12px]"
                >
                  <Plug strokeWidth={1.8} className="w-[14px] h-[14px]" />
                  <span>Connect API</span>
                </Button>
              ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    disabled={isStreaming || disabled}
                    className="h-8 px-2.5 rounded-full text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-colors flex items-center gap-1.5 font-medium text-[12px]"
                    onClick={playClickSound}
                  >
                    {currentModel.icon ? (
                      <Image
                        src={currentModel.icon}
                        alt={currentModel.name}
                        width={14}
                        height={14}
                        className="rounded-sm object-contain shrink-0"
                      />
                    ) : (
                      <Sparkles strokeWidth={2} className="w-[14px] h-[14px]" />
                    )}
                    <span>{currentModel.name}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuContent
                    align="start"
                    side="top"
                    sideOffset={12}
                    className="w-44 p-1.5 rounded-[16px] border border-stone-100/50 shadow-lg bg-white/95 backdrop-blur-xl z-[9999]"
                  >
                    {AI_MODELS.map((model) => {
                      const connected = providers[modelProvider(model.id)] === true
                      return (
                      <DropdownMenuItem
                        key={model.id}
                        onClick={() => {
                          playClickSound()
                          onModelChange(model.id)
                        }}
                        className={cn(
                          "flex items-center cursor-pointer gap-2.5 rounded-[10px] px-2.5 py-2 text-[13px] text-stone-700 transition-colors outline-none",
                          "focus:!bg-stone-50/80 focus:!text-stone-900 data-[highlighted]:!bg-stone-50/80 data-[highlighted]:!text-stone-900",
                          selectedModel === model.id ? "bg-stone-100 font-medium text-stone-900" : "hover:bg-stone-50"
                        )}
                      >
                        <Image
                          src={model.icon || "/placeholder.svg"}
                          alt={model.name}
                          width={16}
                          height={16}
                          className="rounded-sm object-contain"
                        />
                        <span className="flex-1">{model.name}</span>
                        {keysLoaded && (
                          <span
                            title={connected ? "API key configured" : "No API key for this provider"}
                            className={cn(
                              "h-1.5 w-1.5 shrink-0 rounded-full",
                              connected ? "bg-emerald-500" : "bg-stone-300"
                            )}
                          />
                        )}
                      </DropdownMenuItem>
                      )
                    })}
                  </DropdownMenuContent>
                </DropdownMenuPortal>
              </DropdownMenu>
              )}

              {/* Working folder selector (chat-style, inline) */}
              <div className="mx-0.5 h-4 w-px bg-stone-200/70" />
              <WorkspaceSelector
                workspace={workspace}
                onSelect={onWorkspaceChange}
                disabled={isStreaming || disabled}
              />
            </div>

            <div className="flex items-center gap-2">
              {/* Audio visualizer */}
              {isRecording && (
                <div className="shrink-0 w-20 mr-2">
                  <AudioWaveform isRecording={isRecording} stream={mediaStream} />
                </div>
              )}

              {/* Mic Button */}
              <Button
                onClick={toggleRecording}
                disabled={isStreaming || disabled}
                variant="ghost"
                size="icon"
                className={cn(
                  "h-8 w-8 rounded-full transition-colors",
                  isRecording
                    ? "bg-red-50 text-red-500 hover:bg-red-100 hover:text-red-600 animate-pulse"
                    : "text-stone-500 hover:text-stone-800 hover:bg-stone-100"
                )}
                aria-label={isRecording ? "Stop recording" : "Start voice input"}
              >
                {isRecording ? <MicOff strokeWidth={2} className="w-[16px] h-[16px]" /> : <Mic strokeWidth={2} className="w-[16px] h-[16px]" />}
              </Button>

              {/* Send / Stop Button */}
              {isStreaming ? (
                <button
                  onClick={() => {
                    playClickSound()
                    onStop()
                  }}
                  className="relative h-8 w-8 shrink-0 rounded-full flex items-center justify-center bg-stone-900 text-white hover:bg-stone-800 transition-colors"
                  aria-label="Stop generating"
                >
                  <Square className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true" />
                </button>
              ) : (
                <div className="flex items-center gap-1 shrink-0 bg-stone-50/80 border border-stone-200/40 rounded-full p-0.5">
                  {/* Dropdown trigger */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        onClick={playClickSound}
                        className="h-8 min-w-[128px] rounded-full bg-white px-3 text-stone-700 border border-stone-200/40 hover:border-stone-300/60 hover:text-stone-950 transition-colors outline-none"
                      >
                        <div className="flex h-full items-center justify-center gap-1.5 text-[12.5px] font-medium">
                          <SelectedIcon className="w-3.5 h-3.5 text-stone-500" />
                          <span>{selectedModeObj.title}</span>
                          <ChevronDown className="w-3 h-3 text-stone-400" />
                        </div>
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="end"
                      side="top"
                      sideOffset={12}
                      className="w-[280px] p-1.5 rounded-[20px] border border-stone-100/50 shadow-xl bg-white/95 backdrop-blur-xl z-[9999]"
                    >
                      {PLAN_MODES.map((mode) => {
                        const Icon = mode.icon
                        const isActive = planMode === mode.id
                        return (
                          <DropdownMenuItem
                            key={mode.id}
                            onClick={() => {
                              playClickSound()
                              onPlanModeChange(mode.id)
                            }}
                            className={cn(
                              "flex flex-col items-start gap-1 cursor-pointer rounded-[14px] px-3.5 py-2.5 transition-colors select-none outline-none",
                              isActive ? "bg-stone-50" : "hover:bg-stone-50/50",
                              "focus:!bg-stone-50/80 focus:!text-stone-900 data-[active]:!bg-stone-50/80 data-[focus]:!bg-stone-50/80"
                            )}
                          >
                            <div className="flex items-center justify-between w-full">
                              <div className="flex items-center gap-2">
                                <Icon className={cn("w-3.5 h-3.5", isActive ? "text-stone-900" : "text-stone-500")} />
                                <span className={cn("text-[13px] font-semibold", isActive ? "text-stone-900" : "text-stone-700")}>
                                  {mode.title}
                                </span>
                              </div>
                              {isActive && <Check className="w-3.5 h-3.5 text-stone-900" />}
                            </div>
                            <span className="text-[11px] text-stone-400 font-light leading-relaxed">
                              {mode.description}
                            </span>
                          </DropdownMenuItem>
                        )
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>

                  {/* Submit arrow button */}
                  <button
                    onClick={handleSend}
                    disabled={(!value.trim() && !uploadedImage) || disabled || !workspace}
                    title={!workspace ? "Choose a working folder first" : undefined}
                    className={cn(
                      "relative h-8 w-8 shrink-0 transition-all duration-200 rounded-full flex items-center justify-center text-white shadow-[0_2px_12px_rgba(0,0,0,0.15)]",
                      (!value.trim() && !uploadedImage) || disabled || !workspace
                        ? "opacity-40 cursor-not-allowed grayscale bg-stone-400"
                        : "cursor-pointer hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(0,0,0,0.2)] active:scale-95"
                    )}
                    style={
                      (!value.trim() && !uploadedImage) || disabled || !workspace
                        ? undefined
                        : { backgroundImage: 'linear-gradient(180deg, #2c2c2c 0%, #111111 100%)' }
                    }
                    aria-label="Send message"
                  >
                    <ArrowRight className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
