from collections import deque

_announcements = deque()


def add(response):
    _announcements.append(response)


def get_all():
    items = list(_announcements)
    _announcements.clear()
    return items