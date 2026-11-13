from zendilohub.core.infrastructure.aes_cipher import AesGcmCipher


def test_seals_values_for_their_place_only() -> None:
    cipher = AesGcmCipher(lambda: b'app secret')

    sealed = cipher.seal('sk-live-123', context='tenant-1:shop_key')

    assert b'sk-live-123' not in sealed
    assert sealed != cipher.seal('sk-live-123', context='tenant-1:shop_key')
    assert cipher.open(sealed, context='tenant-1:shop_key') == 'sk-live-123'
    assert cipher.open(sealed, context='tenant-2:shop_key') is None
    assert AesGcmCipher(lambda: b'new secret').open(sealed, context='tenant-1:shop_key') is None
    assert cipher.open(b'\x02' + sealed[1:], context='tenant-1:shop_key') is None
    assert cipher.open(sealed[:20], context='tenant-1:shop_key') is None
