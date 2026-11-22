"""APP-033 release identity.

Bump APP_VERSION for every distributed EXE candidate. Do not silently reuse a
version string across different deliverables. This is not a hardware approval.
"""

APP_VERSION = "0.6.2-preview.1"
APP_ID = "APP-033"


def version_label() -> str:
    return f"v{APP_VERSION}"


def window_title() -> str:
    return f"黒カット印刷 {version_label()} | {APP_ID}"
