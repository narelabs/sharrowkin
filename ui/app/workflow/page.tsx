"use client"

import { useState, useEffect, useCallback, Suspense } from "react"
import { useRouter } from "next/navigation"
import { ArrowLeft, Loader2, FolderTree, RotateCw, Search, X, FileCode, Save, Folder } from "lucide-react"
import { FileTree, type FileNode } from "@/components/workflow/file-tree"
import { CodeViewer } from "@/components/workflow/code-viewer"
import { LeftSidebar } from "@/components/chat/left-sidebar"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

export default function WorkflowPage() {
  const router = useRouter()
  const [workspacePath, setWorkspacePath] = useState<string>("")
  const [treeData, setTreeData] = useState<FileNode | null>(null)
  const [isLoadingTree, setIsLoadingTree] = useState(false)
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null)
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [isLoadingFile, setIsLoadingFile] = useState(false)
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  // Load workspace path from localStorage
  // Auto-detect workspace from backend settings
  useEffect(() => {
    async function detectWorkspace() {
      // 1. Try localStorage first
      const savedPath = localStorage.getItem("workspace_path") ||
                       localStorage.getItem("sharrowkin-workspace-path")
      if (savedPath) {
        setWorkspacePath(savedPath)
        return
      }

      // 2. Ask backend for current workspace
      try {
        const res = await fetch(`${BACKEND_URL}/api/settings`)
        if (res.ok) {
          const data = await res.json()
          if (data.workspace_path) {
            setWorkspacePath(data.workspace_path)
            localStorage.setItem("workspace_path", data.workspace_path)
            return
          }
        }
      } catch {}

      // 3. Try backend workspace/detect endpoint
      try {
        const res = await fetch(`${BACKEND_URL}/api/workspace/detect`)
        if (res.ok) {
          const data = await res.json()
          if (data.path) {
            setWorkspacePath(data.path)
            localStorage.setItem("workspace_path", data.path)
            return
          }
        }
      } catch {}
    }

    detectWorkspace()
  }, [])

  const handleSearch = useCallback(async (query: string) => {
    if (!query.trim() || !workspacePath) {
      setSearchResults([])
      return
    }
    setIsSearching(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/workspace/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace: workspacePath,
          query,
          max_results: 30
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setSearchResults(data.results || [])
      }
    } catch {
      setSearchResults([])
    } finally {
      setIsSearching(false)
    }
  }, [workspacePath])

  const handleSearchSelect = (result: any) => {
    handleSelectFile(result.file, result.file.split("/").pop() || result.file)
    setShowSearch(false)
  }

  const handleStartEdit = () => {
    if (fileContent) {
      setEditContent(fileContent)
      setIsEditing(true)
    }
  }

  const handleSaveFile = async () => {
    if (!selectedFilePath || !workspacePath) return
    setIsSaving(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/workspace/file`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace: workspacePath,
          path: selectedFilePath,
          content: editContent
        }),
      })
      if (res.ok) {
        setFileContent(editContent)
        setIsEditing(false)
        toast.success("File saved")
      } else {
        toast.error("Failed to save file")
      }
    } catch (err) {
      toast.error("Save error")
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditContent("")
  }

  const fetchTree = async () => {
    if (!workspacePath) {
      toast.error("No workspace selected")
      return
    }

    setIsLoadingTree(true)
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/workspace/tree?path=${encodeURIComponent(workspacePath)}`
      )

      if (!res.ok) {
        throw new Error("Failed to fetch workspace tree")
      }

      const data = await res.json()
      setTreeData(data.tree)
      toast.success("Workspace tree loaded")
    } catch (err) {
      console.error("Failed to fetch tree:", err)
      toast.error("Failed to load workspace tree")
      setTreeData(null)
    } finally {
      setIsLoadingTree(false)
    }
  }

  useEffect(() => {
    if (workspacePath) {
      fetchTree()
    }
  }, [workspacePath])

  const handleSelectFile = async (path: string, name: string) => {
    if (!workspacePath) return

    setSelectedFilePath(path)
    setSelectedFileName(name)
    setIsLoadingFile(true)
    setFileContent(null)

    try {
      const res = await fetch(
        `${BACKEND_URL}/api/workspace/file?workspace=${encodeURIComponent(workspacePath)}&path=${encodeURIComponent(path)}`
      )

      if (res.ok) {
        const data = await res.json()
        setFileContent(data.content || "")
      } else {
        setFileContent("Failed to load file.")
        toast.error("Failed to load file")
      }
    } catch (err) {
      setFileContent(`Error loading file: ${err}`)
      toast.error("Error loading file")
    } finally {
      setIsLoadingFile(false)
    }
  }

  const handleWorkspaceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newPath = e.target.value
    setWorkspacePath(newPath)
    localStorage.setItem("workspace_path", newPath)
  }

  return (
    <div className="h-full bg-background flex overflow-hidden">
      <Suspense>
        <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />
      </Suspense>

      <div className="flex-1 flex flex-col overflow-hidden bg-white font-sans relative z-10">
        {/* Header */}
        <header className="h-[52px] bg-white flex items-center justify-between px-5 shrink-0 border-b border-stone-100/50">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-stone-700 font-medium text-[13.5px]">
              <FolderTree size={16} className="text-emerald-500" />
              <span>Project Explorer</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSearch(!showSearch)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium border rounded-md transition-colors",
                showSearch
                  ? "text-stone-700 bg-stone-100 border-stone-300"
                  : "text-stone-500 hover:text-stone-700 bg-stone-50 hover:bg-stone-100 border-stone-200/60"
              )}
            >
              <Search size={13} />
              Search
            </button>
            {selectedFilePath && !isEditing && (
              <button
                onClick={handleStartEdit}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-stone-500 hover:text-stone-700 bg-stone-50 hover:bg-stone-100 border border-stone-200/60 rounded-md transition-colors"
              >
                <FileCode size={13} />
                Edit
              </button>
            )}
            {isEditing && (
              <>
                <button
                  onClick={handleSaveFile}
                  disabled={isSaving}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-white bg-emerald-600 hover:bg-emerald-700 border border-emerald-700 rounded-md transition-colors"
                >
                  <Save size={13} />
                  {isSaving ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={handleCancelEdit}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-stone-500 hover:text-stone-700 bg-stone-50 hover:bg-stone-100 border border-stone-200/60 rounded-md transition-colors"
                >
                  <X size={13} />
                  Cancel
                </button>
              </>
            )}
            <button
              onClick={fetchTree}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-stone-500 hover:text-stone-700 bg-stone-50 hover:bg-stone-100 border border-stone-200/60 rounded-md transition-colors"
              disabled={isLoadingTree}
            >
              <RotateCw size={13} className={isLoadingTree ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </header>

        {/* Main Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar - Workspace Selector + File Tree + Search */}
          <div className="w-[320px] bg-[#fafafa] flex flex-col shrink-0">
            {/* Workspace Path Input */}
            <div className="px-3 py-3 border-b border-stone-200/60">
              <div className="flex items-center gap-2 mb-1.5">
                <Folder size={14} className="text-stone-500" />
                <span className="text-[11px] font-medium text-stone-600 uppercase tracking-wide">Workspace</span>
              </div>
              <input
                type="text"
                value={workspacePath}
                onChange={handleWorkspaceChange}
                placeholder="Enter workspace path..."
                className="w-full px-3 py-2 text-[12px] bg-white border border-stone-200 rounded-lg outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 transition-all"
              />
            </div>

            {showSearch ? (
              <>
                <div className="px-3 py-2.5 border-b border-stone-200/60">
                  <div className="flex items-center gap-2 bg-white border border-stone-200 rounded-lg px-3 py-2">
                    <Search size={14} className="text-stone-400 shrink-0" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => {
                        setSearchQuery(e.target.value)
                        handleSearch(e.target.value)
                      }}
                      placeholder="Search code..."
                      className="flex-1 text-[12px] bg-transparent outline-none text-stone-700 placeholder:text-stone-400"
                      autoFocus
                    />
                    {searchQuery && (
                      <button onClick={() => { setSearchQuery(""); setSearchResults([]) }}>
                        <X size={12} className="text-stone-400 hover:text-stone-600" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {isSearching ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-4 h-4 animate-spin text-stone-400" />
                    </div>
                  ) : searchResults.length > 0 ? (
                    <div className="divide-y divide-stone-100">
                      {searchResults.map((r, i) => (
                        <button
                          key={i}
                          onClick={() => handleSearchSelect(r)}
                          className="w-full text-left px-3 py-2 hover:bg-stone-100/80 transition-colors"
                        >
                          <div className="text-[11px] font-mono text-stone-500 truncate">{r.file}:{r.line}</div>
                          <div className="text-[11.5px] text-stone-700 truncate mt-0.5">{r.match}</div>
                        </button>
                      ))}
                    </div>
                  ) : searchQuery ? (
                    <div className="text-center py-8 text-[12px] text-stone-400">No results</div>
                  ) : (
                    <div className="text-center py-8 text-[12px] text-stone-400">Type to search code</div>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="px-4 py-3 flex items-center text-[12.5px] font-medium text-stone-600">
                  Workspace Files
                </div>
                <div className="flex-1 overflow-y-auto px-2 pb-4">
                  {!workspacePath ? (
                    <div className="p-4 text-center text-[12px] text-stone-500">
                      Enter workspace path above to browse files
                    </div>
                  ) : isLoadingTree ? (
                    <div className="flex flex-col items-center justify-center h-32 text-stone-400 gap-2">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span className="text-[12px]">Loading tree...</span>
                    </div>
                  ) : treeData ? (
                    <FileTree
                      node={treeData}
                      onSelectFile={handleSelectFile}
                      selectedPath={selectedFilePath}
                    />
                  ) : (
                    <div className="p-4 text-center text-[12px] text-stone-500">
                      Failed to load workspace tree
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Main - Code Viewer or Editor */}
          <div className="flex-1 overflow-hidden bg-white">
            {isEditing && selectedFilePath ? (
              <div className="h-full flex flex-col">
                <div className="h-10 border-b border-stone-200/60 flex items-center px-4 bg-amber-50/50 shrink-0">
                  <span className="text-[12px] font-medium text-amber-700">Editing: {selectedFilePath.split("/").pop()}</span>
                </div>
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="flex-1 w-full p-4 font-mono text-[12.5px] leading-relaxed bg-white text-stone-800 outline-none resize-none"
                  spellCheck={false}
                />
              </div>
            ) : (
              <CodeViewer
                filename={selectedFilePath}
                content={fileContent}
                isLoading={isLoadingFile}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
