"use client"

export function TypingIndicator() {
  return (
    <div className="flex gap-3 max-w-[90%] md:max-w-[80%] mr-auto animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="h-8 w-8 shrink-0 rounded-full border border-stone-200 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.04)]" />
      <div
        className="px-4 py-3 rounded-2xl rounded-bl-md bg-white border border-stone-200 shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition-all duration-300 hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(0,0,0,0.06)]"
        role="status"
        aria-label="Assistant is typing"
      >
        <div className="flex items-center gap-1">
          <span
            className="w-2 h-2 rounded-full animate-bounce"
            style={{
              animationDelay: "0ms",
              background: "linear-gradient(to bottom, #786EF1 0%, #5588FB 100%)"
            }}
          />
          <span
            className="w-2 h-2 rounded-full animate-bounce"
            style={{
              animationDelay: "150ms",
              background: "linear-gradient(to bottom, #5588FB 0%, #F7B2FB 100%)"
            }}
          />
          <span
            className="w-2 h-2 rounded-full animate-bounce"
            style={{
              animationDelay: "300ms",
              background: "linear-gradient(to bottom, #F7B2FB 0%, #786EF1 100%)"
            }}
          />
        </div>
      </div>
    </div>
  )
}
