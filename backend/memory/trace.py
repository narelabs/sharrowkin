"""TraceMemory for Sharrowkin - Buffering and replaying successful trajectories."""

from __future__ import annotations

import json
from pathlib import Path
import time
from memory.dsm.indexing.embedding import cosine

class TraceMemory:
    """Tracks historical reasoning traces for trace_replay queries."""
    
    def __init__(self, filepath: Path) -> None:
        self.filepath = Path(filepath)
        self.traces: list[dict] = []
        self.load()
        
    def load(self) -> None:
        """Load traces from disk."""
        if not self.filepath.exists():
            self.traces = []
            return
            
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.traces = data
                else:
                    self.traces = data.get("traces", [])
        except Exception as e:
            print(f"[TraceMemory] Error loading trace memory, initializing empty: {e}")
            self.traces = []
            
    def save(self) -> None:
        """Save traces to disk."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"traces": self.traces[-100:]}, f, indent=2) # Keep last 100 traces
        except Exception as e:
            print(f"[TraceMemory] Error saving trace memory: {e}")
            
    def _calculate_jaccard_and_keywords(self, query: str, task: str) -> float:
        """Calculate word token overlap (Jaccard index) and award bonuses for keyword matches."""
        q_words = set(query.lower().split())
        t_words = set(task.lower().split())
        
        if not q_words or not t_words:
            return 0.0
            
        intersection = q_words.intersection(t_words)
        union = q_words.union(t_words)
        
        jaccard = len(intersection) / len(union)
        
        # Keyword bonus: boost score if critical technical keywords match (e.g. "pytest", "bug", "error", "auth", "csv")
        keywords = {"pytest", "test", "error", "bug", "import", "class", "function", "method", "fix", "missing", "failing"}
        keyword_matches = q_words.intersection(t_words).intersection(keywords)
        bonus = len(keyword_matches) * 0.15
        
        return min(1.0, jaccard + bonus)

    def _summarize_trace_context(self, states: list[str], actions: list[str], final_answer: str) -> dict:
        """Create a highly compact summary of states, actions, and final answer to prevent LLM prompt bloat."""
        summarized_states = []
        for state in states:
            # Look for traceback or error matches
            lines = state.split("\n")
            error_lines = []
            for line in lines:
                if any(err in line for err in ["Error", "Exception", "Fail", "Traceback", "AttributeError", "KeyError", "TypeError"]):
                    error_lines.append(line.strip()[:120])
                if len(error_lines) >= 3:
                    break
            
            # If no errors found, just grab the first non-empty line
            if error_lines:
                summarized_states.append(" -> ".join(error_lines))
            else:
                non_empty = [l.strip()[:150] for l in lines if l.strip()]
                if non_empty:
                    summarized_states.append(non_empty[0])
                else:
                    summarized_states.append("empty state")
                
        # Keep only the last 3 state summaries to save space
        if len(summarized_states) > 3:
            summarized_states = summarized_states[-3:]

        # Summarize final answer: get first few lines and check for diff summaries
        final_lines = final_answer.split("\n")
        brief_ans = []
        for line in final_lines[:5]:
            if line.strip():
                brief_ans.append(line.strip()[:150])
        # Find if there are diff changes mentioned
        diff_info = [l for l in final_lines if l.startswith("+ ") or l.startswith("- ")]
        if diff_info:
            brief_ans.append(f"Diff modifications: {len(diff_info)} lines changed.")
            
        return {
            "summarized_states": summarized_states,
            "brief_actions": actions[:5],  # Keep first 5 actions
            "brief_final_answer": "\n".join(brief_ans)
        }

    def add_trace(
        self,
        task: str,
        states: list[str],
        actions: list[str],
        final_answer: str,
        success: bool,
        tools_used: list[str],
        energy_used: float,
        task_embedding: list[float]
    ) -> None:
        """Add a new execution trace to the memory with an integrated summary representation."""
        summary = self._summarize_trace_context(states, actions, final_answer)
        trace = {
            "id": f"trace_{int(time.time())}_{len(self.traces)}",
            "task": task,
            "states": [s[:1000] for s in states],  # Truncate raw states to avoid massive files
            "actions": actions,
            "final_answer": final_answer[:2000],
            "summary": summary,  # Store a compact summary for few-shot prompt injection
            "success": success,
            "tools_used": tools_used,
            "energy_used": round(energy_used, 2),
            "timestamp": time.time(),
            "task_embedding": task_embedding
        }
        self.traces.append(trace)
        self.save()
        
    def find_similar_traces(
        self,
        query: str,
        query_embedding: list[float],
        limit: int = 2,
        min_similarity: float = 0.55
    ) -> list[dict]:
        """Query trace memory using hybrid cosine similarity of task embeddings and token Jaccard overlap."""
        if not self.traces:
            return []
            
        scored_traces = []
        for trace in self.traces:
            # 1. Cosine similarity score
            trace_emb = trace.get("task_embedding")
            vector_sim = 0.0
            if query_embedding and trace_emb and len(trace_emb) == len(query_embedding):
                vector_sim = cosine(query_embedding, trace_emb)
                
            # 2. Jaccard token similarity score
            jaccard_sim = self._calculate_jaccard_and_keywords(query, trace.get("task", ""))
            
            # 3. Hybrid scoring formula
            if query_embedding:
                hybrid_sim = 0.5 * vector_sim + 0.5 * jaccard_sim
            else:
                hybrid_sim = jaccard_sim  # 100% fallback to Jaccard
                
            if hybrid_sim >= min_similarity:
                scored_traces.append((hybrid_sim, trace))
                
        # Sort descending by hybrid similarity
        scored_traces.sort(key=lambda x: x[0], reverse=True)
        
        # Return limit traces, removing the raw embeddings to conserve context space
        results = []
        for sim, trace in scored_traces[:limit]:
            clean_trace = trace.copy()
            clean_trace.pop("task_embedding", None)
            clean_trace["similarity"] = round(sim, 3)
            results.append(clean_trace)
            
        return results
