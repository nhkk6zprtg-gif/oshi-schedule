
import re
import urllib.request
from html.parser import HTMLParser

BASE = "https://shop.nijisanji.jp"

# 公式ストアの商品一覧から確認済みの商品
SEARCH_URLS = {
    "叶": BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100",
    "葛葉": BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009",
}

KEYWORDS = [
    "発売日",
    "販売開始",
    "販売期間",
    "販売終了",
    "受注",
    "予約",
    "受付期間",
    "発送",
    "お届け",
    "出荷",
]

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
                    "title": "",
                    "url": "",
                }
                self.depth = 1
            return

        if tag == "div":
            self.depth += 1

        if tag == "a" and not self.current["url"]:
            href = attrs.get("href", "")
            if href:
                self.current["url"] = (
                    BASE + href
                    if href.startswith("/")
                    else href
                )

        if tag == "img" and not self.current["title"]:
            self.current["title"] = (
                attrs.get("alt", "").strip()
            )

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                if self.current["url"]:
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


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )
    with urllib.request.urlopen(
        request, timeout=30
    ) as response:
        return response.read().decode(
            "utf-8", errors="replace"
        )


def inspect_product(url):
    html = fetch(url)
    parser = TextParser()
    parser.feed(html)

    text = " ".join(parser.parts)

    found = []

    for keyword in KEYWORDS:
        for match in list(
            re.finditer(re.escape(keyword), text)
        )[:3]:
            start = max(0, match.start() - 65)
            end = min(len(text), match.end() + 160)

            snippet = text[start:end]
            found.append((keyword, snippet))

    return found


def main():
    for name, search_url in SEARCH_URLS.items():
        print(
            "\n==========", name, "==========",
            flush=True,
        )

        html = fetch(search_url)
        parser = ProductParser()
        parser.feed(html)

        # 各カテゴリの先頭3商品を調査
        products = parser.products[:3]

        print("調査商品数:", len(products), flush=True)

        for product in products:
            print(
                "\n商品:",
                product["title"],
                flush=True,
            )
            print(
                "URL:",
                product["url"],
                flush=True,
            )

            try:
                results = inspect_product(product["url"])

                if not results:
                    print(
                        "日付・受注関連の記載なし",
                        flush=True,
                    )

                for keyword, snippet in results:
                    print(
                        "項目:", keyword,
                        flush=True,
                    )
                    print(
                        "記載:", snippet,
                        flush=True,
                    )

            except Exception as error:
                print(
                    "取得エラー:",
                    repr(error),
                    flush=True,
                )


if __name__ == "__main__":
    main()
