import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ["YOUTUBE_API_KEY"]
HANDLE = "@kanae"
API_BASE = "https://www.googleapis.com/youtube/v3"
ARCHIVE_PAGES = 5


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


def main():
    old_data = load_existing()

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

    # 今後の配信予定を取得
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
        item["id"]["videoId"]
        for item in upcoming_data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]

    # チャンネルの動画一覧から過去の配信候補を取得
    archive_ids = []
    page_token = None

    for _ in range(ARCHIVE_PAGES):
        params = {
            "part": "snippet",
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

    # APIの動画詳細取得は一度に最大50件
    all_ids = list(dict.fromkeys(upcoming_ids + archive_ids))
    details = {}

    for start in range(0, len(all_ids), 50):
        batch = all_ids[start:start + 50]

        result = youtube_api(
            "videos",
            {
                "part": "snippet,liveStreamingDetails",
                "id": ",".join(batch),
            },
        )

        for item in result.get("items", []):
            details[item["id"]] = item

    upcoming = []

    for video_id in upcoming_ids:
        item = details.get(video_id)
        if not item:
            continue

        snippet = item.get("snippet", {})
        live = item.get("liveStreamingDetails", {})
        scheduled_at = live.get("scheduledStartTime")

        if not scheduled_at:
            continue

        upcoming.append({
            "videoId": video_id,
            "title": snippet.get("title", "配信予定"),
            "description": snippet.get("description", ""),
            "thumbnail": (
                snippet.get("thumbnails", {})
                .get("high", {})
                .get("url", "")
            ),
            "scheduledAt": scheduled_at,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    # 過去の配信を蓄積
    saved_archives = {
        item.get("videoId", item.get("url", "")): item
        for item in old_data.get("pastStreams", [])
    }

    for video_id in archive_ids:
        item = details.get(video_id)
        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        actual_start = live.get("actualStartTime")

        # 実際に開始されたライブ配信だけを対象にする
        if not actual_start:
            continue

        snippet = item.get("snippet", {})
        saved_archives[video_id] = {
            "videoId": video_id,
            "title": snippet.get("title", "過去の配信"),
            "description": snippet.get("description", ""),
            "thumbnail": (
                snippet.get("thumbnails", {})
                .get("high", {})
                .get("url", "")
            ),
            "scheduledAt": actual_start,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    past_streams = list(saved_archives.values())
    past_streams.sort(
        key=lambda stream: stream.get("scheduledAt", ""),
        reverse=True,
    )

    # 過去の配信が誤って未来の予定に混ざらないようにする
    now = datetime.now(timezone.utc)
    upcoming = [
        stream for stream in upcoming
        if datetime.fromisoformat(
            stream["scheduledAt"].replace("Z", "+00:00")
        ) > now
    ]
    upcoming.sort(key=lambda stream: stream["scheduledAt"])

    output = {
        "channel": {
            "id": channel_id,
            "title": channel.get("snippet", {}).get("title", ""),
            "url": "https://youtube.com/@kanae",
        },
        "updatedAt": now.isoformat(),
        "streams": upcoming,
        "pastStreams": past_streams,
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


if __name__ == "__main__":
    main()
