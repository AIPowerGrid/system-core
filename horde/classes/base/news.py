# SPDX-FileCopyrightText: 2022 Konstantinos Thoukydidis <mail@dbzer0.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime

from loguru import logger


class News:
    def __init__(self):
        import json
        import os

        # The news.json file is located at ../../data/news.json
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "news.json"))

        if os.path.exists(path):
            with open(path) as file:
                try:
                    self.HORDE_NEWS = json.load(file)
                except json.JSONDecodeError:
                    self.HORDE_NEWS = []
                    logger.error(f"File {path} is not a valid JSON file. No news will be available.")
                except Exception as e:
                    self.HORDE_NEWS = []
                    logger.exception(f"An error occurred while reading the news file: {e}")
        else:
            self.HORDE_NEWS = []
            logger.error(f"File {path} not found. No news will be available.")

    def get_news(self):
        """extensible function from gathering nodes from extensing classes"""
        return self.HORDE_NEWS

    def sort_news(self, raw_news):
        # unsorted_news = []
        # for piece in raw_news:
        #     piece_dict = {
        #         "date": datetime.strptime(piece["piece"], '%y-%m-%d'),
        #         "piece": piece["news"],
        #     }
        #     unsorted_news.append(piece_dict)
        sorted_news = sorted(
            raw_news,
            key=lambda p: datetime.strptime(p["date_published"], "%Y-%m-%d"),
            reverse=True,
        )
        return sorted_news

    def sorted_news(self):
        return self.sort_news(self.get_news())
