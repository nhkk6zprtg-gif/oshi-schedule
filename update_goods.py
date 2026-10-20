
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

DATE_PATTERN = (
    r"20\d{2}\s*[年/.-]\s*"
    r"\d{1,2}\s*[月/.-]\s*"
    r"\d{1,2}\s*日?"
    r"(?:\s*[（(][月火水木金土日][）)])?"
    r"(?:\s*\d{1,2}:\d{2})?"
)

PERIOD_PATTERN = re.compile(
    rf"({DATE_PATTERN})\s*[～〜~\-－]\s*"
    rf"({DATE_PATTERN})"
)

DELIVERY_PATTERN = re.compile(
    r"(20\d{2}年\d{1,2}月"
    r"(?:上旬|中旬|下旬|末|頃|ごろ|以降|予定|"
    r"\d{1,2}日)*)"
)

def fetch(url):
    request = urllib.request.Request(
        url, headers=HEADERS
    )
    with urllib.request.urlopen(
        request, timeout=30
    ) as response:
        return response.read().decode(
            "utf-8", errors="replace"
        )


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
                }
                self.depth = 1
            return

        if tag == "div":
            self.depth += 1

        if tag == "a" and not self.current["url"]:
            href = attrs.get("href", "")
            if href:
                self.current["url"] = urljoin(
                    BASE, href
                )

        if tag == "img":
            if not self.current["imageUrl"]:
                src = (
                    attrs.get("data-src")
                    or attrs.get("src")
                    or ""
                )
                if src:
                    self.current["imageUrl"] = (
                        urljoin(BASE, src)
                    )

            if not self.current["title"]:
                self.current["title"] = (
                    attrs.get("alt", "").strip()
                )

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                if (
                    self.current["url"]
                    and self.current["title"]
                ):
                    self.products.append(
                        self.current
                    )
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
        if (
            tag in ("script", "style")
            and self.skip
        ):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def get_text(html):
    parser = DetailParser()
    parser.feed(html)
    return " ".join(parser.parts)


def get_livers(text):
    match = re.search(
        r"ライバー\s+(.+?)\s+"
        r"(?:続き(?:を)?見る|関連タグ|商品を選択)",
        text,
    )
    if not match:
        return ""
    return match.group(1).strip()


def is_related(name, title, livers):
    if name in title:
        return True

    pattern = (
        rf"(?<![一-龯ぁ-んァ-ン])"
        rf"{re.escape(name)}"
        rf"(?![一-龯ぁ-んァ-ン])"
    )

    return bool(re.search(pattern, livers))


def clean_title(title):
    title = re.sub(
        r"\s+", " ", title
    ).strip()

    if len(title) % 2 == 0:
        half = len(title) // 2
        if title[:half] == title[half:]:
            title = title[:half]

    return title


def extract_dates(text):
    result = {
        "date": "",
        "salesPeriod": "",
        "salesType": "",
        "deliveryDate": "",
    }

    # 商品説明に記載された販売期間を優先
    section = text.split("商品説明", 1)
    description = (
        section[1] if len(section) > 1
        else text
    )

    description = description[:12000]

    # 受注販売期間・販売期間などを探す
    period_labels = [
        "受注販売期間",
        "受注期間",
        "予約受付期間",
        "予約期間",
        "販売期間",
        "再販期間",
        "販売",
    ]

    for label in period_labels:
        for match in re.finditer(
            re.escape(label),
            description,
        ):
            nearby = description[
                match.end():match.end() + 180
            ]

            period = PERIOD_PATTERN.search(
                nearby
            )

            if period:
                start = period.group(1).strip()
                end = period.group(2).strip()

                result["date"] = start
                result["salesPeriod"] = (
                    start + " ～ " + end
                )

                if "受注" in label:
                    result["salesType"] = "受注販売"
                elif "予約" in label:
                    result["salesType"] = "予約販売"
                else:
                    result["salesType"] = "通常販売"

                break

        if result["salesPeriod"]:
            break

    # 販売期間が見つからない場合のみ発売日を確認
    if not result["date"]:
        for label in [
            "発売日",
            "販売開始日",
            "販売開始",
        ]:
            match = re.search(
                re.escape(label)
                + r"\s*[:：]?\s*("
                + DATE_PATTERN
                + r")",
                description,
            )
            if match:
                result["date"] = (
                    match.group(1).strip()
                )
                break

    # 販売形式を確認
    if not result["salesType"]:
        if (
            "受注生産" in description
            or "受注販売" in description
        ):
            result["salesType"] = "受注販売"
        elif "予約販売" in description:
            result["salesType"] = "予約販売"

    # お届け予定・発送予定を確認
    for label in [
        "お届け時期",
        "お届け予定",
        "発送予定時期",
        "発送予定",
        "発送時期",
    ]:
        match = re.search(
            re.escape(label),
            description,
        )

        if not match:
            continue

        nearby = description[
            match.end():match.end() + 100
        ]

        delivery = DELIVERY_PATTERN.search(
            nearby
        )

        if delivery:
            result["deliveryDate"] = (
                delivery.group(1)
            )
            break

    return result


def load_existing(path):
    if not path.exists():
        return []

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
        return data.get(
            "announcements", []
        )
    except Exception:
        return []


def update_person(name, settings):
    print(
        f"\n========== {name} ==========",
        flush=True,
    )

    html = fetch(settings["url"])

    parser = ProductParser()
    parser.feed(html)

    products = parser.products[
        :MAX_PRODUCTS
    ]

    print(
        "取得商品数:",
        len(products),
        flush=True,
    )

    if not products:
        print(
            "取得失敗の可能性があるため更新を中止",
            flush=True,
        )
        return

    path = Path(settings["file"])
    existing = load_existing(path)

    existing_by_url = {
        item.get("url"): item
        for item in existing
        if item.get("url")
    }

    matched = []

    for product in products:
        title = clean_title(
            product["title"]
        )

        try:
            detail_html = fetch(
                product["url"]
            )

            text = get_text(detail_html)
            livers = get_livers(text)

            related = is_related(
                name, title, livers
            )

            print(
                "商品:", title,
                flush=True,
            )
            print(
                "参加ライバー:",
                livers[:180],
                flush=True,
            )
            print(
                "判定:",
                related,
                flush=True,
            )

            if related:
                dates = extract_dates(text)

                old = existing_by_url.get(
                    product["url"], {}
                )

                item = dict(old)

                item.update({
                    "type": old.get(
                        "type", "goods"
                    ),
                    "title": title,
                    "imageUrl": (
                        product["imageUrl"]
                        or old.get(
                            "imageUrl", ""
                        )
                    ),
                    "url": product["url"],
                })

                for key in [
                    "date",
                    "salesPeriod",
                    "salesType",
                    "deliveryDate",
                ]:
                    new_value = dates.get(
                        key, ""
                    )

                    if new_value:
                        item[key] = new_value
                    elif key not in item:
                        item[key] = ""

                matched.append(item)

                print(
                    "発売・開始:",
                    item["date"],
                    flush=True,
                )
                print(
                    "販売期間:",
                    item["salesPeriod"],
                    flush=True,
                )
                print(
                    "販売形式:",
                    item["salesType"],
                    flush=True,
                )
                print(
                    "お届け予定:",
                    item["deliveryDate"],
                    flush=True,
                )

            time.sleep(0.2)

        except Exception as error:
            print(
                "詳細取得エラー:",
                repr(error),
                flush=True,
            )

    print(
        "本人関連商品数:",
        len(matched),
        flush=True,
    )

    if not matched:
        print(
            "一致商品なし。既存データを維持します",
            flush=True,
        )
        return

    merged = matched[:]

    seen = {
        item["url"]
        for item in merged
    }

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

    print(
        "保存先:", path,
        flush=True,
    )
    print(
        "保存件数:",
        len(merged),
        flush=True,
    )


def main():
    for name, settings in PEOPLE.items():
        update_person(
            name, settings
        )


if __name__ == "__main__":
    main()
