"use client"

import React, { Component, type ReactNode } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex flex-col items-center justify-center h-full min-h-[200px] p-8 bg-white rounded-2xl border border-stone-200/60">
          <div className="w-12 h-12 rounded-full bg-red-50 border border-red-100 flex items-center justify-center mb-4">
            <AlertTriangle size={22} strokeWidth={1.5} className="text-red-500" />
          </div>
          <h3 className="text-[14px] font-medium text-stone-800 mb-1">Something went wrong</h3>
          <p className="text-[12px] text-stone-400 text-center max-w-[320px] mb-4">
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 bg-stone-900 hover:bg-stone-800 text-white rounded-xl text-[12px] transition-colors shadow-sm"
          >
            <RefreshCw size={13} />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
