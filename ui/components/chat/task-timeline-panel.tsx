"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { ChevronRight, ChevronDown } from "lucide-react"

// =============================================================================
// Types
// =============================================================================

export interface TimelineStep {
  id: string
  label: string
  status: "pending" | "running" | "done" | "error"
  phase?: string // "observe" | "reason" | "stabilize" | "commit"
  duration?: string // "3s", "12s"
  children?: TimelineStep[] // sub-steps (file edits, etc.)
}

export interface TaskTimelinePanelProps {
  steps: TimelineStep[]
  currentPhase?: string
  overallProgress: number // 0-1
  isActive: boolean
  className?: string
}

// =============================================================================
// Styles (injected once)
// =============================================================================

const TIMELINE_STYLES = `
@keyframes timeline-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.4); }
}

@keyframes timeline-slide-in {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.timeline-dot-running {
  animation: timeline-pulse 1.8s ease-in-out infinite;
}

.timeline-step-enter {
  animation: timeline-slide-in var(--motion-base, 200ms) var(--ease-standard, cubic-bezier(0.2, 0.8, 0.2, 1)) forwards;
}

.timeline-panel {
  width: 280px;
  min-width: 280px;
  max-width: 280px;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  background-color: var(--color-bg);
  overflow: hidden;
  transition: width var(--motion-base, 200ms) var(--ease-standard),
              min-width var(--motion-base, 200ms) var(--ease-standard),
              opacity var(--motion-base, 200ms) var(--ease-standard);
}

.timeline-panel[data-hidden="true"] {
  width: 0px;
  min-width: 0px;
  opacity: 0;
  border-right: none;
}

.timeline-progress-bar {
  height: 3px;
  background-color: var(--color-surface-2);
  border-radius: var(--radius-full, 9999px);
  overflow: hidden;
  flex-shrink: 0;
}

.timeline-progress-fill {
  height: 100%;
  background-color: var(--color-accent);
  border-radius: var(--radius-full, 9999px);
  transition: width var(--motion-slow, 360ms) var(--ease-standard);
}

.timeline-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--space-3) 0;
}

.timeline-scroll::-webkit-scrollbar {
  width: 4px;
}

.timeline-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.timeline-scroll::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: var(--radius-full);
}

.timeline-phase-header {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  background-color: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
}

.timeline-step {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  transition: background-color var(--motion-fast, 120ms) var(--ease-standard);
}

.timeline-step[data-current="true"] {
  background-color: var(--color-surface-2);
}

.timeline-step:hover {
  background-color: var(--color-surface);
}

/* Connecting line between dots */
.timeline-dot-col {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 16px;
}

.timeline-dot-col::after {
  content: "";
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  width: 1.5px;
  height: calc(100% + var(--space-2));
  background-color: var(--color-border);
}

.timeline-step:last-child .timeline-dot-col::after {
  display: none;
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-top: 4px;
  transition: background-color var(--motion-base, 200ms) var(--ease-standard),
              box-shadow var(--motion-base, 200ms) var(--ease-standard);
}

.timeline-dot[data-status="pending"] {
  background-color: var(--color-text-muted);
  opacity: 0.4;
}

.timeline-dot[data-status="running"] {
  background-color: var(--color-accent);
  box-shadow: 0 0 6px var(--color-accent);
}

.timeline-dot[data-status="done"] {
  background-color: var(--color-success);
}

.timeline-dot[data-status="error"] {
  background-color: var(--color-danger);
}

.timeline-dot-current {
  width: 10px;
  height: 10px;
  margin-top: 3px;
}

.timeline-label {
  font-size: var(--text-sm, 0.875rem);
  color: var(--color-text-muted);
  line-height: 1.3;
  transition: color var(--motion-base, 200ms) var(--ease-standard),
              font-weight var(--motion-base, 200ms) var(--ease-standard);
}

.timeline-label[data-status="running"] {
  color: var(--color-text);
  font-weight: 500;
}

.timeline-label[data-status="done"] {
  color: var(--color-text);
}

.timeline-label[data-status="error"] {
  color: var(--color-danger);
}

.timeline-duration {
  font-size: var(--text-xs, 0.75rem);
  color: var(--color-text-muted);
  margin-left: auto;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.timeline-children {
  padding-left: calc(16px + var(--space-3));
  overflow: hidden;
  transition: max-height var(--motion-base, 200ms) var(--ease-standard),
              opacity var(--motion-base, 200ms) var(--ease-standard);
}

.timeline-children[data-collapsed="true"] {
  max-height: 0;
  opacity: 0;
}

.timeline-children[data-collapsed="false"] {
  max-height: 500px;
  opacity: 1;
}

.timeline-child-step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
}

.timeline-child-dot {
  width: 5px;
  height: 5px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.timeline-child-dot[data-status="pending"] { background-color: var(--color-text-muted); opacity: 0.3; }
.timeline-child-dot[data-status="running"] { background-color: var(--color-accent); }
.timeline-child-dot[data-status="done"] { background-color: var(--color-success); }
.timeline-child-dot[data-status="error"] { background-color: var(--color-danger); }

.timeline-child-label {
  font-size: var(--text-xs, 0.75rem);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0;
  border-radius: var(--radius-sm);
  transition: background-color var(--motion-fast, 120ms);
}

.timeline-expand-btn:hover {
  background-color: var(--color-surface-2);
}

@media (prefers-reduced-motion: reduce) {
  .timeline-dot-running {
    animation: none;
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  .timeline-step-enter {
    animation: none;
  }
}
`

// =============================================================================
// Helpers
// =============================================================================

function groupByPhase(steps: TimelineStep[]): Map<string, TimelineStep[]> {
  const groups = new Map<string, TimelineStep[]>()
  let currentPhase = "__none__"

  for (const step of steps) {
    if (step.phase && step.phase !== currentPhase) {
      currentPhase = step.phase
    }
    const key = step.phase || currentPhase
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(step)
  }

  return groups
}

const PHASE_LABELS: Record<string, string> = {
  observe: "Observe",
  recall: "Recall",
  reason: "Reason",
  stabilize: "Stabilize",
  commit: "Commit",
}

// =============================================================================
// Sub-components
// =============================================================================

function TimelineStepRow({ step, isCurrent }: { step: TimelineStep; isCurrent: boolean }) {
  const [expanded, setExpanded] = useState(step.status === "running" || step.status === "done")
  const hasChildren = step.children && step.children.length > 0

  return (
    <div className="timeline-step-enter">
      <div className="timeline-step" data-current={isCurrent ? "true" : "false"}>
        {/* Dot column with connecting line */}
        <div className="timeline-dot-col">
          <div
            className={cn(
              "timeline-dot",
              isCurrent && "timeline-dot-current",
              step.status === "running" && "timeline-dot-running"
            )}
            data-status={step.status}
          />
        </div>

        {/* Label + expand toggle */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
          {hasChildren && (
            <button
              className="timeline-expand-btn"
              onClick={() => setExpanded(!expanded)}
              aria-label={expanded ? "Collapse sub-steps" : "Expand sub-steps"}
            >
              {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            </button>
          )}
          <span className="timeline-label" data-status={step.status}>
            {step.label}
          </span>
        </div>

        {/* Duration */}
        {step.duration && (
          <span className="timeline-duration">{step.duration}</span>
        )}
      </div>

      {/* Collapsible children */}
      {hasChildren && (
        <div className="timeline-children" data-collapsed={expanded ? "false" : "true"}>
          {step.children!.map((child) => (
            <div key={child.id} className="timeline-child-step">
              <div className="timeline-child-dot" data-status={child.status} />
              <span className="timeline-child-label">{child.label}</span>
              {child.duration && (
                <span className="timeline-duration">{child.duration}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

export function TaskTimelinePanel({
  steps,
  currentPhase,
  overallProgress,
  isActive,
  className,
}: TaskTimelinePanelProps) {
  const grouped = groupByPhase(steps)
  const runningStepId = steps.find((s) => s.status === "running")?.id

  return (
    <div
      className={cn("timeline-panel", className)}
      data-hidden={!isActive ? "true" : "false"}
      aria-label="Task timeline"
      role="complementary"
    >
      <style dangerouslySetInnerHTML={{ __html: TIMELINE_STYLES }} />

      {/* Header */}
      <div style={{ padding: "var(--space-4)", paddingBottom: "var(--space-3)", flexShrink: 0 }}>
        <div style={{
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          color: "var(--color-text-muted)",
          marginBottom: "var(--space-2)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}>
          Progress
        </div>

        {/* Progress bar */}
        <div className="timeline-progress-bar">
          <div
            className="timeline-progress-fill"
            style={{ width: `${Math.round(overallProgress * 100)}%` }}
          />
        </div>

        <div style={{
          fontSize: "var(--text-xs)",
          color: "var(--color-text-muted)",
          marginTop: "var(--space-1)",
          textAlign: "right",
        }}>
          {Math.round(overallProgress * 100)}%
        </div>
      </div>

      {/* Scrollable timeline */}
      <div className="timeline-scroll">
        {Array.from(grouped.entries()).map(([phase, phaseSteps]) => (
          <div key={phase}>
            {/* Phase header (only if it's a known phase) */}
            {phase !== "__none__" && PHASE_LABELS[phase] && (
              <div className="timeline-phase-header">
                {PHASE_LABELS[phase]}
              </div>
            )}

            {/* Steps in this phase */}
            {phaseSteps.map((step) => (
              <TimelineStepRow
                key={step.id}
                step={step}
                isCurrent={step.id === runningStepId}
              />
            ))}
          </div>
        ))}

        {/* Empty state */}
        {steps.length === 0 && (
          <div style={{
            padding: "var(--space-6) var(--space-4)",
            textAlign: "center",
            fontSize: "var(--text-xs)",
            color: "var(--color-text-muted)",
          }}>
            Waiting for agent to start…
          </div>
        )}
      </div>
    </div>
  )
}
