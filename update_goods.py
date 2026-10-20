
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE = "https://shop.nijisanji.jp"

PEOPLE = {
    "叶": (
        BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100"
    ),
    "葛葉": (
        BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009"
    ),
}


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
                self.current["url"] = urljoin(BASE, href)

        if tag == "img" and not self.current["title"]:
            self.current["title"] = attrs.get(
                "alt", ""
            ).strip()

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
        self.text = []
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
                self.text.append(value)


def inspect_detail(html, name):
    parser = TextParser()
    parser.feed(html)

    text = " ".join(parser.text)

    # 「ライバー」の文字がある位置を調べる
    positions = [
        m.start()
        for m in re.finditer("ライバー", text)
    ]

    evidence = []

    for position in positions:
        snippet = text[
            position:position + 250
        ]

        # 参加者名が現れる箇所を記録
        if name in snippet:
            evidence.append(snippet[:180])

    return evidence


def main():
    for name, url in PEOPLE.items():
        print(
            "\n==========", name, "==========",
            flush=True,
        )

        page = fetch(url)
        parser = ProductParser()
        parser.feed(page)

        products = parser.products[:12]

        print(
            "取得した商品数:",
            len(products),
            flush=True,
        )

        for product in products:
            title = product["title"]
            url = product["url"]

            print("\n商品:", title, flush=True)

            try:
                detail = fetch(url)
                evidence = inspect_detail(detail, name)

                print(
                    "名前を含むライバー欄候補:",
                    len(evidence),
                    flush=True,
                )

                for item in evidence[:2]:
                    print(
                        "確認箇所:",
                        item,
                        flush=True,
                    )

            except Exception as error:
                print(
                    "詳細取得エラー:",
                    repr(error),
                    flush=True,
                )


if __name__ == "__main__":
    main()
