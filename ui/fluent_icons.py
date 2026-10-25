from qfluentwidgets import FluentIcon as FIF


# Map app route keys / logical names → FluentIcon
_ICON_MAP = {
    "HOME": FIF.HOME,
    "dashboard": FIF.HOME,
    "PEOPLE": FIF.PEOPLE,
    "contacts": FIF.PEOPLE,
    "officials": FIF.PEOPLE,
    "org_chart": FIF.UNIT,
    "UNIT": FIF.UNIT,
    "groups": FIF.PEOPLE,
    "users": FIF.PEOPLE,
    "user_management": FIF.PEOPLE,
    "GLOBE": FIF.GLOBE,
    "CALENDAR": FIF.CALENDAR,
    "calendar": FIF.CALENDAR,
    "CHAT": FIF.CHAT,
    "sms": FIF.CHAT,
    "MESSAGE": FIF.MESSAGE,
    "FOLDER": FIF.FOLDER,
    "files": FIF.FOLDER,
    "EDIT": FIF.EDIT,
    "notes": FIF.EDIT,
    "CHECKBOX": FIF.COMPLETED if hasattr(FIF, "COMPLETED") else FIF.ACCEPT,
    "tasks": FIF.COMPLETED if hasattr(FIF, "COMPLETED") else FIF.ACCEPT,
    "DOCUMENT": FIF.DOCUMENT,
    "reports": FIF.DOCUMENT,
    "SETTING": FIF.SETTING,
    "settings": FIF.SETTING,
    "RETURN": FIF.RETURN,
    "CLOSE": FIF.CLOSE,
    "SEARCH": FIF.SEARCH,
    "ADD": FIF.ADD,
    "DELETE": FIF.DELETE,
    "SAVE": FIF.SAVE,
    "SYNC": FIF.SYNC,
    "INFO": FIF.INFO,
    "MAIL": FIF.MAIL,
    "PHONE": FIF.PHONE,
    "LIBRARY": FIF.LIBRARY,
    "MARKET": FIF.MARKET,
}


def fluent_icon(name: str, fallback: str = "HOME"):
    """Resolve FluentIcon by name (case-insensitive logical key or FIF attribute)."""
    if not name:
        name = fallback
    key = str(name).strip()
    if key in _ICON_MAP:
        return _ICON_MAP[key]
    upper = key.upper()
    if upper in _ICON_MAP:
        return _ICON_MAP[upper]
    return getattr(FIF, upper, getattr(FIF, fallback.upper(), FIF.HOME))
