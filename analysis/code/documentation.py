import re
from pathlib import Path


class DocLinker:
    """Scans and parses documentation files, mapping them to codebase symbols."""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path
        self.doc_mapping: dict[str, list[dict[str, str]]] = {}

    def scan_documentation(self) -> dict[str, list[dict[str, str]]]:
        """Scan docs directory and workspace root for markdown files, extracting code links."""
        search_dirs = [
            self.workspace_path,
            self.workspace_path / "docs",
            self.workspace_path / "doc",
            self.workspace_path / "wiki"
        ]

        scanned_paths = set()
        for directory in search_dirs:
            if not directory.exists() or not directory.is_dir():
                continue
            for file_path in directory.glob("*.md"):
                if file_path.is_file():
                    scanned_paths.add(file_path)

        for file_path in scanned_paths:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                relative_path = file_path.relative_to(self.workspace_path).as_posix()
                
                # Simple markdown regex to extract backtick symbols like `MyClass`, `my_method`
                # or explicit markdown links matching files/classes
                symbols = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_\.]+)`", content))
                
                # Check for headings that could specify topics
                headings = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
                title = headings[0] if headings else file_path.stem
                
                for symbol in symbols:
                    # Ignore short symbols or python keywords
                    if len(symbol) < 3 or symbol in ("def", "class", "import", "from", "return", "self"):
                        continue
                    
                    if symbol not in self.doc_mapping:
                        self.doc_mapping[symbol] = []
                    
                    self.doc_mapping[symbol].append({
                        "path": relative_path,
                        "title": title
                    })
            except Exception:
                pass

        return self.doc_mapping

    def get_links_for_symbol(self, symbol: str) -> list[dict[str, str]]:
        """Get documentation references associated with a symbol name (or sub-parts)."""
        links = []
        # Match full symbol or trailing part (e.g. match ClassName if symbol is module.ClassName)
        parts = symbol.split(".")
        for part in parts:
            if part in self.doc_mapping:
                links.extend(self.doc_mapping[part])
        
        # Deduplicate
        seen = set()
        deduped = []
        for link in links:
            key = (link["path"], link["title"])
            if key not in seen:
                seen.add(key)
                deduped.append(link)
                
        return deduped
