"""Tiny Telegram sender. Prints to the console when no token is set."""

import requests


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def send(self, text: str):
        if not text:
            return
        if not self.enabled:
            print("\n[telegram off]\n" + text)
            return
        for start in range(0, len(text), 4000):  # Telegram limit 4096
            try:
                requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    data={"chat_id": self.chat_id, "text": text[start:start + 4000],
                          "parse_mode": "HTML", "disable_web_page_preview": "true"},
                    timeout=20,
                )
            except requests.RequestException as e:
                print(f"Telegram send failed: {type(e).__name__}")
