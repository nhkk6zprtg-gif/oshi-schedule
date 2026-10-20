
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
        "search": "https://shop.nijisanji.jp/searchAjax?cgid=1019&secondCgid=M01-04-0100",
        "output": "announcements.json",
    },
    "葛葉": {
        "search": "https://shop.nijisanji.jp/searchAjax?cgid=1042&secondCgid=M01-04-0009",
        "output": "announcements_kuzuha.json",
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
        self.in_link = False
        self.in_image = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()

        if self.current is None and "card-container" in classes:
            self.current = {
                "id": attrs.get("data-pid", ""),
                "title": "",
                "url": "",
                "image": "",
            }
            self.depth = 1
            return

        if self.current is None:
            return

        if tag == "div":
            self.depth += 1

        if tag == "a" and not self.current["url"]:
            self.current["url"] = urljoin(
                BASE, attrs.get("href", "")
            )

        if tag == "img" and not self.current["image"]:
            image = (
                attrs.get("data-src")
                or attrs.get("src")
                or ""
            )
            self.current["image"] = urljoin(BASE, image)
            self.current["title"] = (
                attrs.get("alt")
                or attrs.get("title")
                or ""
            )

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                if self.current["url"] and self.current["title"]:
                    self.products.append(self.current)
                self.current = None


class TextParser(HTMLParser):
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


def detail_matches(html, name):
    parser = TextParser()
    parser.feed(html)
    text = " ".join(parser.parts)

    # 商品詳細の「ライバー」欄を優先して確認
    for match in re.finditer("ライバー", text):
        nearby = text[match.end():match.end() + 450]

        # 次の項目に移ったらそこで区切る
        nearby = re.split(
            r"関連タグ|商品詳細|商品説明|おすすめ商品|"
            r"関連商品|注意事項|販売期間",
            nearby,
            maxsplit=1,
        )[0]

        if name in nearby:
            return True

    return False


def clean_title(title):
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(
        r"\s+¥[\d,]+(?:\s*[〜～~-]\s*¥[\d,]+)?.*$",
        "",
        title,
    )
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

    html = fetch(settings["search"])
    parser = ProductParser()
    parser.feed(html)

    products = parser.products[:MAX_PRODUCTS]
    print("取得した商品数:", len(products), flush=True)

    if not products:
        print("商品を取得できなかったため更新しません")
        return

    results = []
    checked = set()

    for product in products:
        url = product["url"]

        if url in checked:
            continue
        checked.add(url)

        title = clean_title(product["title"])
        matched = name in title

        if not matched:
            try:
                detail_html = fetch(url)
                matched = detail_matches(detail_html, name)
                time.sleep(0.2)
            except Exception as error:
                print("詳細取得エラー:", url, str(error))
                continue

        if not matched:
            continue

        print("対象商品:", title, flush=True)

        results.append({
            "type": "goods",
            "title": title,
            "date": "",
            "salesPeriod": "",
            "imageUrl": product["image"],
            "url": url,
        })

    print("本人関連商品数:", len(results), flush=True)

    if not results:
        print("該当商品がないため既存データを維持します")
        return

    path = Path(settings["output"])
    existing = load_existing(path)

    # 既存の手動登録や過去の商品を残す
    merged = results[:]
    seen = {item["url"] for item in merged}

    for item in existing:
        url = item.get("url", "")
        if url and url not in seen:
            merged.append(item)
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
    errors = []

    for name, settings in PEOPLE.items():
        try:
            update_person(name, settings)
        except Exception as error:
            print(name, "取得エラー:", str(error), flush=True)
            errors.append(name)

    if errors:
        raise RuntimeError(
            "取得に失敗: " + ", ".join(errors)
        )


if __name__ == "__main__":
    main()
