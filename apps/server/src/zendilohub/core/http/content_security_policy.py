import base64
import hashlib
import re

_INLINE_SCRIPT = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>')


def content_security_policy(index_html: str) -> str:
    """
    A strict policy for the web app: only same-origin resources, plus the inline
    scripts of index.html, allowed by hash (computed from the actual build).
    """
    hashes = [
        f"'sha256-{base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()}'"
        for script in _INLINE_SCRIPT.findall(index_html)
    ]
    return '; '.join(
        [
            "default-src 'self'",
            ' '.join(["script-src 'self'", *hashes]),
            # Vue sets style attributes at runtime.
            "style-src 'self' 'unsafe-inline'",
            # Previews of selected files are blob: URLs.
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )
