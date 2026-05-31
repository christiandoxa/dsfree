import argparse
import json
import os
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

from dsk.api import APIError, AuthenticationError, DeepSeekAPI, NetworkError, RateLimitError


load_dotenv()


app = FastAPI(
    title="dsfree API",
    version="0.1.0",
    description="OpenAI-compatible wrapper for chat.deepseek.com web chat.",
)


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def require_api_key(authorization: Optional[str]) -> None:
    expected = os.getenv("DSFREE_API_KEY")
    if not expected:
        return
    provided = extract_bearer(authorization)
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_upstream_token() -> str:
    token = os.getenv("DEEPSEEK_AUTH_TOKEN")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="DEEPSEEK_AUTH_TOKEN is not set on the server",
        )
    return token


def normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in ("text", "input_text"):
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def build_prompt(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        content = normalize_content(message.get("content")).strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    if not lines:
        raise HTTPException(status_code=400, detail="messages must contain content")
    return "\n".join(lines)


def wants_thinking(body: Dict[str, Any]) -> bool:
    thinking = body.get("thinking")
    if isinstance(thinking, dict):
        return thinking.get("type") == "enabled"
    model = body.get("model")
    return model == "deepseek-reasoner"


def make_usage(prompt: str, content: str, reasoning: str = "") -> Dict[str, Any]:
    prompt_tokens = max(1, len(prompt.split()))
    completion_tokens = max(1, len((content + " " + reasoning).split())) if content or reasoning else 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": prompt_tokens,
        "completion_tokens_details": {
            "reasoning_tokens": max(0, len(reasoning.split())),
        },
    }


def make_completion(
    completion_id: str,
    created: int,
    model: str,
    content: str,
    reasoning: str,
    prompt: str,
) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    if reasoning:
        message["reasoning_content"] = reasoning

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "system_fingerprint": "dsfree-web",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": make_usage(prompt, content, reasoning),
    }


def sse(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_chunks(
    api: DeepSeekAPI,
    chat_id: str,
    prompt: str,
    model: str,
    thinking_enabled: bool,
    search_enabled: bool,
    completion_id: str,
    created: int,
    include_usage: bool,
) -> Iterable[str]:
    yield sse(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": "dsfree-web",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                    "logprobs": None,
                }
            ],
            "usage": None,
        }
    )

    content_parts = []
    reasoning_parts = []

    try:
        for chunk in api.chat_completion(
            chat_id,
            prompt,
            thinking_enabled=thinking_enabled,
            search_enabled=search_enabled,
        ):
            chunk_type = chunk.get("type")
            content = chunk.get("content") or ""
            if chunk_type == "thinking" and content:
                reasoning_parts.append(content)
                delta = {"reasoning_content": content}
            elif chunk_type == "text" and content:
                content_parts.append(content)
                delta = {"content": content}
            else:
                continue

            yield sse(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "system_fingerprint": "dsfree-web",
                    "choices": [
                        {
                            "index": 0,
                            "delta": delta,
                            "finish_reason": None,
                            "logprobs": None,
                        }
                    ],
                    "usage": None,
                }
            )
    except Exception as exc:
        yield sse({"error": {"message": str(exc), "type": exc.__class__.__name__}})
        yield "data: [DONE]\n\n"
        return

    yield sse(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": "dsfree-web",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                    "logprobs": None,
                }
            ],
            "usage": None,
        }
    )

    if include_usage:
        yield sse(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "system_fingerprint": "dsfree-web",
                "choices": [],
                "usage": make_usage(prompt, "".join(content_parts), "".join(reasoning_parts)),
            }
        )

    yield "data: [DONE]\n\n"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
@app.get("/v1/models")
def models(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(authorization)
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": "deepseek-v4-pro", "object": "model", "created": now, "owned_by": "dsfree"},
            {"id": "deepseek-v4-flash", "object": "model", "created": now, "owned_by": "dsfree"},
            {"id": "deepseek-chat", "object": "model", "created": now, "owned_by": "dsfree"},
            {"id": "deepseek-reasoner", "object": "model", "created": now, "owned_by": "dsfree"},
        ],
    }


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def chat_completions_async(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Any:
    require_api_key(authorization)
    body = await request.json()
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    prompt = build_prompt(messages)
    model = body.get("model") or "deepseek-v4-pro"
    stream = bool(body.get("stream"))
    search_enabled = bool(body.get("search_enabled") or body.get("search"))
    thinking_enabled = wants_thinking(body)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    try:
        api = DeepSeekAPI(get_upstream_token())
        chat_id = api.create_chat_session()
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (APIError, NetworkError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if stream:
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        return StreamingResponse(
            stream_chunks(
                api,
                chat_id,
                prompt,
                model,
                thinking_enabled,
                search_enabled,
                completion_id,
                created,
                include_usage,
            ),
            media_type="text/event-stream",
        )

    content_parts = []
    reasoning_parts = []
    try:
        for chunk in api.chat_completion(
            chat_id,
            prompt,
            thinking_enabled=thinking_enabled,
            search_enabled=search_enabled,
        ):
            if chunk.get("type") == "thinking":
                reasoning_parts.append(chunk.get("content") or "")
            elif chunk.get("type") == "text":
                content_parts.append(chunk.get("content") or "")
            if chunk.get("finish_reason") == "stop":
                break
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (APIError, NetworkError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JSONResponse(
        make_completion(
            completion_id,
            created,
            model,
            "".join(content_parts),
            "".join(reasoning_parts),
            prompt,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dsfree OpenAI-compatible API server")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run("api_server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
