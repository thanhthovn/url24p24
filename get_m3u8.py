import argparse
import sys
from time import monotonic
from urllib.parse import urlsplit

from streamlink import Streamlink
from streamlink.exceptions import NoPluginError, StreamlinkError
from streamlink.stream.hls import HLSStream


PLAY_BUTTON = (
    "button[aria-label='play' i], button[aria-label^='phát' i], "
    "button[title='play' i], .jw-state-idle .jw-icon-display, "
    ".vjs-big-play-button, .plyr__control--overlaid"
)


def wait_for_playlist(page, url, headless, browser_error):
    playlist_url = None
    playlist_statuses = set()

    def inspect_response(response):
        nonlocal playlist_url
        path = urlsplit(response.url).path.lower()
        mime = response.headers.get("content-type", "").lower()
        if path.endswith(".m3u8") or "mpegurl" in mime:
            playlist_statuses.add(response.status)
            if response.ok and playlist_url is None:
                playlist_url = response.url

    page.on("response", inspect_response)
    navigation = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    deadline = monotonic() + 90
    clicked_frames = set()
    video_count = 0

    while playlist_url is None and monotonic() < deadline:
        if headless:
            for frame in page.frames:
                if playlist_url is not None or monotonic() >= deadline:
                    break
                try:
                    if frame not in clicked_frames:
                        buttons = frame.locator(PLAY_BUTTON).filter(visible=True)
                        if buttons.count():
                            buttons.first.click(timeout=750)
                            clicked_frames.add(frame)
                    video_count = max(video_count, frame.locator("video").evaluate_all(
                        """videos => {
                            for (const video of videos) {
                                if (video.paused) {
                                    video.muted = true;
                                    video.play().catch(() => {});
                                }
                            }
                            return videos.length;
                        }"""
                    ))
                except browser_error:
                    # An embedded player may replace its frame during startup.
                    continue
        if playlist_url is None:
            page.wait_for_timeout(500)

    if playlist_url is None:
        page_status = navigation.status if navigation else "không có"
        hls_status = ", ".join(map(str, sorted(playlist_statuses))) or "không quan sát được"
        print(
            f"Hết thời gian chờ playlist HLS. HTTP trang: {page_status}. "
            f"HTTP playlist: {hls_status}. Số nút phát đã bấm: {len(clicked_frames)}. "
            f"Số video tối đa trong một khung: {video_count}.",
            file=sys.stderr,
        )
    return playlist_url


def capture_hls(url, headless):
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        print("Cài Playwright bằng lệnh: py -m pip install playwright", file=sys.stderr)
        return 1

    try:
        with sync_playwright() as playwright:
            channel = "chromium" if headless else "msedge"
            browser = playwright.chromium.launch(channel=channel, headless=headless)
            try:
                page = browser.new_page()
                if not headless:
                    print("Trong Edge, bấm nút phát hoặc chọn Link 1, 2, 3 nếu cần.", file=sys.stderr)
                playlist_url = wait_for_playlist(page, url, headless, Error)
                if playlist_url is None:
                    return 1
                print(playlist_url)
                return 0
            finally:
                browser.close()
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
