
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://shop.nijisanji.jp"

PEOPLE = {
    "叶": {
        "url": BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100",
        "file": "announcements.json",
    },
    "葛葉": {
        "url": BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009",
        "file": "announcements_kuzuha.json",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja-JP,ja;q=0.9",
}

MAX_PRODUCTS = 12


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.products = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()

        if self.current is None:
            if tag == "div" and "card-container" in classes:
                if attrs.get("data-pid"):
                    self.current = {
                        "id": attrs["data-pid"],
                        "title": "",
                        "url": "",
                        "imageUrl": "",
                    }
                    self.depth = 1
            return

        if tag == "div":
            self.depth += 1

        if tag == "a" and not self.current["url"]:
            href = attrs.get("href", "")
            if href:
                self.current["url"] = urljoin(BASE, href)

        if tag == "img":
            if not self.current["imageUrl"]:
                src = (
                    attrs.get("data-src")
                    or attrs.get("src")
                    or ""
                )
                if src:
                    self.current["imageUrl"] = urljoin(BASE, src)

            if not self.current["title"]:
                self.current["title"] = attrs.get("alt", "").strip()

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            self.depth -= 1

            if self.depth == 0:
                if self.current["url"] and self.current["title"]:
                    self.products.append(self.current)
                self.current = None


class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def get_livers(html):
    parser = DetailParser()
    parser.feed(html)

    text = " ".join(parser.parts)

    # 商品ページにある「ライバー」欄を取得
    match = re.search(
        r"ライバー\s+(.+?)\s+(?:続き(?:を)?見る|関連タグ|商品を選択)",
        text,
    )

    if not match:
        return ""

    return match.group(1).strip()


def is_related(name, title, livers):
    if name in title:
        return True

    # ライバー欄に名前が独立して存在する場合
    pattern = rf"(?<![一-龯ぁ-んァ-ン]){re.escape(name)}(?![一-龯ぁ-んァ-ン])"

    return bool(re.search(pattern, livers))


def clean_title(title):
    title = re.sub(r"\s+", " ", title).strip()

    # 同じ商品名が二重にある場合は整理
    if len(title) % 2 == 0:
        half = len(title) // 2
        if title[:half] == title[half:]:
            title = title[:half]

    return title


def load_existing(path):
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("announcements", [])
    except Exception:
        return []


def update_person(name, settings):
    print(f"\n========== {name} ==========", flush=True)

    html = fetch(settings["url"])
    parser = ProductParser()
    parser.feed(html)

    products = parser.products[:MAX_PRODUCTS]

    print("取得商品数:", len(products), flush=True)

    if not products:
        print("取得失敗の可能性があるため更新を中止")
        return

    matched = []

    for product in products:
        title = clean_title(product["title"])

        try:
            detail_html = fetch(product["url"])
            livers = get_livers(detail_html)

            related = is_related(name, title, livers)

            print("商品:", title, flush=True)
            print("参加ライバー:", livers[:180], flush=True)
            print("判定:", related, flush=True)

            if related:
                matched.append({
                    "type": "goods",
                    "title": title,
                    "date": "",
                    "salesPeriod": "",
                    "imageUrl": product["imageUrl"],
                    "url": product["url"],
                })

            time.sleep(0.2)

        except Exception as error:
            print("詳細取得エラー:", repr(error), flush=True)

    print("本人関連商品数:", len(matched), flush=True)

    if not matched:
        print("一致商品なし。既存データを維持します")
        return

    path = Path(settings["file"])
    existing = load_existing(path)

    # 手動登録済みの告知は削除しない
    merged = matched[:]
    seen = {item["url"] for item in merged}

    for item in existing:
        url = item.get("url", "")
        if not url or url not in seen:
            merged.append(item)
            if url:
                seen.add(url)

    path.write_text(
        json.dumps(
            {"announcements": merged},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("保存先:", path, flush=True)
    print("保存件数:", len(merged), flush=True)


def main():
    for name, settings in PEOPLE.items():
        update_person(name, settings)


if __name__ == "__main__":
    main()
