import argparse
import sys
from urllib.parse import urlsplit

from streamlink import Streamlink
from streamlink.exceptions import NoPluginError, StreamlinkError
from streamlink.stream.hls import HLSStream


def capture_hls(url, headless):
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError:
        print("Cài Playwright bằng lệnh: py -m pip install playwright", file=sys.stderr)
        return 1

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True) if headless else playwright.chromium.launch(channel="msedge", headless=False)
            try:
                page = browser.new_page()
                if not headless:
                    print("Trong Edge, bấm nút phát hoặc chọn Link 1, 2, 3 nếu cần.", file=sys.stderr)
                with page.expect_response(
                    lambda response: response.ok and (
                        urlsplit(response.url).path.lower().endswith(".m3u8")
                        or "mpegurl" in response.headers.get("content-type", "").lower()
                    ),
                    timeout=90000,
                ) as playlist:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if headless:
                        for frame in page.frames:
                            play = frame.locator(
                                "button[aria-label*=play i], .jw-icon-playback, "
                                ".vjs-big-play-button, .plyr__control--overlaid, video"
                            ).first
                            try:
                                play.click(timeout=2500)
                            except TimeoutError:
                                continue
                print(playlist.value.url)
                return 0
            finally:
                browser.close()
    except TimeoutError:
        print("Hết thời gian chờ playlist HLS.", file=sys.stderr)
    except Error as exc:
        print(f"Lỗi khi mở trình duyệt hoặc đọc trang: {exc}", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Lấy URL HLS từ trang livestream.")
    parser.add_argument("url", nargs="?")
    parser.add_argument("quality", nargs="?", default="best")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    url = args.url
    if url is None:
        try:
            url = input("Nhập link livestream: ")
        except (EOFError, KeyboardInterrupt):
            print("\nĐã hủy nhập link.", file=sys.stderr)
            return 1

    url = url.strip().replace(r":\/", ":/")
    if not url:
        print("Bạn chưa nhập link livestream.", file=sys.stderr)
        return 1

    if not url.startswith(("http://", "https://")) or not urlsplit(url).hostname:
        print("Hãy nhập URL đầy đủ bắt đầu bằng https:// hoặc http://.", file=sys.stderr)
        return 1

    try:
        streams = Streamlink().streams(url)
    except NoPluginError:
        return capture_hls(url, args.headless)
    except StreamlinkError as exc:
        print(f"Lỗi khi đọc trang: {exc or type(exc).__name__}", file=sys.stderr)
        return 1

    if not streams:
        print("Không tìm thấy luồng. Hãy kiểm tra phòng có đang phát không.", file=sys.stderr)
        return 1

    stream = streams.get(args.quality)
    if not isinstance(stream, HLSStream):
        available = ", ".join(
            name for name, item in streams.items() if isinstance(item, HLSStream)
        )
        print(f"Chất lượng HLS có sẵn: {available or 'không có'}", file=sys.stderr)
        return 1

    print(stream.to_url())
    return 0


if __name__ == "__main__":
    sys.exit(main())
