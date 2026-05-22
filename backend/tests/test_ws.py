"""Test WebSocket intent routing end-to-end."""
import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_WS_INTEGRATION") != "1",
    reason="requires a running uvicorn server on 127.0.0.1:8000",
)

# Force utf-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test():
    try:
        import websockets
    except ImportError:
        print("Installing websockets...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    uri = "ws://127.0.0.1:8000/api/agent/ws"
    print(f"Connecting to {uri}...")

    async with websockets.connect(uri) as ws:
        workspace = os.getenv("WORKSPACE_PATH", "/tmp/test-workspace")
        payload = {"task": "изучай проект", "workspace": workspace}
        print(f"Sending: {json.dumps(payload, ensure_ascii=False)}")
        await ws.send(json.dumps(payload))
        
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(msg)
                print(f"  RECV: {json.dumps(data, ensure_ascii=False, indent=2)}")
                
                if data.get("type") == "status" and data.get("status") in ("done", "error"):
                    print("Stream ended via status event.")
                    break
                if data.get("type") in ("success", "error"):
                    print("Stream ended via legacy event.")
                    break
            except asyncio.TimeoutError:
                print("TIMEOUT after 30s!")
                break
            except Exception as e:
                print(f"Error: {e}")
                break

if __name__ == "__main__":
    asyncio.run(test())
