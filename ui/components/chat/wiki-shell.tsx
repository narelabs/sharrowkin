"use client"

import React, { useState, useEffect, useCallback } from "react"
import { LeftSidebar } from "./left-sidebar"
import { RightSidebar } from "./right-sidebar"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
import { Search, FileText, Plus, Folder, ArrowLeft, X } from "lucide-react"
import { cn } from "@/lib/utils"

export function WikiShell() {
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)

  // Terminal emulator state for RightSidebar
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "sharrowkin-core ~ bash",
    "$ dsm status",
    "→ Repository context connected: stable",
    "→ 12,408 Memory chunks active",
    "",
    "$ dsm logs",
    "[SUCCESS] Wiki & Documentation compiler ready.",
  ])
  const [isRunningTask, setIsRunningTask] = useState(false)
  const [currentInput, setCurrentInput] = useState("")
  const [terminalDock, setTerminalDock] = useState<"sidebar" | "bottom">("sidebar")
  const [isDraggingTerminal, setIsDraggingTerminal] = useState(false)

  const runBuildCommand = useCallback(() => {
    if (isRunningTask) return
    setIsRunningTask(true)
    setTerminalLines(prev => [...prev, "", "$ npm run build"])
    fetch(`${BACKEND_URL}/api/terminal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "npm run build" }),
    })
      .then((res) => res.json())
      .then((data) => setTerminalLines((prev) => [...prev, ...(Array.isArray(data.output) ? data.output : [JSON.stringify(data)])]))
      .catch((err) => setTerminalLines((prev) => [...prev, `error: ${err.message}`]))
      .finally(() => setIsRunningTask(false))
  }, [isRunningTask])

  const runTestCommand = useCallback(() => {
    if (isRunningTask) return
    setIsRunningTask(true)
    setTerminalLines(prev => [...prev, "", "$ npm test"])
    fetch(`${BACKEND_URL}/api/terminal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "npm test" }),
    })
      .then((res) => res.json())
      .then((data) => setTerminalLines((prev) => [...prev, ...(Array.isArray(data.output) ? data.output : [JSON.stringify(data)])]))
      .catch((err) => setTerminalLines((prev) => [...prev, `error: ${err.message}`]))
      .finally(() => setIsRunningTask(false))
  }, [isRunningTask])

  const clearTerminal = useCallback(() => {
    setTerminalLines([])
  }, [])

  const handleCommandSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentInput) return
    const cmd = currentInput.trim()
    setTerminalLines(prev => [...prev, `$ ${currentInput}`])
    setCurrentInput("")
    if (cmd.toLowerCase() === "clear") {
      setTerminalLines([])
      return
    }
    setIsRunningTask(true)
    try {
      const response = await fetch(`${BACKEND_URL}/api/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      })
      const data = await response.json()
      setTerminalLines((prev) => [...prev, ...(Array.isArray(data.output) ? data.output : [JSON.stringify(data)])])
    } catch (err: any) {
      setTerminalLines((prev) => [...prev, `error: ${err.message}`])
    } finally {
      setIsRunningTask(false)
    }
  }, [currentInput])

  // Terminal dock drag state
  const handleDragStart = useCallback(() => setIsDraggingTerminal(true), [])
  const handleDragEnd = useCallback(() => setIsDraggingTerminal(false), [])

  useEffect(() => {
    const handleGlobalDragEnd = () => setIsDraggingTerminal(false)
    window.addEventListener("dragend", handleGlobalDragEnd)
    window.addEventListener("drop", handleGlobalDragEnd)
    return () => {
      window.removeEventListener("dragend", handleGlobalDragEnd)
      window.removeEventListener("drop", handleGlobalDragEnd)
    }
  }, [])

  // Dynamic documentation fetching
  const [documents, setDocuments] = useState<any[]>([])
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null)
  const [docContent, setDocContent] = useState<string>("")
  const [folders, setFolders] = useState<any[]>([])

  // New document creation state
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [newDocTitle, setNewDocTitle] = useState("")
  const [newDocFolder, setNewDocFolder] = useState("Theory & Manifesto")
  const [newDocContent, setNewDocContent] = useState("")
  const [isSavingDoc, setIsSavingDoc] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [folderFilter, setFolderFilter] = useState<string | null>(null)

  const fetchFolders = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/docs/folders`)
      if (res.ok) {
        const data = await res.json()
        setFolders(data.folders || [])
      }
    } catch (err) {
      console.error("Failed to load doc folders:", err)
      setFolders([
        { name: "Theory & Manifesto", path: "", count: 0 },
        { name: "Workspace Root", path: "", count: 0 }
      ])
    }
  }, [])

  const fetchDocs = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/docs`)
      if (res.ok) {
        const data = await res.json()
        setDocuments(data)
      }
    } catch (err) {
      console.error("Failed to load real markdown docs:", err)
      setDocuments([])
    }
  }, [])

  useEffect(() => {
    fetchFolders()
    fetchDocs()
  }, [fetchFolders, fetchDocs])

  // Fetch document content upon selection
  useEffect(() => {
    if (!selectedDoc) return
    setDocContent("")
    
    const fetchContent = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/docs/content?filename=${encodeURIComponent(selectedDoc.filename)}`)
        if (res.ok) {
          const data = await res.json()
          setDocContent(data.content)
        }
      } catch (err) {
        setDocContent("Failed to load document content.")
      }
    }
    fetchContent()
  }, [selectedDoc])

  return (
    <div className="h-dvh bg-background flex overflow-hidden">
      <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />

      {/* Main Area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-[#f7f7f9] overflow-hidden">
        
        {/* Top Header */}
        <div className="h-14 border-b border-stone-200/50 flex items-center justify-between px-6 bg-white/50 backdrop-blur-sm z-10 shrink-0">
          <div className="flex items-center gap-2 text-stone-855">
            <BookIcon />
            <span className="font-medium text-[13px] tracking-wide text-stone-700">Project Knowledge Base</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" strokeWidth={1.5} />
              <input 
                type="text" 
                placeholder="Search wiki..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-1.5 text-[13px] bg-white border border-stone-200/60 rounded-full w-64 focus:outline-none focus:ring-0 shadow-[0_1px_4px_rgba(0,0,0,0.02)]"
              />
            </div>
            <button 
              onClick={() => setIsCreateOpen(true)}
              className="bg-stone-900 hover:bg-stone-850 text-white rounded-xl px-4 text-[12px] h-8 shadow-sm flex items-center gap-1.5 font-sans"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Doc</span>
            </button>
          </div>
        </div>

        {/* Content Box */}
        <div className="flex-1 overflow-hidden flex relative">
          
          {/* Main List Column */}
          <div className={cn(
            "flex-1 overflow-y-auto p-8 transition-all duration-300", 
            selectedDoc ? "max-w-[45%]" : "max-w-4xl mx-auto w-full"
          )}>
            
            <div className="flex flex-col gap-1 mb-6">
              <h1 className="text-xl font-light text-stone-800 tracking-tight">Documentation</h1>
              <p className="text-[13px] text-stone-400 font-light">Manage project context, guidelines, and architecture decisions.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Folders */}
              {folders.map((folder) => (
                <button key={folder.name} onClick={() => setFolderFilter(folderFilter === folder.name ? null : folder.name)} className={cn("p-4 rounded-2xl bg-white border border-stone-200/40 shadow-[0_1px_8px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all text-left group", folderFilter === folder.name && "bg-stone-50 border-stone-300/70")}>
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-8 h-8 rounded-full bg-stone-50 flex items-center justify-center group-hover:bg-stone-100 transition-colors">
                      <Folder className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                    </div>
                    <span className="font-medium text-[14px] text-stone-700">{folder.name}</span>
                  </div>
                  <div className="text-[12px] text-stone-400 font-normal ml-11">
                    {folder.count} documents
                  </div>
                </button>
              ))}
            </div>

            <div className="pt-8">
              <h2 className="text-[12.5px] font-semibold text-stone-500 tracking-tight mb-3">Active Documents</h2>
              <div className="bg-white border border-stone-200/40 rounded-2xl shadow-[0_1px_8px_rgba(0,0,0,0.02)] overflow-hidden">
                {documents
                .filter(doc => (!searchQuery || doc.title.toLowerCase().includes(searchQuery.toLowerCase())) && (!folderFilter || doc.folder === folderFilter))
                .map((doc, i) => (
                  <div 
                    key={doc.id} 
                    onClick={() => setSelectedDoc(doc)}
                    className={cn(
                      "flex items-center justify-between p-4 hover:bg-stone-50 transition-colors cursor-pointer",
                      selectedDoc?.id === doc.id ? "bg-stone-50" : "",
                      i !== documents.length - 1 ? 'border-b border-stone-100' : ''
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                      <span className="text-[13.5px] text-stone-700 font-normal">{doc.title}</span>
                    </div>
                    <div className="flex items-center gap-6">
                      <span className="text-[11px] text-stone-400 font-normal bg-stone-100 px-2 py-0.5 rounded-full">{doc.folder}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Premium Document View Panel (Split Column) */}
          {selectedDoc && (
            <div className="w-[55%] border-l border-stone-200/60 bg-white flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
              {/* Header */}
              <div className="p-6 border-b border-stone-200/55 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setSelectedDoc(null)}
                    className="p-1 hover:bg-stone-100 rounded-lg text-stone-500 transition-colors mr-1"
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <div className="flex flex-col">
                    <h2 className="text-[14.5px] font-medium text-stone-850 leading-tight">{selectedDoc.title}</h2>
                    <span className="text-[11px] text-stone-400 font-mono mt-0.5">{selectedDoc.folder}</span>
                  </div>
                </div>
              </div>

              {/* Document Text View */}
              <div className="flex-1 overflow-y-auto p-8 font-sans text-[13px] leading-relaxed text-stone-650 bg-[#fdfdfd] whitespace-pre-wrap select-text selection:bg-stone-200/80">
                {docContent || "Loading file content..."}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Right Sidebar with fully functional terminal lines sync */}
      <RightSidebar 
        isOpen={rightSidebarOpen} 
        onToggle={() => setRightSidebarOpen(!rightSidebarOpen)} 
        terminalLines={terminalLines}
        isRunningTask={isRunningTask}
        currentInput={currentInput}
        setCurrentInput={setCurrentInput}
        onSubmitCommand={handleCommandSubmit}
        runBuildCommand={runBuildCommand}
        runTestCommand={runTestCommand}
        clearTerminal={clearTerminal}
        terminalDock={terminalDock}
        setTerminalDock={setTerminalDock}
        isDraggingTerminal={isDraggingTerminal}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      />

      {/* Apple-style Doc Creation Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-stone-950/20 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
          <div className="bg-white border border-stone-200 shadow-2xl rounded-3xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200 animate-out fade-out zoom-out">
            <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between">
              <span className="text-[14px] font-semibold text-stone-800 tracking-tight">Create Document</span>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="w-6 h-6 rounded-full hover:bg-stone-100 flex items-center justify-center text-stone-400 hover:text-stone-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Document Title</label>
                <input
                  type="text"
                  value={newDocTitle}
                  onChange={(e) => setNewDocTitle(e.target.value)}
                  placeholder="e.g. SYSTEM_FLOWS"
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 bg-stone-50/50"
                />
              </div>
              
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Target Location</label>
                <select
                  value={newDocFolder}
                  onChange={(e) => setNewDocFolder(e.target.value)}
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 bg-white"
                >
                  {folders.map((folder) => (
                    <option key={folder.name} value={folder.name}>
                      {folder.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Content (Markdown)</label>
                <textarea
                  value={newDocContent}
                  onChange={(e) => setNewDocContent(e.target.value)}
                  placeholder="# Write your markdown here..."
                  rows={8}
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 font-mono bg-stone-50/30"
                />
              </div>
            </div>
            
            <div className="px-6 py-4 bg-stone-50 border-t border-stone-100 flex items-center justify-end gap-2">
              <button
                onClick={() => setIsCreateOpen(false)}
                className="px-4 py-2 border border-stone-200 text-stone-600 rounded-xl text-[12px] hover:bg-stone-100 font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!newDocTitle.trim() || isSavingDoc}
                onClick={async () => {
                  setIsSavingDoc(true)
                  try {
                    const res = await fetch(`${BACKEND_URL}/api/docs/create`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        title: newDocTitle,
                        folder: newDocFolder,
                        content: newDocContent,
                      }),
                    })
                    if (res.ok) {
                      await fetchDocs()
                      setIsCreateOpen(false)
                      setNewDocTitle("")
                      setNewDocContent("")
                    }
                  } catch (err) {
                    console.error("Failed to create document:", err)
                  } finally {
                    setIsSavingDoc(false)
                  }
                }}
                className="px-4 py-2 bg-stone-900 text-white rounded-xl text-[12px] hover:bg-stone-850 font-medium shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isSavingDoc ? "Saving..." : "Create Document"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function BookIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
    </svg>
  )
}
