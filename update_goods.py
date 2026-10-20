
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://shop.nijisanji.jp"

SOURCES = {
    "叶": {
        "url": BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100",
        "file": "announcements.json",
    },
    "葛葉": {
        "url": BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009",
        "file": "announcements_kuzuha.json",
    },
}


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.products = []
        self.current = None
        self.depth = 0
        self.price_depth = None
        self.name_depth = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()

        if self.current is None:
            if (
                tag == "div"
                and "card-container" in classes
                and attrs.get("data-pid")
            ):
                self.current = {
                    "id": attrs["data-pid"],
                    "title": "",
                    "url": "",
                    "imageUrl": "",
                    "price": "",
                }
                self.depth = 1
            return

        if tag == "div":
            self.depth += 1

        if tag == "a" and not self.current["url"]:
            href = attrs.get("href", "")
            if href:
                self.current["url"] = urljoin(BASE, href)

        if tag == "img" and not self.current["imageUrl"]:
            src = (
                attrs.get("data-src")
                or attrs.get("src")
                or ""
            )
            if src:
                self.current["imageUrl"] = urljoin(BASE, src)

            alt = attrs.get("alt", "").strip()
            if alt:
                self.current["title"] = alt

        if "card-price" in classes or "text-price" in classes:
            self.price_depth = self.depth

        if any(c in classes for c in [
            "card-name",
            "card-title",
            "card-product-name",
        ]):
            self.name_depth = self.depth

    def handle_data(self, data):
        if self.current is None:
            return

        value = " ".join(data.split())
        if not value:
            return

        if self.price_depth is not None:
            if re.search(r"[\d,]+", value):
                self.current["price"] += value + " "

        if self.name_depth is not None:
            self.current["title"] += value + " "

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            if self.price_depth == self.depth:
                self.price_depth = None

            if self.name_depth == self.depth:
                self.name_depth = None

            self.depth -= 1

            if self.depth == 0:
                self.current["title"] = (
                    self.current["title"].strip()
                )
                self.current["price"] = (
                    self.current["price"].strip()
                )
                self.products.append(self.current)
                self.current = None
                self.price_depth = None
                self.name_depth = None


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def load_existing(filename):
    path = Path(filename)

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("announcements", [])
        return items if isinstance(items, list) else []
    except (ValueError, OSError, AttributeError):
        return []


def save_announcements(filename, items):
    path = Path(filename)

    data = {
        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
        "announcements": items,
    }

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8",
    )


def main():
    for name, config in SOURCES.items():
        print("\n==========", name, "==========")

        try:
            page = fetch(config["url"])
            parser = ProductParser()
            parser.feed(page)

            print("取得した商品数:", len(parser.products))

            if not parser.products:
                print("商品が取得できないため更新を中止")
                continue

            existing = load_existing(config["file"])

            manual = [
                item for item in existing
                if item.get("source") != "nijisanji_store"
            ]

            goods = []
            seen = set()

            for product in parser.products:
                title = product["title"]
                url = product["url"]

                if name not in title:
                    continue

                if not title or not url:
                    continue

                if url in seen:
                    continue

                seen.add(url)

                goods.append({
                    "type": (
                        "voice"
                        if "ボイス" in title
                        else "goods"
                    ),
                    "title": title,
                    "date": "",
                    "salesPeriod": "",
                    "imageUrl": product["imageUrl"],
                    "url": url,
                    "price": product["price"],
                    "source": "nijisanji_store",
                })

            print("本人関連商品数:", len(goods))

            if not goods:
                print(
                    "本人関連商品が見つからないため"
                    "既存ファイルを維持"
                )
                continue

            merged = manual + goods

            save_announcements(
                config["file"],
                merged
            )

            print("保存先:", config["file"])
            print("保存件数:", len(merged))

            for item in goods[:5]:
                print("商品:", item["title"])
                print("URL:", item["url"])

        except Exception as error:
            print("更新失敗:", repr(error))


if __name__ == "__main__":
    main()
