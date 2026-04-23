import os
import anthropic
from config import CLAUDE_MODEL, MAX_TOKENS
from agent.system_prompt import build_system_prompt
from agent.tools.definitions import TOOLS
from agent.tools.dispatcher import dispatch
from memory import conversation as conv_store


def _make_client() -> anthropic.Anthropic:
    """每次调用时读取最新的环境变量，确保向导保存后能生效。
    当设置了 base_url（自定义代理）时，同时传 auth_token，
    让 SDK 发 Authorization: Bearer header，兼容 Bilibili 等代理。
    """
    token = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "")
    kwargs: dict = {"api_key": token}
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["auth_token"] = token   # 代理需要 Authorization: Bearer header
    return anthropic.Anthropic(**kwargs)


class MusicAgent:
    def __init__(self):
        pass  # client 在每次请求时创建，确保读到最新 key

    def chat(self, user_message: str, history: list[list]) -> str:
        """
        处理用户消息，返回完整回复文本。
        history: Gradio 格式的历史 [[user, assistant], ...]
        """
        # 构建 messages（从持久化历史加载）
        messages = conv_store.load_recent()

        # 追加当前用户消息
        messages.append({"role": "user", "content": user_message})

        system_prompt = build_system_prompt()

        # Agentic loop
        while True:
            response = _make_client().messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

            # 收集本次响应的所有 content blocks
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # 提取文本回复
                text = self._extract_text(response.content)
                # 持久化本轮对话
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", text)
                return text

            elif response.stop_reason == "tool_use":
                # 执行所有工具调用
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = dispatch(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

            else:
                # 其他停止原因，直接返回
                text = self._extract_text(response.content)
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", text)
                return text

    def chat_stream(self, user_message: str, history: list[list]):
        """
        流式版本，用于 Gradio streaming。
        yield 文本片段，工具调用期间 yield 状态提示。
        """
        messages = conv_store.load_recent()
        messages.append({"role": "user", "content": user_message})
        system_prompt = build_system_prompt()

        full_response = ""

        while True:
            with _make_client().messages.stream(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                collected_content = []
                current_text = ""

                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_start":
                            if hasattr(event, "content_block"):
                                collected_content.append(event.content_block)
                        elif event.type == "content_block_delta":
                            if hasattr(event, "delta"):
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
                        # 如果是播放工具，yield 特殊标记让 UI 层触发播放
                        if block.name == "play_song":
                            import json as _json
                            try:
                                song = _json.loads(result)
                                if song.get("__play__"):
                                    yield f"__PLAY_SONG__{_json.dumps(song, ensure_ascii=False)}"
                            except Exception:
                                pass
                        # 如果是切换声音工具，yield 特殊标记
                        elif block.name == "switch_tts_voice":
                            import json as _json
                            try:
                                data = _json.loads(result)
                                if data.get("__switch_voice__"):
                                    yield f"__SWITCH_VOICE__{data['voice_id']}"
                            except Exception:
                                pass

                # 显示工具调用状态
                tool_hint = _tool_hint(tool_names)
                if tool_hint:
                    full_response += f"\n\n*{tool_hint}*\n\n"
                    yield full_response

                messages.append({"role": "user", "content": tool_results})
            else:
                conv_store.save_turn("user", user_message)
                conv_store.save_turn("assistant", full_response)
                return

    @staticmethod
    def _extract_text(content) -> str:
        for block in content:
            if hasattr(block, "type") and block.type == "text":
                return block.text
        return ""


_TOOL_HINTS = {
    "play_song":         "正在搜索并准备播放...",
    "switch_tts_voice":  "正在切换声音...",
    "get_current_weather": "正在获取天气信息...",
    "update_user_profile": "正在记录你的偏好...",
}


def _tool_hint(tool_names: list) -> str:
    hints = [_TOOL_HINTS.get(n, f"调用 {n}...") for n in tool_names]
    return " | ".join(hints)
