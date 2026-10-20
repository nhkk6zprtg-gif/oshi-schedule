import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

API_KEY = os.environ['YOUTUBE_API_KEY']
API_BASE = 'https://www.googleapis.com/youtube/v3'
ARCHIVE_PAGES = 5
JST = ZoneInfo('Asia/Tokyo')
CHANNELS = [
    {'handle': '@kanae', 'file': 'schedule.json'},
    {'handle': '@kuzuha', 'file': 'schedule_kuzuha.json'},
]
GAME_RULES = [
    ('原神', [r'原神', r'genshin(?: impact)?']),
    ('崩壊：スターレイル', [r'崩壊[：: ]?スターレイル', r'スターレイル', r'honkai[: ]? star rail']),
    ('ゼンレスゾーンゼロ', [r'ゼンレスゾーンゼロ', r'ゼンゼロ', r'zenless zone zero']),
    ('VALORANT', [r'valorant', r'ヴァロラント', r'ヴァロ(?=[^ァ-ヶ]|$)']),
    ('Apex Legends', [r'apex(?: legends)?', r'エーペックス']),
    ('League of Legends', [r'league of legends', r'リーグ[・･ ]?オブ[・･ ]?レジェンド', r'(?<![a-z])lol(?![a-z])']),
    ('Minecraft', [r'minecraft', r'マインクラフト', r'マイクラ']),
    ('Overwatch', [r'overwatch(?: 2)?', r'オーバーウォッチ']),
    ('ストリートファイター6', [r'ストリートファイター[ ６6]', r'street fighter[ ６6]', r'(?<![a-z0-9])sf6(?![a-z0-9])']),
    ('雀魂', [r'雀魂', r'じゃんたま', r'mahjong soul']),
    ('ポケモン', [r'ポケモン', r'ポケットモンスター', r'pok[eé]mon']),
    ('スプラトゥーン', [r'スプラトゥーン', r'splatoon']),
    ('Grand Theft Auto V', [r'grand theft auto', r'(?<![a-z0-9])gta[ Ⅴv5]?(?![a-z0-9])']),
    ('ELDEN RING', [r'elden ring', r'エルデンリング']),
    ('ARK', [r'ark[: ]?survival', r'(?<![a-z])ark(?![a-z])']),
    ('モンスターハンター', [r'モンスターハンター', r'モンハン', r'monster hunter']),
    ('Escape from Tarkov', [r'escape from tarkov', r'タルコフ', r'(?<![a-z])eft(?![a-z])']),
    ('Rust', [r'(?<![a-z])rust(?![a-z])']),
    ('Dead by Daylight', [r'dead by daylight', r'(?<![a-z])dbd(?![a-z])', r'デッドバイデイライト']),
    ('Among Us', [r'among us', r'アモングアス', r'アモアス']),
    ('スーパーマリオ', [r'スーパーマリオ', r'super mario']),
    ('あつまれ どうぶつの森', [r'あつまれ[ 　]?どうぶつの森', r'あつ森', r'animal crossing']),
]


def youtube_api(endpoint, params):
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode({**params, 'key': API_KEY})}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode('utf-8', errors='replace')
        reason = ''
        try:
            info = json.loads(body)['error']
            reason = ', '.join(x.get('reason', '') for x in info.get('errors', []))
            message = info.get('message', '')
        except (ValueError, KeyError, TypeError):
            message = body[:300]
        raise RuntimeError(f'YouTube API {endpoint}: HTTP {error.code} ({reason}) {message}') from error


def load_existing(filename):
    try:
        with open(filename, encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def parse_datetime(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def parse_duration(value):
    match = re.fullmatch(r'P(?:([0-9]+)D)?T?(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?', value or '')
    if not match:
        return None
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total or None


def find_games(text):
    return [game for game, patterns in GAME_RULES if any(re.search(pattern, text or '', re.IGNORECASE) for pattern in patterns)]


def classify_game(title, description=''):
    title_games = find_games(title)
    if len(title_games) == 1:
        return title_games[0]
    if len(title_games) > 1:
        return None
    first_lines = []
    for line in (description or '').splitlines()[:5]:
        line = line.strip()
        if line and 'http' not in line.lower() and not line.startswith('#'):
            first_lines.append(line)
    desc_games = find_games('\n'.join(first_lines)[:300])
    return desc_games[0] if len(desc_games) == 1 else None


def get_video_details(video_ids):
    result = {}
    ids = list(dict.fromkeys(video_ids))
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        data = youtube_api('videos', {'part': 'snippet,contentDetails,liveStreamingDetails', 'id': ','.join(batch)})
        for item in data.get('items', []):
            result[item['id']] = item
    return result


def make_stream(video_id, item, fallback_time):
    snippet = item.get('snippet', {})
    live = item.get('liveStreamingDetails', {})
    content = item.get('contentDetails', {})
    thumbnails = snippet.get('thumbnails', {})
    thumbnail = next((thumbnails[k]['url'] for k in ('high', 'medium', 'default') if thumbnails.get(k, {}).get('url')), '')
    actual_start = live.get('actualStartTime')
    actual_end = live.get('actualEndTime')
    start_dt = parse_datetime(actual_start)
    end_dt = parse_datetime(actual_end)
    seconds = parse_duration(content.get('duration'))
    if start_dt and end_dt and end_dt > start_dt:
        seconds = int((end_dt - start_dt).total_seconds())
    title = snippet.get('title', '配信')
    description = snippet.get('description', '')
    return {
        'videoId': video_id,
        'title': title,
        'description': description,
        'thumbnail': thumbnail,
        'scheduledAt': actual_start or fallback_time,
        'actualStartTime': actual_start,
        'actualEndTime': actual_end,
        'durationSeconds': seconds,
        'game': classify_game(title, description),
        'url': f'https://www.youtube.com/watch?v={video_id}',
    }


def build_monthly_game_hours(streams):
    totals = defaultdict(int)
    for stream in streams:
        seconds = stream.get('durationSeconds')
        start = parse_datetime(stream.get('actualStartTime') or stream.get('scheduledAt'))
        if not isinstance(seconds, (int, float)) or seconds <= 0 or not start:
            continue
        month = start.astimezone(JST).strftime('%Y-%m')
        totals[(month, stream.get('game') or '未分類')] += int(seconds)
    output = {}
    for (month, game), seconds in totals.items():
        output.setdefault(month, []).append({'game': game, 'seconds': seconds, 'hours': round(seconds / 3600, 2)})
    for rows in output.values():
        rows.sort(key=lambda row: row['seconds'], reverse=True)
    return output


def collect_channel(config):
    handle = config['handle']
    filename = config['file']
    old_data = load_existing(filename)
    now = datetime.now(timezone.utc)
    print(f'取得開始: {handle}')

    channel_data = youtube_api('channels', {'part': 'id,snippet,contentDetails', 'forHandle': handle})
    channels = channel_data.get('items', [])
    if not channels:
        raise RuntimeError(f'YouTubeチャンネルが見つかりません: {handle}')
    channel = channels[0]
    channel_id = channel['id']
    uploads_playlist = channel['contentDetails']['relatedPlaylists']['uploads']

    # playlistItems costs 1 quota unit per request, unlike search.list (100 units).
    archive_ids = []
    page_token = None
    for _ in range(ARCHIVE_PAGES):
        params = {'part': 'contentDetails', 'playlistId': uploads_playlist, 'maxResults': 50}
        if page_token:
            params['pageToken'] = page_token
        page = youtube_api('playlistItems', params)
        archive_ids.extend(x['contentDetails']['videoId'] for x in page.get('items', []) if x.get('contentDetails', {}).get('videoId'))
        page_token = page.get('nextPageToken')
        if not page_token:
            break

    # Keep already saved upcoming IDs in the next refresh. New scheduled
    # livestreams generally appear in the channel uploads playlist.
    old_upcoming_ids = [x.get('videoId') for x in old_data.get('streams', []) if x.get('videoId')]
    details = get_video_details(archive_ids + old_upcoming_ids)
    upcoming = []
    saved_archives = {}
    for stream in old_data.get('pastStreams', []):
        video_id = stream.get('videoId')
        if not video_id:
            video_id = urllib.parse.parse_qs(urllib.parse.urlparse(stream.get('url', '')).query).get('v', [''])[0]
        if video_id:
            saved_archives[video_id] = stream

    for video_id, item in details.items():
        live = item.get('liveStreamingDetails', {})
        scheduled = live.get('scheduledStartTime')
        actual_start = live.get('actualStartTime')
        actual_end = live.get('actualEndTime')
        scheduled_dt = parse_datetime(scheduled)
        if scheduled_dt and scheduled_dt > now and not actual_start:
            upcoming.append(make_stream(video_id, item, scheduled))
        elif actual_start:
            saved_archives[video_id] = make_stream(video_id, item, actual_start)
        elif actual_end:
            saved_archives[video_id] = make_stream(video_id, item, scheduled or item.get('snippet', {}).get('publishedAt'))

    upcoming.sort(key=lambda x: x['scheduledAt'])
    past_streams = list(saved_archives.values())
    for stream in past_streams:
        if stream.get('durationSeconds'):
            stream['game'] = classify_game(stream.get('title', ''), stream.get('description', ''))
    past_streams.sort(key=lambda x: x.get('scheduledAt') or '', reverse=True)
    output = {
        'channel': {'id': channel_id, 'title': channel.get('snippet', {}).get('title', ''), 'url': f'https://www.youtube.com/{handle}'},
        'updatedAt': now.isoformat(),
        'streams': upcoming,
        'pastStreams': past_streams,
        'monthlyGameHours': build_monthly_game_hours(past_streams),
        'weeklySchedule': [{'day': jp, 'dayEn': en} for jp, en in [('月曜日', 'MON'), ('火曜日', 'TUE'), ('水曜日', 'WED'), ('木曜日', 'THU'), ('金曜日', 'FRI'), ('土曜日', 'SAT'), ('日曜日', 'SUN')]],
    }
    # Only write after every API request for this channel has succeeded.
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
    print(f'保存先: {filename} / 今後の配信予定: {len(upcoming)} 件 / 過去配信: {len(past_streams)} 件')


def main():
    errors = []
    for config in CHANNELS:
        try:
            collect_channel(config)
        except Exception as error:
            errors.append(f"{config['handle']}: {error}")
            print(f"取得失敗: {config['handle']} - {error}")
    if errors:
        raise RuntimeError(' / '.join(errors))


if __name__ == '__main__':
    main()
