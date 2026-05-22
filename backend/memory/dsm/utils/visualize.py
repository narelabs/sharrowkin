from __future__ import annotations

import html
import json
from typing import Any

from ..core.memory import DynamicSegmentedMemory


def graph_data(memory: DynamicSegmentedMemory) -> dict[str, Any]:
    nodes = [
        {
            "id": segment.id,
            "label": segment.description,
            "category": " → ".join(segment.category_path),
            "tokens": segment.estimated_tokens,
            "importance": segment.priorities.importance,
            "compressed": bool(segment.compressed_from),
        }
        for segment in memory.segments.values()
    ]
    links = []
    seen: set[tuple[str, str]] = set()
    for source, targets in memory.graph.edges.items():
        for target, edge in targets.items():
            key = tuple(sorted((source, target)))
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "source": source,
                    "target": target,
                    "relation": edge.relation,
                    "weight": edge.weight,
                    "reason": edge.reason,
                }
            )
    return {"nodes": nodes, "links": links}


def graph_html(memory: DynamicSegmentedMemory, title: str = "DSM Memory Graph") -> str:
    payload = json.dumps(graph_data(memory), ensure_ascii=False)
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; background: #0b1020; color: #e5e7eb; font-family: sans-serif; }}
    #info {{ position: fixed; left: 16px; top: 16px; max-width: 360px; padding: 12px; background: #111827dd; border: 1px solid #334155; border-radius: 10px; }}
    svg {{ width: 100vw; height: 100vh; }}
    line {{ stroke: #64748b; stroke-opacity: .7; }}
    circle {{ stroke: #e5e7eb; stroke-width: 1.5; }}
    text {{ fill: #e5e7eb; font-size: 11px; pointer-events: none; }}
  </style>
</head>
<body>
  <div id="info"><b>{safe_title}</b><br><span id="meta"></span><br><span id="selected">Hover a node or edge.</span></div>
  <svg id="graph"></svg>
  <script>
    const data = {payload};
    const svg = document.getElementById("graph");
    const meta = document.getElementById("meta");
    const selected = document.getElementById("selected");
    const width = innerWidth, height = innerHeight;
    meta.textContent = `${{data.nodes.length}} segments, ${{data.links.length}} links`;
    const byId = new Map(data.nodes.map(n => [n.id, n]));
    const degree = new Map(data.nodes.map(n => [n.id, 0]));
    data.links.forEach(l => {{ degree.set(l.source, (degree.get(l.source)||0)+1); degree.set(l.target, (degree.get(l.target)||0)+1); }});
    data.nodes.forEach((n, i) => {{
      const angle = (2 * Math.PI * i) / Math.max(1, data.nodes.length);
      const radius = Math.min(width, height) * (0.25 + 0.25 * ((i % 5) / 5));
      n.x = width / 2 + Math.cos(angle) * radius;
      n.y = height / 2 + Math.sin(angle) * radius;
    }});
    for (let t = 0; t < 180; t++) {{
      data.links.forEach(l => {{
        const a = byId.get(l.source), b = byId.get(l.target);
        if (!a || !b) return;
        const dx = b.x - a.x, dy = b.y - a.y;
        a.x += dx * 0.002 * l.weight; a.y += dy * 0.002 * l.weight;
        b.x -= dx * 0.002 * l.weight; b.y -= dy * 0.002 * l.weight;
      }});
      data.nodes.forEach((a, i) => data.nodes.slice(i + 1).forEach(b => {{
        const dx = b.x - a.x, dy = b.y - a.y;
        const d2 = Math.max(80, dx*dx + dy*dy);
        const f = 900 / d2;
        a.x -= dx * f; a.y -= dy * f; b.x += dx * f; b.y += dy * f;
      }}));
    }}
    data.links.forEach(l => {{
      const a = byId.get(l.source), b = byId.get(l.target);
      if (!a || !b) return;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
      line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
      line.setAttribute("stroke-width", 1 + 4 * l.weight);
      line.onmouseenter = () => selected.textContent = `${{l.relation}} (${{l.weight.toFixed(2)}}): ${{l.reason}}`;
      svg.appendChild(line);
    }});
    data.nodes.forEach(n => {{
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", n.x); circle.setAttribute("cy", n.y);
      circle.setAttribute("r", 7 + 3 * (degree.get(n.id) || 0));
      circle.setAttribute("fill", n.compressed ? "#f59e0b" : "#38bdf8");
      circle.onmouseenter = () => selected.textContent = `${{n.category}}: ${{n.label}}`;
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", n.x + 10); text.setAttribute("y", n.y + 4);
      text.textContent = n.label.slice(0, 42);
      group.appendChild(circle); group.appendChild(text); svg.appendChild(group);
    }});
  </script>
</body>
</html>"""
