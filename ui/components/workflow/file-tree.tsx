"use client"

import { useState } from "react"
import { ChevronRight, ChevronDown, Folder, FileCode, FileText, FileJson, FileImage, FolderOpen } from "lucide-react"
import { cn } from "@/lib/utils"

export type FileNode = {
  id: string
  name: string
  type: "folder" | "file"
  path: string
  children?: FileNode[]
}

interface FileTreeProps {
  node: FileNode
  depth?: number
  onSelectFile: (path: string, name: string) => void
  selectedPath?: string | null
}

const getFileIcon = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase()
  if (["tsx", "ts", "jsx", "js", "py", "go", "rs", "java", "cpp", "c", "h"].includes(ext || "")) return <FileCode className="w-4 h-4 text-emerald-500" strokeWidth={1.5} />
  if (["json", "yml", "yaml", "toml"].includes(ext || "")) return <FileJson className="w-4 h-4 text-amber-500" strokeWidth={1.5} />
  if (["png", "jpg", "jpeg", "svg", "gif"].includes(ext || "")) return <FileImage className="w-4 h-4 text-purple-500" strokeWidth={1.5} />
  return <FileText className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
}

export function FileTree({ node, depth = 0, onSelectFile, selectedPath }: FileTreeProps) {
  const [isOpen, setIsOpen] = useState(depth < 1) // Auto-open root
  const isSelected = selectedPath === node.path

  if (node.type === "folder") {
    return (
      <div className="w-full">
        <div 
          className={cn(
            "flex items-center gap-1.5 py-1 px-2 rounded-md cursor-pointer text-stone-600 hover:bg-stone-100/80 transition-colors",
            depth === 0 && "font-medium text-stone-800"
          )}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronDown className="w-3.5 h-3.5 opacity-50 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 opacity-50 shrink-0" />}
          {isOpen ? <FolderOpen className="w-4 h-4 text-sky-500 shrink-0" strokeWidth={1.5} /> : <Folder className="w-4 h-4 text-sky-500 shrink-0" strokeWidth={1.5} />}
          <span className="text-[13px] truncate select-none">{node.name}</span>
        </div>
        
        {isOpen && node.children && (
          <div className="w-full">
            {node.children.map(child => (
              <FileTree 
                key={child.id} 
                node={child} 
                depth={depth + 1} 
                onSelectFile={onSelectFile}
                selectedPath={selectedPath}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div 
      className={cn(
        "flex items-center gap-2 py-1 px-2 rounded-md cursor-pointer transition-colors",
        isSelected ? "bg-stone-200/60 text-stone-900" : "text-stone-600 hover:bg-stone-100/80"
      )}
      style={{ paddingLeft: `${depth * 12 + 22}px` }}
      onClick={() => onSelectFile(node.path, node.name)}
    >
      {getFileIcon(node.name)}
      <span className={cn("text-[13px] truncate select-none", isSelected && "font-medium")}>{node.name}</span>
    </div>
  )
}
