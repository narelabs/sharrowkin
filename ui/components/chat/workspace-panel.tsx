"use client"

import { useState, useMemo } from "react"
import { ChevronRight, ChevronDown, File, Folder, FolderOpen, FileCode, FileText, FileJson, Image as ImageIcon, Settings, Database } from "lucide-react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"

interface FileNode {
  name: string
  path: string
  type: "file" | "directory"
  children?: FileNode[]
  modified?: boolean
  additions?: number
  deletions?: number
}

interface WorkspacePanelProps {
  files: FileNode[]
  onFileClick: (path: string) => void
  selectedFile?: string
  className?: string
}

function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase()

  if (ext === "tsx" || ext === "ts" || ext === "jsx" || ext === "js") {
    return <FileCode className="w-4 h-4 text-blue-500" />
  }
  if (ext === "json") {
    return <FileJson className="w-4 h-4 text-yellow-500" />
  }
  if (ext === "md" || ext === "txt") {
    return <FileText className="w-4 h-4 text-stone-500" />
  }
  if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "svg" || ext === "gif") {
    return <ImageIcon className="w-4 h-4 text-purple-500" />
  }
  if (ext === "py") {
    return <FileCode className="w-4 h-4 text-green-500" />
  }
  if (ext === "sql" || ext === "db") {
    return <Database className="w-4 h-4 text-orange-500" />
  }
  if (ext === "yaml" || ext === "yml" || ext === "toml" || ext === "ini") {
    return <Settings className="w-4 h-4 text-stone-500" />
  }

  return <File className="w-4 h-4 text-stone-400" />
}

function FileTreeNode({
  node,
  depth = 0,
  onFileClick,
  selectedFile,
  expandedDirs,
  toggleDir
}: {
  node: FileNode
  depth?: number
  onFileClick: (path: string) => void
  selectedFile?: string
  expandedDirs: Set<string>
  toggleDir: (path: string) => void
}) {
  const isExpanded = expandedDirs.has(node.path)
  const isSelected = selectedFile === node.path

  if (node.type === "directory") {
    return (
      <div>
        <button
          onClick={() => toggleDir(node.path)}
          className={cn(
            "w-full flex items-center gap-1.5 px-2 py-1 text-[12px] hover:bg-stone-100 rounded transition-colors",
            "text-stone-700"
          )}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-stone-400 shrink-0" />
          )}
          {isExpanded ? (
            <FolderOpen className="w-4 h-4 text-blue-500 shrink-0" />
          ) : (
            <Folder className="w-4 h-4 text-blue-500 shrink-0" />
          )}
          <span className="truncate">{node.name}</span>
        </button>

        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                onFileClick={onFileClick}
                selectedFile={selectedFile}
                expandedDirs={expandedDirs}
                toggleDir={toggleDir}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <button
      onClick={() => onFileClick(node.path)}
      className={cn(
        "w-full flex items-center gap-1.5 px-2 py-1 text-[12px] rounded transition-colors",
        isSelected
          ? "bg-blue-50 text-blue-700"
          : "hover:bg-stone-100 text-stone-700",
        node.modified && "font-medium"
      )}
      style={{ paddingLeft: `${depth * 12 + 8 + 16}px` }}
    >
      {getFileIcon(node.name)}
      <span className="truncate flex-1 text-left">{node.name}</span>

      {node.modified && (
        <div className="flex items-center gap-1 text-[10px] shrink-0">
          {node.additions !== undefined && (
            <span className="text-emerald-600">+{node.additions}</span>
          )}
          {node.deletions !== undefined && (
            <span className="text-red-600">-{node.deletions}</span>
          )}
        </div>
      )}
    </button>
  )
}

export function WorkspacePanel({ files, onFileClick, selectedFile, className }: WorkspacePanelProps) {
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set())

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  // Auto-expand directories with modified files
  useMemo(() => {
    const modifiedPaths = new Set<string>()

    const findModified = (nodes: FileNode[], parentPath = "") => {
      for (const node of nodes) {
        if (node.modified) {
          // Add all parent directories
          const parts = node.path.split("/")
          let current = ""
          for (let i = 0; i < parts.length - 1; i++) {
            current += (current ? "/" : "") + parts[i]
            modifiedPaths.add(current)
          }
        }
        if (node.children) {
          findModified(node.children, node.path)
        }
      }
    }

    findModified(files)
    setExpandedDirs(modifiedPaths)
  }, [files])

  return (
    <div className={cn("flex flex-col h-full bg-white border-r border-stone-200", className)}>
      <div className="px-3 py-2 border-b border-stone-200 bg-stone-50">
        <h3 className="text-[11px] font-semibold text-stone-600 uppercase tracking-wide">
          Workspace
        </h3>
      </div>

      <ScrollArea className="flex-1">
        <div className="py-1">
          {files.map((node) => (
            <FileTreeNode
              key={node.path}
              node={node}
              onFileClick={onFileClick}
              selectedFile={selectedFile}
              expandedDirs={expandedDirs}
              toggleDir={toggleDir}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
