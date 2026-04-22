TOOLS = [
    {
        "name": "play_song",
        "description": "在网易云音乐上搜索并立即播放一首歌曲。当用户说'播放'、'放一首'、'我想听'等时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "song_name": {
                    "type": "string",
                    "description": "歌曲名称"
                },
                "artist": {
                    "type": "string",
                    "description": "艺术家名字（可选，提供后搜索更准确）",
                    "default": ""
                }
            },
            "required": ["song_name"]
        }
    },
    {
        "name": "switch_tts_voice",
        "description": "切换语音助手的朗读声音。当用户要求换声音、换男声/女声、换方言时调用。可用声音：晓晓（普通话女，默认）、晓伊（活泼女）、小北（东北女）、小妮（陕西女）、云希（普通话男）、云健（新闻男）、云夏（年轻男）、云扬（播音男）、晓佳（粤语女）、云龙（粤语男）、晓臻（台湾女）、云哲（台湾男）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_name": {
                    "type": "string",
                    "description": "声音名称，从可用声音列表中选择，如'云希'、'晓晓'等"
                }
            },
            "required": ["voice_name"]
        }
    },
    {
        "name": "get_current_weather",
        "description": "获取用户当前所在城市的实时天气信息。在推荐音乐前可以先查天气。",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名，留空则自动通过 IP 定位",
                    "default": ""
                }
            },
            "required": []
        }
    },
    {
        "name": "update_user_profile",
        "description": "更新用户的音乐偏好画像。当用户表达喜好时调用，如'我喜欢爵士乐'、'这首歌真好听'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "liked_genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新增喜欢的音乐风格，英文小写，如 ['jazz', 'pop']"
                },
                "liked_artists": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新增喜欢的艺术家"
                },
                "disliked_genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新增不喜欢的风格"
                },
                "notes": {
                    "type": "string",
                    "description": "其他值得记录的偏好备注"
                }
            },
            "required": []
        }
    },
]
