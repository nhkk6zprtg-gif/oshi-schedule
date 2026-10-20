
import json
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

API_KEY = os.environ["YOUTUBE_API_KEY"]
API_BASE = "https://www.googleapis.com/youtube/v3"
ARCHIVE_PAGES = 5
JST = ZoneInfo("Asia/Tokyo")

CHANNELS = [
    {"handle": "@kanae", "file": "schedule.json"},
    {"handle": "@kuzuha", "file": "schedule_kuzuha.json"},
]

GAME_RULES = [
    ("原神", [r"原神", r"genshin(?: impact)?"]),
    ("崩壊：スターレイル", [r"崩壊[：: ]?スターレイル", r"スターレイル", r"honkai[: ]? star rail"]),
    ("ゼンレスゾーンゼロ", [r"ゼンレスゾーンゼロ", r"ゼンゼロ", r"zenless zone zero"]),
    ("VALORANT", [r"valorant", r"ヴァロラント", r"ヴァロ(?=[^ァ-ヶ]|$)"]),
    ("Apex Legends", [r"apex(?: legends)?", r"エーペックス"]),
    ("League of Legends", [r"league of legends", r"リーグ[・･ ]?オブ[・･ ]?レジェンド", r"(?<![a-z])lol(?![a-z])"]),
    ("Minecraft", [r"minecraft", r"マインクラフト", r"マイクラ"]),
    ("Overwatch", [r"overwatch(?: 2)?", r"オーバーウォッチ"]),
    ("ストリートファイター6", [r"ストリートファイター[ ６6]", r"street fighter[ ６6]", r"(?<![a-z0-9])sf6(?![a-z0-9])"]),
    ("雀魂", [r"雀魂", r"じゃんたま", r"mahjong soul"]),
    ("ポケモン", [r"ポケモン", r"ポケットモンスター", r"pok[eé]mon"]),
    ("スプラトゥーン", [r"スプラトゥーン", r"splatoon"]),
    ("Grand Theft Auto V", [r"grand theft auto", r"(?<![a-z0-9])gta[ Ⅴv5]?(?![a-z0-9])"]),
    ("ELDEN RING", [r"elden ring", r"エルデンリング"]),
    ("ARK", [r"ark[: ]?survival", r"(?<![a-z])ark(?![a-z])"]),
    ("モンスターハンター", [r"モンスターハンター", r"モンハン", r"monster hunter"]),
    ("Escape from Tarkov", [r"escape from tarkov", r"タルコフ", r"(?<![a-z])eft(?![a-z])"]),
    ("Rust", [r"(?<![a-z])rust(?![a-z])"]),
    ("Dead by Daylight", [r"dead by daylight", r"(?<![a-z])dbd(?![a-z])", r"デッドバイデイライト"]),
    ("Among Us", [r"among us", r"アモングアス", r"アモアス"]),
    ("スーパーマリオ", [r"スーパーマリオ", r"super mario"]),
    ("あつまれ どうぶつの森", [r"あつまれ[ 　]?どうぶつの森", r"あつ森", r"animal crossing"]),
]


def youtube_api(endpoint, params):
    params = {**params, "key": API_KEY}
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def load_existing(filename):
    try:
        with open(filename, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def parse_datetime(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def parse_duration(value):
    match = re.fullmatch(
        r"P(?:([0-9]+)D)?T?(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?",
        value or ""
    )
    if not match:
        return None
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total or None


def find_games(text):
    text = (text or "").lower()
    return [
        game for game, patterns in GAME_RULES
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    ]


def classify_game(title, description=""):
    title_games = find_games(title)
    if len(title_games) == 1:
        return title_games[0]
    if len(title_games) > 1:
        return None

    first_lines = []
    for line in (description or "").splitlines()[:5]:
        line = line.strip()
        if not line or "http" in line.lower() or line.startswith("#"):
            continue
        first_lines.append(line)

    desc_games = find_games("\n".join(first_lines)[:300])
    return desc_games[0] if len(desc_games) == 1 else None


def get_video_details(video_ids):
    result = {}
    ids = list(dict.fromkeys(video_ids))
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        if not batch:
            continue
        data = youtube_api(
            "videos",
            {
                "part": "snippet,contentDetails,liveStreamingDetails",
                "id": ",".join(batch)
            }
        )
        for item in data.get("items", []):
            result[item["id"]] = item
    return result


def make_stream(video_id, item, fallback_time):
    snippet = item.get("snippet", {})
    live = item.get("liveStreamingDetails", {})
    content = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails", {})

    thumbnail = next(
        (
            thumbnails[k]["url"]
            for k in ("high", "medium", "default")
            if thumbnails.get(k, {}).get("url")
        ),
        ""
    )

    actual_start = live.get("actualStartTime")
    actual_end = live.get("actualEndTime")
    start_dt = parse_datetime(actual_start)
    end_dt = parse_datetime(actual_end)

    seconds = parse_duration(content.get("duration"))
    if start_dt and end_dt and end_dt > start_dt:
        seconds = int((end_dt - start_dt).total_seconds())

    title = snippet.get("title", "配信")
    description = snippet.get("description", "")

    return {
        "videoId": video_id,
        "title": title,
        "description": description,
        "thumbnail": thumbnail,
        "scheduledAt": actual_start or fallback_time,
        "actualStartTime": actual_start,
        "actualEndTime": actual_end,
        "durationSeconds": seconds,
        "game": classify_game(title, description),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def build_monthly_game_hours(streams):
    totals = defaultdict(int)

    for stream in streams:
        seconds = stream.get("durationSeconds")
        start = parse_datetime(
            stream.get("actualStartTime") or stream.get("scheduledAt")
        )
        if not isinstance(seconds, (int, float)) or seconds <= 0 or not start:
            continue

        game = stream.get("game") or "未分類"
        month = start.astimezone(JST).strftime("%Y-%m")
        totals[(month, game)] += int(seconds)

    output = {}
    for (month, game), seconds in totals.items():
        output.setdefault(month, []).append({
            "game": game,
            "seconds": seconds,
            "hours": round(seconds / 3600, 2)
        })

    for rows in output.values():
        rows.sort(key=lambda row: row["seconds"], reverse=True)

    return output


def collect_channel(config):
    handle = config["handle"]
    filename = config["file"]
    old_data = load_existing(filename)
    now = datetime.now(timezone.utc)

    print(f"\n取得開始: {handle}")

    channel_data = youtube_api(
        "channels",
        {
            "part": "id,snippet,contentDetails",
            "forHandle": handle
        }
    )
    channels = channel_data.get("items", [])
    if not channels:
        raise RuntimeError(f"YouTubeチャンネルが見つかりません: {handle}")

    channel = channels[0]
    channel_id = channel["id"]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    upcoming_data = youtube_api(
        "search",
        {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "eventType": "upcoming",
            "order": "date",
            "maxResults": 25
        }
    )
    upcoming_ids = [
        x["id"]["videoId"]
        for x in upcoming_data.get("items", [])
        if x.get("id", {}).get("videoId")
    ]

    archive_ids = []
    page_token = None

    for _ in range(ARCHIVE_PAGES):
        params = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 50
        }
        if page_token:
            params["pageToken"] = page_token

        page = youtube_api("playlistItems", params)
        archive_ids.extend(
            x["contentDetails"]["videoId"]
            for x in page.get("items", [])
            if x.get("contentDetails", {}).get("videoId")
        )
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    completed_ids = []
    page_token = None

    for _ in range(ARCHIVE_PAGES):
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "eventType": "completed",
            "order": "date",
            "maxResults": 50
        }
        if page_token:
            params["pageToken"] = page_token

        page = youtube_api("search", params)
        completed_ids.extend(
            x["id"]["videoId"]
            for x in page.get("items", [])
            if x.get("id", {}).get("videoId")
        )
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    completed_set = set(completed_ids)
    all_archive_ids = list(dict.fromkeys(archive_ids + completed_ids))
    details = get_video_details(
        list(dict.fromkeys(upcoming_ids + all_archive_ids))
    )

    upcoming = []
    for video_id in upcoming_ids:
        item = details.get(video_id)
        if not item:
            continue

        scheduled = item.get(
            "liveStreamingDetails", {}
        ).get("scheduledStartTime")

        scheduled_dt = parse_datetime(scheduled)
        if scheduled_dt and scheduled_dt > now:
            upcoming.append(make_stream(video_id, item, scheduled))

    upcoming.sort(key=lambda x: x["scheduledAt"])

    saved_archives = {}
    for stream in old_data.get("pastStreams", []):
        video_id = stream.get("videoId")
        if not video_id:
            url = stream.get("url", "")
            video_id = urllib.parse.parse_qs(
                urllib.parse.urlparse(url).query
            ).get("v", [""])[0]

        if video_id:
            saved_archives[video_id] = stream

    for video_id in all_archive_ids:
        item = details.get(video_id)
        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        actual_start = live.get("actualStartTime")

        if not actual_start and video_id not in completed_set:
            continue

        fallback = actual_start or item.get(
            "snippet", {}
        ).get("publishedAt")

        if not fallback:
            continue

        saved_archives[video_id] = make_stream(
            video_id, item, fallback
        )

    past_streams = list(saved_archives.values())

    for stream in past_streams:
        if stream.get("durationSeconds"):
            stream["game"] = classify_game(
                stream.get("title", ""),
                stream.get("description", "")
            )

    past_streams.sort(
        key=lambda x: x.get("scheduledAt") or "",
        reverse=True
    )

    monthly = build_monthly_game_hours(past_streams)

    output = {
        "channel": {
            "id": channel_id,
            "title": channel.get("snippet", {}).get("title", ""),
            "url": f"https://www.youtube.com/{handle}"
        },
        "updatedAt": now.isoformat(),
        "streams": upcoming,
        "pastStreams": past_streams,
        "monthlyGameHours": monthly,
        "weeklySchedule": [
            {"day": jp, "dayEn": en}
            for jp, en in [
                ("月曜日", "MON"),
                ("火曜日", "TUE"),
                ("水曜日", "WED"),
                ("木曜日", "THU"),
                ("金曜日", "FRI"),
                ("土曜日", "SAT"),
                ("日曜日", "SUN")
            ]
        ]
    }

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"保存先: {filename}")
    print(f"今後の配信予定: {len(upcoming)} 件")
    print(f"保存済みの過去配信: {len(past_streams)} 件")
    print(f"月別集計対象: {sum(len(rows) for rows in monthly.values())} 件")


def main():
    errors = []

    for config in CHANNELS:
        try:
            collect_channel(config)
        except Exception as error:
            errors.append(f"{config['handle']}: {error}")
            print(f"取得失敗: {config['handle']} - {error}")

    if errors:
        raise RuntimeError(" / ".join(errors))


if __name__ == "__main__":
    main()
