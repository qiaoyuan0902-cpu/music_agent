import gradio as gr
from agent.core import MusicAgent
from memory import conversation as conv_store
from weather.locator import get_city_by_ip
from weather.fetcher import get_weather

agent = MusicAgent()

_CSS = """
/* ── 全局背景 ── */
body, .gradio-container {
    background: #0f0f1a !important;
    font-family: -apple-system, 'PingFang SC', 'Helvetica Neue', sans-serif !important;
}
.gradio-container {
    max-width: 420px !important;
    margin: 0 auto !important;
    padding: 0 !important;
    min-height: 100vh;
}

/* ── 顶部状态栏 ── */
#top-bar {
    background: linear-gradient(180deg, #1a1a3e 0%, #0f0f1a 100%);
    padding: 16px 20px 12px;
    border-bottom: 1px solid #2a2a4a;
}

/* ── 聊天区域 ── */
#chatbot {
    background: transparent !important;
    border: none !important;
    height: calc(100vh - 220px) !important;
    min-height: 400px;
    padding: 8px 12px !important;
}
#chatbot .message-wrap {
    padding: 4px 0;
}
/* 用户气泡 */
#chatbot .user .message {
    background: linear-gradient(135deg, #6c63ff, #a855f7) !important;
    color: #fff !important;
    border-radius: 18px 18px 4px 18px !important;
    padding: 10px 14px !important;
    max-width: 78% !important;
    font-size: 14px !important;
    box-shadow: 0 2px 8px rgba(108,99,255,0.3);
}
/* AI 气泡 */
#chatbot .bot .message {
    background: #1e1e3a !important;
    color: #e8e8f0 !important;
    border-radius: 18px 18px 18px 4px !important;
    padding: 10px 14px !important;
    max-width: 82% !important;
    font-size: 14px !important;
    border: 1px solid #2a2a4a;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
#chatbot .bot .message p { margin: 4px 0; }
#chatbot .bot .message ul { padding-left: 16px; margin: 4px 0; }

/* ── 快捷标签 ── */
#quick-tags {
    padding: 8px 12px;
    background: #0f0f1a;
    overflow-x: auto;
    white-space: nowrap;
    scrollbar-width: none;
}
#quick-tags::-webkit-scrollbar { display: none; }
.quick-tag-btn {
    display: inline-block !important;
    background: #1e1e3a !important;
    color: #a0a0c0 !important;
    border: 1px solid #2a2a4a !important;
    border-radius: 20px !important;
    padding: 5px 12px !important;
    margin-right: 8px !important;
    font-size: 12px !important;
    cursor: pointer;
    white-space: nowrap;
    min-width: unset !important;
}
.quick-tag-btn:hover {
    background: #2a2a5a !important;
    border-color: #6c63ff !important;
    color: #fff !important;
}

/* ── 底部输入区 ── */
#input-area {
    background: #141428;
    border-top: 1px solid #2a2a4a;
    padding: 10px 12px 16px;
    position: sticky;
    bottom: 0;
}
#msg-input textarea {
    background: #1e1e3a !important;
    border: 1px solid #2a2a4a !important;
    border-radius: 24px !important;
    color: #e8e8f0 !important;
    padding: 10px 16px !important;
    font-size: 14px !important;
    resize: none !important;
    min-height: 44px !important;
    max-height: 120px !important;
}
#msg-input textarea:focus {
    border-color: #6c63ff !important;
    box-shadow: 0 0 0 2px rgba(108,99,255,0.2) !important;
    outline: none !important;
}
#msg-input textarea::placeholder { color: #555580 !important; }
#send-btn {
    background: linear-gradient(135deg, #6c63ff, #a855f7) !important;
    border: none !important;
    border-radius: 50% !important;
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    padding: 0 !important;
    font-size: 18px !important;
    box-shadow: 0 2px 8px rgba(108,99,255,0.4);
    align-self: flex-end;
}
#send-btn:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(108,99,255,0.5);
}

/* ── 清除按钮 ── */
#clear-btn {
    background: transparent !important;
    border: 1px solid #3a3a5a !important;
    color: #888 !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    padding: 4px 10px !important;
}

/* 隐藏 Gradio 默认元素 */
footer { display: none !important; }
.gr-prose { display: none !important; }
#component-0 > .gap { gap: 0 !important; }
"""

_QUICK_TAGS = [
    ("🌤 天气推荐", "根据今天的天气给我推荐几首歌"),
    ("🎵 搜索歌曲", "帮我搜索"),
    ("🎸 相似艺术家", "推荐和我喜欢的艺术家风格相似的"),
    ("🌙 深夜氛围", "推荐几首适合深夜听的歌"),
    ("☕ 工作专注", "推荐适合工作时听的背景音乐"),
    ("💃 元气满满", "推荐几首让人心情好的歌"),
]


def _get_weather_bar() -> str:
    try:
        city = get_city_by_ip()
        w = get_weather(city)
        icons = {
            "clear": "☀️", "clouds": "☁️", "rain": "🌧️",
            "drizzle": "🌦️", "snow": "❄️", "thunderstorm": "⛈️",
            "mist": "🌫️", "fog": "🌫️", "haze": "🌫️",
        }
        icon = icons.get(w.get("weather_main", ""), "🌡️")
        return f"""
        <div id="top-bar">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="color:#a0a0c0; font-size:11px; letter-spacing:1px;">NOW PLAYING MOOD</div>
                    <div style="color:#fff; font-size:18px; font-weight:600; margin-top:2px;">🎵 音乐小助手</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:28px;">{icon}</div>
                    <div style="color:#e8e8f0; font-size:13px;">{w['city']} {w['temp']}°C</div>
                    <div style="color:#888; font-size:11px;">{w['description']}</div>
                </div>
            </div>
        </div>
        """
    except Exception:
        return """
        <div id="top-bar">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="color:#a0a0c0; font-size:11px;">NOW PLAYING MOOD</div>
                    <div style="color:#fff; font-size:18px; font-weight:600; margin-top:2px;">🎵 音乐小助手</div>
                </div>
                <div style="color:#888; font-size:12px;">天气加载中...</div>
            </div>
        </div>
        """


def clear_memory():
    conv_store.clear_history()
    return []


def build_ui():
    with gr.Blocks(title="🎵 音乐小助手") as demo:

        # 顶部天气栏
        gr.HTML(_get_weather_bar())

        # 聊天区
        chatbot = gr.Chatbot(
            elem_id="chatbot",
            show_label=False,
            avatar_images=(None, "https://api.dicebear.com/7.x/bottts/svg?seed=music"),
            layout="bubble",
            render_markdown=True,
        )

        # 快捷标签横向滚动
        with gr.Row(elem_id="quick-tags"):
            tag_btns = []
            for label, prompt in _QUICK_TAGS:
                btn = gr.Button(label, elem_classes=["quick-tag-btn"], size="sm")
                tag_btns.append((btn, prompt))

        # 底部输入区
        with gr.Row(elem_id="input-area", equal_height=True):
            msg = gr.Textbox(
                placeholder="和我聊聊音乐吧...",
                show_label=False,
                scale=9,
                container=False,
                elem_id="msg-input",
                lines=1,
                max_lines=4,
            )
            send_btn = gr.Button("➤", scale=1, elem_id="send-btn", variant="primary")

        # 清除按钮（折叠在底部）
        with gr.Row():
            clear_btn = gr.Button("🗑 清除记忆", elem_id="clear-btn", size="sm")

        # ── 事件 ──
        def submit(message, history):
            if not message.strip():
                yield history, ""
                return
            history = history or []
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "▌"})
            yield history, ""
            full = ""
            for chunk in agent.chat_stream(message, history[:-2]):
                full = chunk
                history[-1]["content"] = full + " ▌"
                yield history, ""
            history[-1]["content"] = full
            yield history, ""

        msg.submit(submit, [msg, chatbot], [chatbot, msg])
        send_btn.click(submit, [msg, chatbot], [chatbot, msg])
        clear_btn.click(clear_memory, outputs=[chatbot])

        # 快捷标签点击 → 填入输入框
        for btn, prompt in tag_btns:
            btn.click(lambda p=prompt: p, outputs=msg)

    return demo


def launch():
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=_CSS,
    )
