"""YouTube 명령 — 웹브라우저로 검색/play"""
import webbrowser
import urllib.parse
import logging
from commands.base_command import BaseCommand
from i18n.translator import _


class YoutubeCommand(BaseCommand):
    def __init__(self, tts_func):
        self.tts_wrapper = tts_func

    def matches(self, text: str) -> bool:
        return "YouTube" in text

    # 검색어가 아닌 동사/조사 표현
    _ACTION_WORDS = [
        "열어줘", "열어 줘", "켜줘", "켜 줘", "틀어줘", "틀어 줘",
        "play해줘", "play해 줘", "보여줘", "보여 줘", "찾아줘", "찾아 줘",
        "열어", "켜", "틀어", "play", "검색", "열기", "해줘", "줘",
    ]

    def execute(self, text: str) -> None:
        query = text.replace("YouTube", "").strip()

        # 동사/조사 제거
        for word in self._ACTION_WORDS:
            query = query.replace(word, "")
        query = query.strip()

        if query:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
            self.tts_wrapper(_("{query} YouTube에서 검색할게요.").format(query=query))
        else:
            url = "https://www.youtube.com"
            self.tts_wrapper(_("YouTube를 열게요."))

        logging.info(f"YouTube 열기: {url}")
        webbrowser.open(url)
