
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

API_KEY = os.environ["YOUTUBE_API_KEY"]
HANDLE = "@kanae"
API_BASE = "https://www.googleapis.com/youtube/v3"
ARCHIVE_PAGES = 5
JST = ZoneInfo("Asia/Tokyo")


def youtube_api(endpoint, params):
    params = dict(params)
    params["key"] = API_KEY
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def load_existing():
    try:
        with open("schedule.json", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def parse_duration(value):
    """YouTubeのISO 8601動画時間を秒数に変換する。"""
    if not value:
        return None

    match = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        value,
    )
    if not match:
        return None

    hours, minutes, seconds = (
        int(part or 0) for part in match.groups()
    )
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def classify_game(title):
    """タイトルに明示されたゲーム名だけを判定する。"""
    text = (title or "").lower()

    rules = [
        ("原神", ["原神", "genshin impact", "genshin"]),
        ("崩壊：スターレイル", [
            "崩壊スターレイル", "崩壊：スターレイル",
            "スターレイル", "honkai: star rail",
        ]),
        ("ゼンレスゾーンゼロ", [
            "ゼンレスゾーンゼロ", "ゼンゼロ",
            "zenless zone zero",
        ]),
        ("VALORANT", ["valorant", "ヴァロラント"]),
        ("Apex Legends", ["apex legends", "apex", "エーペックス"]),
        ("League of Legends", [
            "league of legends", "リーグ・オブ・レジェンド",
            "lol",
        ]),
        ("Minecraft", ["minecraft", "マインクラフト", "マイクラ"]),
        ("Overwatch", ["overwatch", "オーバーウォッチ"]),
        ("ストリートファイター6", [
            "ストリートファイター6", "street fighter 6", "sf6",
        ]),
        ("雀魂", ["雀魂", "じゃんたま", "mahjong soul"]),
        ("ポケモン", ["ポケモン", "pokemon"]),
        ("スプラトゥーン", ["スプラトゥーン", "splatoon"]),
        ("Grand Theft Auto V", [
            "grand theft auto", "gta v", "gta5", "gtaオンライン",
        ]),
        ("ELDEN RING", ["elden ring", "エルデンリング"]),
        ("ARK", ["ark: survival", "ark survival", "ark"]),
        ("モンスターハンター", [
            "モンスターハンター", "monster hunter",
        ]),
        ("VALORANT", ["ヴァロ"]),
    ]

    for game, keywords in rules:
        for keyword in keywords:
            if keyword in text:
                # 「lol」などの短い語は単語として判定
                if keyword == "lol" and not re.search(
                    r"(?<![a-z])lol(?![a-z])", text
                ):
                    continue
                if keyword == "ark" and not re.search(
                    r"(?<![a-z])ark(?![a-z])", text
                ):
                    continue
                return game

    return None


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def get_video_details(video_ids):
    details = {}
    unique_ids = list(dict.fromkeys(video_ids))

    for start in range(0, len(unique_ids), 50):
        batch = unique_ids[start:start + 50]
        if not batch:
            continue

        result = youtube_api(
            "videos",
            {
                "part": "snippet,contentDetails,liveStreamingDetails",
                "id": ",".join(batch),
            },
        )

        for item in result.get("items", []):
            details[item["id"]] = item

    return details


def make_stream(video_id, item, date_value):
    snippet = item.get("snippet", {})
    live = item.get("liveStreamingDetails", {})
    content = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails", {})

    thumbnail = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url", "")
    )

    duration_seconds = parse_duration(content.get("duration"))
    actual_start = live.get("actualStartTime")
    actual_end = live.get("actualEndTime")

    start_dt = parse_datetime(actual_start)
    end_dt = parse_datetime(actual_end)

    # 開始・終了時刻が両方ある場合は実際の配信時間を優先
    if start_dt and end_dt and end_dt > start_dt:
        duration_seconds = int((end_dt - start_dt).total_seconds())

    title = snippet.get("title", "配信")

    return {
        "videoId": video_id,
        "title": title,
        "description": snippet.get("description", ""),
        "thumbnail": thumbnail,
        "scheduledAt": actual_start or date_value,
        "actualStartTime": actual_start,
        "actualEndTime": actual_end,
        "durationSeconds": duration_seconds,
        "game": classify_game(title),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def build_monthly_game_hours(streams):
    totals = defaultdict(int)

    for stream in streams:
        seconds = stream.get("durationSeconds")
        game = stream.get("game")
        start = parse_datetime(stream.get("scheduledAt"))

        # 時間・ゲーム名・開始日時が確認できる配信だけ集計
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            continue
        if not game or not start:
            continue

        month = start.astimezone(JST).strftime("%Y-%m")
        totals[(month, game)] += int(seconds)

    result = {}

    for (month, game), seconds in totals.items():
        result.setdefault(month, []).append({
            "game": game,
            "seconds": seconds,
            "hours": round(seconds / 3600, 2),
        })

    for month in result:
        result[month].sort(
            key=lambda item: item["seconds"],
            reverse=True,
        )

    return result


def main():
    old_data = load_existing()
    now = datetime.now(timezone.utc)

    channel_data = youtube_api(
        "channels",
        {
            "part": "id,snippet,contentDetails",
            "forHandle": HANDLE,
        },
    )

    channels = channel_data.get("items", [])
    if not channels:
        raise RuntimeError(f"YouTubeチャンネルが見つかりません: {HANDLE}")

    channel = channels[0]
    channel_id = channel["id"]
    uploads_playlist = (
        channel["contentDetails"]["relatedPlaylists"]["uploads"]
    )

    upcoming_data = youtube_api(
        "search",
        {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "eventType": "upcoming",
            "order": "date",
            "maxResults": 25,
        },
    )

    upcoming_ids = [
        entry["id"]["videoId"]
        for entry in upcoming_data.get("items", [])
        if entry.get("id", {}).get("videoId")
    ]

    archive_ids = []
    page_token = None

    for _ in range(ARCHIVE_PAGES):
        params = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        page = youtube_api("playlistItems", params)

        for entry in page.get("items", []):
            video_id = entry.get("contentDetails", {}).get("videoId")
            if video_id:
                archive_ids.append(video_id)

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
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        page = youtube_api("search", params)

        for entry in page.get("items", []):
            video_id = entry.get("id", {}).get("videoId")
            if video_id:
                completed_ids.append(video_id)

        page_token = page.get("nextPageToken")
        if not page_token:
            break

    completed_id_set = set(completed_ids)
    all_archive_ids = list(dict.fromkeys(archive_ids + completed_ids))
    all_ids = list(dict.fromkeys(upcoming_ids + all_archive_ids))
    details = get_video_details(all_ids)

    upcoming = []

    for video_id in upcoming_ids:
        item = details.get(video_id)
        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        scheduled_at = live.get("scheduledStartTime")
        stream_time = parse_datetime(scheduled_at)

        if stream_time and stream_time > now:
            upcoming.append(make_stream(video_id, item, scheduled_at))

    upcoming.sort(key=lambda stream: stream["scheduledAt"])

    # 既存アーカイブを保持し、取得できた動画情報で更新
    saved_archives = {}

    for stream in old_data.get("pastStreams", []):
        video_id = stream.get("videoId")

        if not video_id:
            url = stream.get("url", "")
            video_id = url.split("v=")[-1] if "v=" in url else ""

        if video_id:
            saved_archives[video_id] = stream

    for video_id in all_archive_ids:
        item = details.get(video_id)
        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        actual_start = live.get("actualStartTime")

        if not actual_start and video_id in completed_id_set:
            actual_start = item.get("snippet", {}).get("publishedAt")

        if not actual_start:
            continue

        saved_archives[video_id] = make_stream(
            video_id,
            item,
            actual_start,
        )

    past_streams = list(saved_archives.values())
    past_streams.sort(
        key=lambda stream: stream.get("scheduledAt", ""),
        reverse=True,
    )

    output = {
        "channel": {
            "id": channel_id,
            "title": channel.get("snippet", {}).get("title", ""),
            "url": "https://youtube.com/@kanae",
        },
        "updatedAt": now.isoformat(),
        "streams": upcoming,
        "pastStreams": past_streams,
        "monthlyGameHours": build_monthly_game_hours(past_streams),
        "weeklySchedule": [
            {"day": "月曜日", "dayEn": "MON"},
            {"day": "火曜日", "dayEn": "TUE"},
            {"day": "水曜日", "dayEn": "WED"},
            {"day": "木曜日", "dayEn": "THU"},
            {"day": "金曜日", "dayEn": "FRI"},
            {"day": "土曜日", "dayEn": "SAT"},
            {"day": "日曜日", "dayEn": "SUN"},
        ],
    }

    with open("schedule.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"今後の配信予定: {len(upcoming)} 件")
    print(f"保存済みの過去配信: {len(past_streams)} 件")
    print(f"月別集計対象: {sum(len(v) for v in output['monthlyGameHours'].values())} 件")


if __name__ == "__main__":
    main()
