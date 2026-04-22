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
        "name": "search_tracks",
        "description": "在 Spotify 上搜索歌曲。用于用户想找特定歌曲、歌手或专辑时。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如歌曲名、艺术家名、专辑名，支持中英文"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5，最多 10",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_recommendations",
        "description": "基于种子艺术家、风格或歌曲获取 Spotify 推荐歌曲。用于推荐场景。",
        "input_schema": {
            "type": "object",
            "properties": {
                "seed_genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "风格种子列表，如 ['pop', 'jazz', 'indie']，最多 3 个"
                },
                "seed_artists": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "艺术家名字列表（Spotify 艺术家 ID 或名字），最多 2 个"
                },
                "limit": {
                    "type": "integer",
                    "description": "推荐数量，默认 6",
                    "default": 6
                }
            },
            "required": []
        }
    },
    {
        "name": "get_artist_top_tracks",
        "description": "获取某位艺术家在 Spotify 上的热门歌曲。",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {
                    "type": "string",
                    "description": "艺术家名字，支持中英文"
                }
            },
            "required": ["artist_name"]
        }
    },
    {
        "name": "get_similar_artists",
        "description": "通过 Last.fm 获取与某艺术家风格相似的其他艺术家。",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist": {
                    "type": "string",
                    "description": "艺术家名字"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认 5",
                    "default": 5
                }
            },
            "required": ["artist"]
        }
    },
    {
        "name": "get_tracks_by_mood",
        "description": "通过 Last.fm 按心情/风格标签获取热门歌曲。适合用户说'推荐适合下雨天的歌'这类请求。",
        "input_schema": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "风格或情绪标签，英文，如 'rainy day', 'jazz', 'chill', 'happy'"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认 6",
                    "default": 6
                }
            },
            "required": ["tag"]
        }
    },
    {
        "name": "get_lyrics",
        "description": "通过 Genius 获取歌曲歌词。",
        "input_schema": {
            "type": "object",
            "properties": {
                "song": {
                    "type": "string",
                    "description": "歌曲名"
                },
                "artist": {
                    "type": "string",
                    "description": "艺术家名（可选，提供后搜索更准确）",
                    "default": ""
                }
            },
            "required": ["song"]
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
