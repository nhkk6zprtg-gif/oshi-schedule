
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin

BASE = "https://shop.nijisanji.jp"

SEARCHES = {
    "叶": [
        BASE + "/search?" + urlencode({"q": "叶"}),
        BASE + "/searchAjax?" + urlencode({"q": "叶"}),
    ],
    "葛葉": [
        BASE + "/search?" + urlencode({"q": "葛葉"}),
        BASE + "/searchAjax?" + urlencode({"q": "葛葉"}),
    ],
}


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

        if tag == "img":
            if not self.current["imageUrl"]:
                src = (
                    attrs.get("data-src")
                    or attrs.get("src")
                    or ""
                )
                if src:
                    self.current["imageUrl"] = urljoin(
                        BASE, src
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
                self.products.append(self.current)
                self.current = None


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


def clean_title(title):
    title = " ".join(title.split())

    # 同じ商品名が連続している場合は整理する
    words = title.split(" ")
    half = len(words) // 2

    if (
        len(words) % 2 == 0
        and words[:half] == words[half:]
    ):
        title = " ".join(words[:half])

    return title


def main():
    for name, urls in SEARCHES.items():
        print("\n==========", name, "==========")

        for url in urls:
            print("\n検索URL:", url)

            try:
                page = fetch(url)
                parser = ProductParser()
                parser.feed(page)

                print("HTML文字数:", len(page))
                print(
                    "取得した商品数:",
                    len(parser.products)
                )

                matched = [
                    p for p in parser.products
                    if name in p["title"]
                ]

                print(
                    "本人名を含む商品数:",
                    len(matched)
                )

                for product in matched[:8]:
                    print(
                        "商品:",
                        clean_title(product["title"])
                    )
                    print("ID:", product["id"])
                    print("URL:", product["url"])
                    print(
                        "画像:",
                        product["imageUrl"][:150]
                    )

                if not matched:
                    print("検索結果の先頭3件:")
                    for product in parser.products[:3]:
                        print(
                            product["id"],
                            clean_title(product["title"])
                        )

            except Exception as error:
                print(
                    "検索エラー:",
                    repr(error)
                )


if __name__ == "__main__":
    main()
