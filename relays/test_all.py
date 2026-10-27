import asyncio
import json

import numpy as np
import soundfile as sf
import websockets

ENGINES = {
    "whispercpp": "ws://localhost:8765",
    "openaiwhisper": "ws://localhost:8766",
}

FORMATS = {"whispercpp": "int16", "openaiwhisper": "int16"}


async def run_one(name, url, audio_bytes, wait_s):
    results = []
    try:
        async with websockets.connect(url, max_size=None) as ws:
            async def reader():
                try:
                    async for msg in ws:
                        results.append(json.loads(msg))
                except Exception:
                    pass

            reader_task = asyncio.create_task(reader())
            bytes_per_sample = 4 if FORMATS[name] == "float32" else 2
            chunk = int(0.1 * 16000) * bytes_per_sample
            for i in range(0, len(audio_bytes), chunk):
                await ws.send(audio_bytes[i:i + chunk])
                await asyncio.sleep(0.1)  # real-time pacing: 0.1s of audio per 0.1s
            await asyncio.sleep(wait_s)
            reader_task.cancel()
    except Exception as e:
        return name, f"ERROR: {e}"
    texts = [r.get("text", "") for r in results if r.get("text")]
    return name, (texts[-1] if texts else "(no output)")


async def main():
    audio, sr = sf.read("whisper.cpp/samples/jfk.wav")
    assert sr == 16000
    audio_i16 = (audio * 32767).astype(np.int16)

    bytes_by_format = {"int16": audio_i16.tobytes()}
    waits = {"whispercpp": 10, "openaiwhisper": 10}
    tasks = [
        run_one(name, url, bytes_by_format[FORMATS[name]], waits[name])
        for name, url in ENGINES.items()
    ]
    results = await asyncio.gather(*tasks)
    for name, text in results:
        print(f"=== {name} ===\n{text}\n")


asyncio.run(main())
