import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import StreamingResponse
import httpx
import websockets
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Using the same v1alpha URL format the client previously used
GEMINI_WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={GEMINI_KEY}"

@app.post("/v1/chat/completions")
async def proxy_openrouter(request: Request):
    body = await request.body()
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/humphi/humphi",
        "X-Title": "Humphi AI"
    }

    async def stream_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", OPENROUTER_URL, headers=headers, content=body) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    try:
        data = json.loads(body)
        is_stream = data.get("stream", False)
    except:
        is_stream = False

    if is_stream:
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(OPENROUTER_URL, headers=headers, content=body)
            # Proxy headers back just in case, or just return json
            return response.json()

@app.websocket("/ws/gemini-live")
async def proxy_gemini_live(ws: WebSocket):
    await ws.accept()
    
    # We open a connection to Gemini Live and pipe messages bidirectionally
    try:
        async with websockets.connect(GEMINI_WS_URL) as gemini_ws:
            async def client_to_gemini():
                try:
                    while True:
                        message = await ws.receive()
                        if "text" in message:
                            await gemini_ws.send(message["text"])
                        elif "bytes" in message:
                            await gemini_ws.send(message["bytes"])
                except Exception as e:
                    print(f"Client disconnected: {e}")

            async def gemini_to_client():
                try:
                    while True:
                        response = await gemini_ws.recv()
                        if isinstance(response, str):
                            await ws.send_text(response)
                        else:
                            await ws.send_bytes(response)
                except Exception as e:
                    print(f"Gemini disconnected: {e}")

            await asyncio.gather(client_to_gemini(), gemini_to_client(), return_exceptions=True)
    except Exception as e:
        print(f"Error connecting to Gemini: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
