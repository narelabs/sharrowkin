import sqlite3
import json
from pathlib import Path
from typing import Any

class RldSqliteStore:
    """SQLite backend for RLD genes and traces."""
    
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS genes (
                    id TEXT PRIMARY KEY,
                    data TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trajectories (
                    id TEXT PRIMARY KEY,
                    data TEXT
                )
            ''')

    def save(self, data: dict[str, Any]) -> None:
        """Save the RLD state to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            # Save meta
            meta_keys = ["version", "activation_threshold", "top_k", "embedding_dim", "use_dsm_backend", "gene_segment_ids", "dsm_policy"]
            for k in meta_keys:
                if k in data:
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (k, json.dumps(data[k])))
            
            # Save genes
            for gene in data.get("genes", []):
                conn.execute("INSERT OR REPLACE INTO genes (id, data) VALUES (?, ?)", (gene["id"], json.dumps(gene)))
                
            # Save trajectories
            for traj in data.get("trajectories", []):
                conn.execute("INSERT OR REPLACE INTO trajectories (id, data) VALUES (?, ?)", (traj["id"], json.dumps(traj)))
                
    def load(self) -> dict[str, Any]:
        """Load the RLD state from SQLite."""
        if not self.db_path.exists():
            return {}
            
        data = {}
        with sqlite3.connect(self.db_path) as conn:
            # Load meta
            cursor = conn.execute("SELECT key, value FROM meta")
            for k, v in cursor:
                data[k] = json.loads(v)
                
            # Load genes
            cursor = conn.execute("SELECT data FROM genes")
            data["genes"] = [json.loads(row[0]) for row in cursor]
            
            # Load trajectories
            cursor = conn.execute("SELECT data FROM trajectories")
            data["trajectories"] = [json.loads(row[0]) for row in cursor]
            
            # Empty traces for now (not persisted in this simple schema)
            data["activation_traces"] = []
            
        return data

    def exists(self) -> bool:
        return self.db_path.exists()
