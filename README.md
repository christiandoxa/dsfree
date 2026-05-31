# dsfree

Minimal Python client for the current `chat.deepseek.com` web chat endpoints.

This project is unofficial and depends on private web behavior. It can stop
working when DeepSeek changes the site, authentication, proof-of-work flow, or
stream format.

## Install

Use Python 3.10 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Authentication

Preferred: let the CLI ask for the token. Input is hidden and does not enter
shell history.

```bash
python dsfree.py
```

Do not commit tokens, cookies, or generated credential files.

## Quick Test

```bash
python example.py
```

## CLI

Start an interactive chat:

```bash
python dsfree.py
```

By default, the CLI deletes the temporary DeepSeek web chat when it exits. Use
`--keep-history` only if you want the chat to stay visible in the web UI.

Send one prompt and exit without putting the token in shell history:

```bash
printf 'Reply only with: pong' | python dsfree.py
```

Argument and environment modes are still supported:

```bash
python dsfree.py <token> "Reply only with: pong"
DEEPSEEK_AUTH_TOKEN='your-token' python dsfree.py
```

## API Server

Run a local API compatible with the DeepSeek/OpenAI chat-completions shape:

```bash
export DEEPSEEK_AUTH_TOKEN='your-web-token'
export DSFREE_API_KEY='local-api-key'
python api_server.py --host 127.0.0.1 --port 8000
```

Call it with curl:

```bash
curl http://127.0.0.1:8000/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local-api-key' \
  -d '{
    "model": "deepseek-v4-pro",
    "messages": [
      {"role": "system", "content": "You are concise."},
      {"role": "user", "content": "Reply only with: pong"}
    ],
    "thinking": {"type": "disabled"},
    "stream": false
  }'
```

Use it with the OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    api_key="local-api-key",
    base_url="http://127.0.0.1:8000",
)

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "Reply only with: pong"}],
)
print(response.choices[0].message.content)
```

Supported endpoints:

- `GET /health`
- `GET /models`
- `GET /v1/models`
- `POST /chat/completions`
- `POST /v1/chat/completions`

Streaming is supported with `stream: true` and sends `data: [DONE]` at the end.

By default, each API request creates a temporary web chat and deletes it after
the response finishes, so it should not remain in the DeepSeek web history.
Set `"keep_history": true` per request or `DSFREE_KEEP_HISTORY=1` on the server
to keep chats visible.

## Minimal Usage

```python
from dsk.api import DeepSeekAPI

api = DeepSeekAPI("your-token")
chat_id = api.create_chat_session()

for chunk in api.chat_completion(
    chat_id,
    "Reply only with: pong",
    thinking_enabled=False,
    search_enabled=False,
):
    if chunk["type"] == "text":
        print(chunk["content"], end="", flush=True)
```

## Notes

- Streaming responses are parsed from DeepSeek's current patch-style event
  stream.
- `thinking_enabled=True` returns thinking chunks when the web endpoint emits
  them.
- `search_enabled=True` asks the web endpoint to use search when available.
- Cloudflare or AWS WAF challenges may require a fresh browser session.

## Security

Keep credentials outside the repository. Safest local-only pattern:

```bash
python dsfree.py
```
