
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
                "part": "snippet,liveStreamingDetails",
                "id": ",".join(batch),
            },
        )

        for item in result.get("items", []):
            details[item["id"]] = item

    return details


def make_stream(video_id, item, date_value):
    snippet = item.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})

    thumbnail = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url", "")
    )

    return {
        "videoId": video_id,
        "title": snippet.get("title", "配信"),
        "description": snippet.get("description", ""),
        "thumbnail": thumbnail,
        "scheduledAt": date_value,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def main():
    old_data = load_existing()
    now = datetime.now(timezone.utc)

    # チャンネル情報を取得
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
        entry["id"]["videoId"]
        for entry in upcoming_data.get("items", [])
        if entry.get("id", {}).get("videoId")
    ]

    # チャンネルの動画一覧から過去の動画候補を取得
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

    # 配信済みのライブ配信を検索
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

    # 動画の詳細を取得
    details = get_video_details(all_ids)

    # 今後の配信予定を作成
    upcoming = []

    for video_id in upcoming_ids:
        item = details.get(video_id)

        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        scheduled_at = live.get("scheduledStartTime")

        if not scheduled_at:
            continue

        try:
            stream_time = datetime.fromisoformat(
                scheduled_at.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        if stream_time > now:
            upcoming.append(make_stream(video_id, item, scheduled_at))

    upcoming.sort(key=lambda stream: stream["scheduledAt"])

    # 既に保存済みの過去配信を保持
    saved_archives = {}

    for stream in old_data.get("pastStreams", []):
        video_id = stream.get("videoId")

        if not video_id:
            url = stream.get("url", "")
            video_id = url.split("v=")[-1] if "v=" in url else ""

        if video_id:
            saved_archives[video_id] = stream

    # 新しい過去配信を追加・更新
    for video_id in all_archive_ids:
        item = details.get(video_id)

        if not item:
            continue

        live = item.get("liveStreamingDetails", {})
        actual_start = live.get("actualStartTime")

        # 配信済み検索で見つかったライブは公開日時も補助的に利用
        if not actual_start and video_id in completed_id_set:
            actual_start = item.get("snippet", {}).get("publishedAt")

        # 通常の動画は過去配信として登録しない
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
    print(f"今回検索した配信済みライブ: {len(completed_ids)} 件")


if __name__ == "__main__":
    main()
