
import urllib.request
from html.parser import HTMLParser

SOURCES = {
    "叶": "https://shop.nijisanji.jp/searchAjax?cgid=1019&secondCgid=M01",
    "葛葉": "https://shop.nijisanji.jp/searchAjax?cgid=1042&secondCgid=M01",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.text.append(value)


for name, url in SOURCES.items():
    print(f"\n=== {name} ===")

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request, timeout=25
        ) as response:
            html = response.read().decode(
                "utf-8", errors="replace"
            )

        parser = PageParser()
        parser.feed(html)

        print("取得成功")
        print("HTML文字数:", len(html))
        print("抽出テキスト例:")
        for line in parser.text[:30]:
            print(line)

    except Exception as error:
        print("取得失敗:", error)
