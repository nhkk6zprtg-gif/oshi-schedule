
import re
import html
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE = "https://shop.nijisanji.jp"

SOURCES = {
    "叶": BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100",
    "葛葉": BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009",
}


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.products = []
        self.current = None
        self.depth = 0
        self.capture_name = False
        self.capture_price = False

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

        if tag in ("div", "section", "article"):
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

            title = (
                attrs.get("alt")
                or attrs.get("title")
                or ""
            ).strip()

            if title and not self.current["title"]:
                self.current["title"] = title

        if "card-price" in classes or "text-price" in classes:
            self.capture_price = True

        if any(x in classes for x in [
            "card-name",
            "card-title",
            "card-product-name",
        ]):
            self.capture_name = True

    def handle_data(self, data):
        if self.current is None:
            return

        value = " ".join(data.split())
        if not value:
            return

        if self.capture_price:
            if re.search(r"[\d,]+", value):
                self.current["price"] += value + " "

        if self.capture_name:
            self.current["title"] += value + " "

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag in ("span", "p", "a"):
            self.capture_price = False
            self.capture_name = False

        if tag in ("div", "section", "article"):
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
                self.capture_price = False
                self.capture_name = False


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


def main():
    for name, url in SOURCES.items():
        print("\n==========", name, "==========")

        try:
            page = fetch(url)
            parser = ProductParser()
            parser.feed(page)

            products = parser.products

            print("取得した商品数:", len(products))

            for index, product in enumerate(
                products[:10], start=1
            ):
                print("\n--- 商品", index, "---")
                print("ID:", product["id"])
                print("商品名:", product["title"])
                print("価格:", product["price"])
                print("商品URL:", product["url"])
                print("画像URL:", product["imageUrl"][:200])

            if not products:
                print("商品カードが見つかりませんでした")

        except Exception as error:
            print("取得エラー:", repr(error))


if __name__ == "__main__":
    main()
