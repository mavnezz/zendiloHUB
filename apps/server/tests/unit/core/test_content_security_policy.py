import base64
import hashlib

from zendilohub.core.http.content_security_policy import content_security_policy


def test_allows_the_inline_scripts_of_index_html_by_hash() -> None:
    inline = "document.documentElement.classList.add('dark')"
    html = f'<html><head><script>{inline}</script><script type="module" src="/assets/app.js"></script></head></html>'
    digest = base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()

    policy = content_security_policy(html)

    assert f"script-src 'self' 'sha256-{digest}'" in policy
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy


def test_allows_only_own_scripts_without_inline_ones() -> None:
    assert "script-src 'self';" in content_security_policy('<html></html>')
