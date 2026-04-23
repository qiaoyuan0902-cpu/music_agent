import os
import json
import anthropic
from config import MAX_TOKENS
from agent.system_prompt import build_system_prompt
from agent.tools.definitions import TOOLS
from agent.tools.dispatcher import dispatch
from memory import conversation as conv_store


# ── Client factories ──────────────────────────────────────────
def _make_anthropic_client() -> anthropic.Anthropic:
    token = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "")
    kwargs: dict = {"api_key": token}
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["auth_token"] = token
    return anthropic.Anthropic(**kwargs)


def _make_openai_client():
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "") or None
    return OpenAI(api_key=api_key, base_url=base_url)


def _get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "claude").lower()


def _get_model() -> str:
    provider = _get_provider()
    if provider == "claude":
        return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    return os.getenv("OPENAI_MODEL", "gpt-4o")


# ── Anthropic tools → OpenAI tools format ────────────────────
def _to_openai_tools(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


# ── Special sentinel yields ───────────────────────────────────
def _check_special_yields(tool_name: str, result: str):
    """Return a sentinel string if the tool result needs UI action, else None."""
    if tool_name == "play_song":
        try:
            song = json.loads(result)
            if song.get("__play__"):
                return f"__PLAY_SONG__{json.dumps(song, ensure_ascii=False)}"
        except Exception:
            pass
    elif tool_name == "switch_tts_voice":
        try:
            data = json.loads(result)
            if data.get("__switch_voice__"):
                return f"__SWITCH_VOICE__{data['voice_id']}"
        except Exception:
            pass
    return None


class MusicAgent:
    def __init__(self):
        pass

    # ── Public streaming entry point ──────────────────────────
    def chat_stream(self, user_message: str, history: list):
        provider = _get_provider()
        if provider == "claude":
            yield from self._stream_claude(user_message)
        else:
            yield from self._stream_openai(user_message)

    # ── Claude (Anthropic SDK) ────────────────────────────────
    def _stream_claude(self, user_message: str):
        messages = conv_store.load_recent()
        messages.append({"role": "user", "content": user_message})
        system_prompt = build_system_prompt()
        full_response = ""

        while True:
            with _make_anthropic_client().messages.stream(
                model=_get_model(),
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                current_text = ""
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta" and hasattr(event, "delta"):
                            if event.delta.type == "text_delta":
                                current_text += event.delta.text
                                full_response += event.delta.text
                                yield full_response

                final_message = stream.get_final_message()

            messages.append({"role": "assistant", "content": final_message.content})

            if final_message.stop_reason == "end_turn":
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", full_response)
                return

            elif final_message.stop_reason == "tool_use":
                tool_results = []
                tool_names = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        tool_names.append(block.name)
                        result = dispatch(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        sentinel = _check_special_yields(block.name, result)
                        if sentinel:
                            yield sentinel

                hint = _tool_hint(tool_names)
                if hint:
                    full_response += f"\n\n*{hint}*\n\n"
                    yield full_response

                messages.append({"role": "user", "content": tool_results})
            else:
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", full_response)
                return

    # ── OpenAI-compatible (OpenAI / Qwen) ────────────────────
    def _stream_openai(self, user_message: str):
        messages = conv_store.load_recent()
        # Convert Anthropic-style history to OpenAI flat format
        oai_messages = _to_openai_messages(messages)
        oai_messages.append({"role": "user", "content": user_message})
        system_prompt = build_system_prompt()
        oai_messages.insert(0, {"role": "system", "content": system_prompt})

        oai_tools = _to_openai_tools(TOOLS)
        full_response = ""
        client = _make_openai_client()
        model = _get_model()

        while True:
            stream = client.chat.completions.create(
                model=model,
                messages=oai_messages,
                tools=oai_tools,
                stream=True,
            )

            collected_text = ""
            tool_calls_acc: dict[int, dict] = {}
            finish_reason = None

            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                if delta.content:
                    collected_text += delta.content
                    full_response += delta.content
                    yield full_response

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

            if finish_reason == "tool_calls" and tool_calls_acc:
                tool_calls_list = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in (tool_calls_acc[i] for i in sorted(tool_calls_acc))
                ]
                oai_messages.append({
                    "role": "assistant",
                    "content": collected_text or None,
                    "tool_calls": tool_calls_list,
                })

                tool_names = []
                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    tool_names.append(name)
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    result = dispatch(name, args)
                    oai_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                    sentinel = _check_special_yields(name, result)
                    if sentinel:
                        yield sentinel

                hint = _tool_hint(tool_names)
                if hint:
                    full_response += f"\n\n*{hint}*\n\n"
                    yield full_response
            else:
                oai_messages.append({"role": "assistant", "content": collected_text})
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", full_response)
                return

    # ── Non-streaming (kept for compatibility) ────────────────
    def chat(self, user_message: str, history: list) -> str:
        result = ""
        for chunk in self.chat_stream(user_message, history):
            if not chunk.startswith("__"):
                result = chunk
        return result

    @staticmethod
    def _extract_text(content) -> str:
        for block in content:
            if hasattr(block, "type") and block.type == "text":
                return block.text
        return ""


# ── Helpers ───────────────────────────────────────────────────
def _to_openai_messages(anthropic_messages: list) -> list:
    """Convert Anthropic-style messages to OpenAI flat format (best-effort)."""
    result = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            result.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Flatten text blocks; skip tool_use/tool_result blocks
            text = " ".join(
                b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                for b in content
                if (isinstance(b, dict) and b.get("type") == "text")
                or (hasattr(b, "type") and b.type == "text")
            )
            if text:
                result.append({"role": role, "content": text})
    return result


_TOOL_HINTS = {
    "play_song":           "正在搜索并准备播放...",
    "switch_tts_voice":    "正在切换声音...",
    "get_current_weather": "正在获取天气信息...",
    "update_user_profile": "正在记录你的偏好...",
}


def _tool_hint(tool_names: list) -> str:
    hints = [_TOOL_HINTS.get(n, f"调用 {n}...") for n in tool_names]
    return " | ".join(hints)
