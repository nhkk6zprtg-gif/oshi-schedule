
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ["YOUTUBE_API_KEY"]
HANDLE = "@kanae"
API_BASE = "https://www.googleapis.com/youtube/v3"


def youtube_api(endpoint, params):
    params["key"] = API_KEY
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def main():
    channel_data = youtube_api(
        "channels",
        {
            "part": "id,snippet",
            "forHandle": HANDLE,
        },
    )

    channels = channel_data.get("items", [])
    if not channels:
        raise RuntimeError(
            f"YouTubeチャンネルが見つかりません: {HANDLE}"
        )

    channel = channels[0]
    channel_id = channel["id"]

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

    streams = []

    for item in upcoming_data.get("items", []):
        video_id = item["id"].get("videoId")
        snippet = item.get("snippet", {})

        if not video_id:
            continue

        streams.append(
            {
                "title": snippet.get("title", "配信予定"),
                "description": snippet.get("description", ""),
                "thumbnail": snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url", ""),
                "scheduledAt": snippet.get("publishedAt", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    output = {
        "channel": {
            "id": channel_id,
            "title": channel.get("snippet", {}).get("title", ""),
            "url": "https://youtube.com/@kanae",
        },
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "streams": streams,
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

    print(f"配信予定を {len(streams)} 件取得しました。")


if __name__ == "__main__":
    main()
