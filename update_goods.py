
import re
import html
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE_URL = "https://shop.nijisanji.jp"

SOURCES = {
    "叶": (
        "https://shop.nijisanji.jp/"
        "searchAjax?cgid=1019&secondCgid=M01"
    ),
    "葛葉": (
        "https://shop.nijisanji.jp/"
        "searchAjax?cgid=1042&secondCgid=M01"
    ),
}


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = []
        self.prices = []
        self.current_link = None
        self.link_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")
            if href:
                self.current_link = href
                self.link_text = []

        if tag == "img":
            src = (
                attrs.get("data-src")
                or attrs.get("src")
                or ""
            )
            alt = attrs.get("alt", "")

            if src:
                self.images.append({
                    "alt": alt.strip(),
                    "url": urljoin(BASE_URL, src),
                })

    def handle_data(self, data):
        text = " ".join(data.split())

        if not text:
            return

        if self.current_link is not None:
            self.link_text.append(text)

        if re.search(
            r"(?:¥|￥|円)\s*[\d,]+",
            text
        ):
            self.prices.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link:
            title = " ".join(self.link_text).strip()

            if title:
                self.links.append({
                    "title": title,
                    "url": urljoin(
                        BASE_URL,
                        self.current_link
                    ),
                })

            self.current_link = None
            self.link_text = []


def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(iPhone; CPU iPhone OS 17_0 "
                "like Mac OS X) "
                "AppleWebKit/605.1.15 "
                "Version/17.0 Mobile Safari/604.1"
            ),
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


def main():
    for name, url in SOURCES.items():
        print(f"\n========== {name} ==========")

        try:
            page = fetch_page(url)
            parser = ProductParser()
            parser.feed(page)

            print("HTML文字数:", len(page))
            print("リンク数:", len(parser.links))
            print("画像数:", len(parser.images))
            print("価格候補数:", len(parser.prices))

            print("\n--- 商品リンク候補 ---")

            candidates = [
                item
                for item in parser.links
                if (
                    "/products/" in item["url"]
                    or "/product/" in item["url"]
                    or "Product-Show" in item["url"]
                )
            ]

            for item in candidates[:10]:
                print(
                    item["title"][:100],
                    "=>",
                    item["url"]
                )

            print(
                "商品リンク候補数:",
                len(candidates)
            )

            print("\n--- 画像候補 ---")

            for item in parser.images[:10]:
                print(
                    item["alt"][:80],
                    "=>",
                    item["url"][:200]
                )

            print("\n--- 価格候補 ---")

            for price in parser.prices[:10]:
                print(price[:150])

            print("\n--- HTML内の識別子 ---")

            for keyword in [
                "product-tile",
                "product-name",
                "product-price",
                "productId",
                "search-result",
                "product-grid",
            ]:
                count = page.lower().count(
                    keyword.lower()
                )
                print(keyword, ":", count)

        except Exception as error:
            print(
                "取得エラー:",
                type(error).__name__,
                str(error)
            )


if __name__ == "__main__":
    main()
