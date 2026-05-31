import argparse
import getpass
import os
import sys

from dsk.api import APIError, AuthenticationError, DeepSeekAPI, NetworkError, RateLimitError


def stream_response(api, chat_id, prompt, parent_message_id=None, thinking=False, search=False):
    next_parent_id = parent_message_id

    for chunk in api.chat_completion(
        chat_id,
        prompt,
        parent_message_id=parent_message_id,
        thinking_enabled=thinking,
        search_enabled=search,
    ):
        if chunk.get("message_id"):
            next_parent_id = chunk["message_id"]
        if chunk.get("type") == "thinking" and chunk.get("content"):
            print(chunk["content"], end="", flush=True)
        if chunk.get("type") == "text" and chunk.get("content"):
            print(chunk["content"], end="", flush=True)
        if chunk.get("finish_reason") == "stop":
            break

    print()
    return next_parent_id


def parse_args():
    parser = argparse.ArgumentParser(description="Small CLI for chat.deepseek.com")
    parser.add_argument(
        "token",
        nargs="?",
        help="DeepSeek web session token. Falls back to DEEPSEEK_AUTH_TOKEN.",
    )
    parser.add_argument("prompt", nargs="*", help="Optional one-shot prompt.")
    parser.add_argument("--thinking", action="store_true", help="Enable DeepThink when available.")
    parser.add_argument("--search", action="store_true", help="Enable web search when available.")
    return parser.parse_args()


def main():
    args = parse_args()
    token = args.token or os.getenv("DEEPSEEK_AUTH_TOKEN")

    if not token:
        token = getpass.getpass("Token: ").strip()
        if not token:
            print("Missing token.", file=sys.stderr)
            return 2

    try:
        api = DeepSeekAPI(token)
        chat_id = api.create_chat_session()
        parent_message_id = None

        if args.prompt:
            prompt = " ".join(args.prompt)
            stream_response(
                api,
                chat_id,
                prompt,
                parent_message_id=parent_message_id,
                thinking=args.thinking,
                search=args.search,
            )
            return 0

        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
            if not prompt:
                print("Empty prompt on stdin.", file=sys.stderr)
                return 2
            stream_response(
                api,
                chat_id,
                prompt,
                parent_message_id=parent_message_id,
                thinking=args.thinking,
                search=args.search,
            )
            return 0

        print("Interactive mode. Type exit or press Ctrl-D to quit.")
        while True:
            try:
                prompt = input("> ").strip()
            except EOFError:
                print()
                break

            if prompt.lower() in {"exit", "quit"}:
                break
            if not prompt:
                continue

            parent_message_id = stream_response(
                api,
                chat_id,
                prompt,
                parent_message_id=parent_message_id,
                thinking=args.thinking,
                search=args.search,
            )

        return 0

    except AuthenticationError as exc:
        print(f"Authentication error: {exc}", file=sys.stderr)
        return 1
    except RateLimitError as exc:
        print(f"Rate limit error: {exc}", file=sys.stderr)
        return 1
    except NetworkError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except APIError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
