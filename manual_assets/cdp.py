"""Tiny one-shot CDP client -- reconnects fresh each invocation against the
already-running headless Chrome (port 9333), since this is driven as a
sequence of separate CLI calls, not a long-lived process.
"""
import asyncio
import base64
import json
import sys

import websockets

DEVTOOLS_HTTP = "http://localhost:9333"


async def _get_page_ws_url():
    import urllib.request
    with urllib.request.urlopen(f"{DEVTOOLS_HTTP}/json") as resp:
        targets = json.loads(resp.read())
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise SystemExit("no page target found")


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def send(self, method, params=None):
        self._id += 1
        msg_id = self._id
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = await self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


async def run(action, *args):
    ws_url = await _get_page_ws_url()
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        cdp = CDP(ws)
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")

        if action == "nav":
            url = args[0]
            await cdp.send("Page.navigate", {"url": url})
            await asyncio.sleep(2.5)

        elif action == "screenshot":
            path = args[0]
            result = await cdp.send("Page.captureScreenshot", {"format": "png"})
            with open(path, "wb") as f:
                f.write(base64.b64decode(result["data"]))
            print(path)

        elif action == "click":
            x, y = float(args[0]), float(args[1])
            await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

        elif action == "type":
            text = args[0]
            for ch in text:
                await cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": ch})
                await asyncio.sleep(0.02)

        elif action == "key":
            key = args[0]
            await cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
            await cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})

        elif action == "wait":
            await asyncio.sleep(float(args[0]))

        elif action == "drag":
            x1, y1, x2, y2 = (float(a) for a in args[:4])
            steps = 80
            await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x1, "y": y1, "button": "left", "buttons": 1, "clickCount": 1, "pointerType": "mouse"})
            await asyncio.sleep(0.1)
            for i in range(1, steps + 1):
                t = i / steps
                x = x1 + (x2 - x1) * t
                y = y1 + (y2 - y1) * t
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "left", "buttons": 1, "pointerType": "mouse"})
                await asyncio.sleep(0.015)
            await asyncio.sleep(0.3)
            await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x2, "y": y2, "button": "left", "buttons": 1, "pointerType": "mouse"})
            await asyncio.sleep(0.8)

        elif action == "touchdrag":
            x1, y1, x2, y2 = (float(a) for a in args[:4])
            await cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
            steps = 40
            pt = [{"x": x1, "y": y1, "id": 1}]
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt})
            await asyncio.sleep(0.1)
            for i in range(1, steps + 1):
                t = i / steps
                x = x1 + (x2 - x1) * t
                y = y1 + (y2 - y1) * t
                pt = [{"x": x, "y": y, "id": 1}]
                await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt})
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            await asyncio.sleep(0.8)

        elif action == "eval":
            expr = args[0]
            result = await cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            print(result.get("result", {}).get("value"))

        else:
            raise SystemExit(f"unknown action: {action}")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1], *sys.argv[2:]))
