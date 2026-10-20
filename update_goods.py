
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE = "https://shop.nijisanji.jp"

SOURCES = {
    "叶": BASE + "/searchAjax?cgid=1019&secondCgid=M01-04-0100",
    "葛葉": BASE + "/searchAjax?cgid=1042&secondCgid=M01-04-0009",
}


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.blocks = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag == "a":
            self.current = {
                "href": a.get("href", ""),
                "class": a.get("class", ""),
                "text": [],
            }

        cls = a.get("class", "")
        if any(x in cls.lower() for x in [
            "product", "tile", "search-result",
            "price", "grid"
        ]):
            self.blocks.append((tag, cls[:160]))

    def handle_data(self, data):
        if self.current is not None:
            value = " ".join(data.split())
            if value:
                self.current["text"].append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            item = self.current
            item["text"] = " ".join(item["text"])[:100]
            self.links.append(item)
            self.current = None


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main():
    for name, url in SOURCES.items():
        print("\n==========", name, "==========")
        print("URL:", url)

        try:
            page = fetch(url)
            parser = Inspector()
            parser.feed(page)

            print("HTML文字数:", len(page))
            print("リンク数:", len(parser.links))

            print("\n--- 商品関連HTMLクラス ---")
            for tag, cls in list(dict.fromkeys(
                parser.blocks
            ))[:20]:
                print(tag, cls)

            print("\n--- 商品らしいリンク ---")
            matches = []
            for item in parser.links:
                href = item["href"]
                cls = item["class"]
                if any(x in (href + cls).lower() for x in [
                    "product", "item", "detail",
                    "pid", "sku", "tile"
                ]):
                    matches.append(item)

            print("候補数:", len(matches))
            for item in matches[:12]:
                print("TEXT:", item["text"])
                print("HREF:", item["href"][:220])
                print("CLASS:", item["class"][:120])

            print("\n--- HTML内のキーワード ---")
            for keyword in [
                "product-tile",
                "product-name",
                "product-price",
                "product-id",
                "data-pid",
                "search-result",
                "product-grid",
                "product-list",
                "¥",
                "税込",
                "商品一覧",
            ]:
                print(
                    keyword,
                    page.lower().count(keyword.lower())
                )

            print("\n--- 商品表示部分のHTML抜粋 ---")
            for keyword in [
                "product-tile",
                "product-name",
                "data-pid",
                "商品一覧",
            ]:
                pos = page.lower().find(keyword.lower())
                if pos >= 0:
                    start = max(0, pos - 200)
                    end = min(len(page), pos + 500)
                    snippet = re.sub(
                        r"\s+", " ", page[start:end]
                    )
                    print(keyword, ":", snippet[:700])

            print("\n--- 検出されたURL形式 ---")
            urls = re.findall(
                r'''(?:href|data-url)=["']([^"']+)''',
                page,
                re.I,
            )
            seen = set()
            count = 0

            for path in urls:
                full = urljoin(BASE, path)
                if full in seen:
                    continue
                seen.add(full)
                if any(x in full.lower() for x in [
                    "search", "product", "item"
                ]):
                    print(full[:220])
                    count += 1
                    if count >= 15:
                        break

        except Exception as error:
            print("ERROR:", repr(error))


if __name__ == "__main__":
    main()
