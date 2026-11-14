"""S/MIME with `cryptography`: signing, encryption and decryption are its PKCS #7 builders; it has no verification of
signatures, so that is done here on a small BER reader of the CMS structure (RFC 5652, 5.4 and 5.6)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ..domain.models.smime import CertificateInfo, SigningKey, Verification
from ..domain.ports.services import SmimeError

_SIGNED_DATA = '1.2.840.113549.1.7.2'
_ENVELOPED_DATA = '1.2.840.113549.1.7.3'
_MESSAGE_DIGEST = '1.2.840.113549.1.9.4'
_DIGESTS: dict[str, type[hashes.HashAlgorithm]] = {
    '1.3.14.3.2.26': hashes.SHA1,
    '2.16.840.1.101.3.4.2.1': hashes.SHA256,
    '2.16.840.1.101.3.4.2.2': hashes.SHA384,
    '2.16.840.1.101.3.4.2.3': hashes.SHA512,
    '2.16.840.1.101.3.4.2.4': hashes.SHA224,
}
_RSA_WITH: dict[str, type[hashes.HashAlgorithm] | None] = {
    '1.2.840.113549.1.1.1': None,
    '1.2.840.113549.1.1.5': hashes.SHA1,
    '1.2.840.113549.1.1.11': hashes.SHA256,
    '1.2.840.113549.1.1.12': hashes.SHA384,
    '1.2.840.113549.1.1.13': hashes.SHA512,
    '1.2.840.113549.1.1.14': hashes.SHA224,
}
_RSA_PSS = '1.2.840.113549.1.1.10'
_ECDSA_WITH: dict[str, type[hashes.HashAlgorithm] | None] = {
    '1.2.840.10045.2.1': None,
    '1.2.840.10045.4.1': hashes.SHA1,
    '1.2.840.10045.4.3.1': hashes.SHA224,
    '1.2.840.10045.4.3.2': hashes.SHA256,
    '1.2.840.10045.4.3.3': hashes.SHA384,
    '1.2.840.10045.4.3.4': hashes.SHA512,
}
_CHAIN_MAX = 6


# --- A BER reader: enough of X.690 for CMS as mail programs write it (definite and indefinite lengths). ---


@dataclass
class Node:
    tag: int
    """The first identifier octet (class, constructed bit, number up to 30)."""
    number: int
    raw: bytes
    """The whole encoding (identifier, length, content)."""
    value: bytes
    """The content octets (primitive) or the concatenated encodings of the children (constructed)."""
    children: list[Node] = field(default_factory=list)

    @property
    def constructed(self) -> bool:
        return bool(self.tag & 0x20)

    @property
    def context(self) -> bool:
        return self.tag & 0xC0 == 0x80

    def octets(self) -> bytes:
        """An OCTET STRING's content, also when BER cut it into pieces."""
        if not self.constructed:
            return self.value
        return b''.join(child.octets() for child in self.children)


class BerError(ValueError):
    pass


def parse(data: bytes, offset: int = 0) -> tuple[Node, int]:
    if offset + 2 > len(data):
        raise BerError('truncated')
    start, tag = offset, data[offset]
    offset += 1
    number = tag & 0x1F
    if number == 0x1F:
        number = 0
        while True:
            if offset >= len(data):
                raise BerError('truncated')
            byte = data[offset]
            offset += 1
            number = (number << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
    if offset >= len(data):
        raise BerError('truncated')
    length = data[offset]
    offset += 1
    constructed = bool(tag & 0x20)
    if length == 0x80:
        if not constructed:
            raise BerError('indefinite primitive')
        children: list[Node] = []
        while data[offset : offset + 2] != b'\x00\x00':
            child, offset = parse(data, offset)
            children.append(child)
        offset += 2
        content = b''.join(child.raw for child in children)
        return Node(tag, number, data[start:offset], content, children), offset
    if length & 0x80:
        count = length & 0x7F
        if count > 4 or offset + count > len(data):
            raise BerError('length')
        length = int.from_bytes(data[offset : offset + count], 'big')
        offset += count
    end = offset + length
    if end > len(data):
        raise BerError('truncated')
    content = data[offset:end]
    node = Node(tag, number, data[start:end], content)
    if constructed:
        position = 0
        while position < len(content):
            child, position = parse(content, position)
            node.children.append(child)
    return node, end


def oid(node: Node) -> str:
    if node.tag != 0x06 or not node.value:
        raise BerError('not an OID')
    first = node.value[0]
    arcs = [min(first // 40, 2), first - 40 * min(first // 40, 2)]
    value = 0
    for byte in node.value[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(value)
            value = 0
    return '.'.join(str(arc) for arc in arcs)


def _content_info(data: bytes) -> tuple[str, Node | None]:
    root, _ = parse(data)
    if root.tag != 0x30 or not root.children:
        raise BerError('not a ContentInfo')
    kind = oid(root.children[0])
    inner = root.children[1] if len(root.children) > 1 and root.children[1].context else None
    return kind, inner.children[0] if inner and inner.children else None


# --- Certificates ---


def _certificate(pem: str) -> x509.Certificate:
    return x509.load_pem_x509_certificate(pem.encode())


def _fingerprint(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex()


def _emails(certificate: x509.Certificate) -> tuple[str, ...]:
    found: list[str] = []
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        found += names.get_values_for_type(x509.RFC822Name)
    except x509.ExtensionNotFound:
        pass
    found += [str(each.value) for each in certificate.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)]
    return tuple(dict.fromkeys(address.strip().lower() for address in found if '@' in address))


def _is_ca(certificate: x509.Certificate) -> bool:
    try:
        return certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _for_email(certificate: x509.Certificate) -> bool:
    try:
        usages = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound:
        return True
    return ExtendedKeyUsageOID.EMAIL_PROTECTION in usages or ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE in usages


def info_of(certificate: x509.Certificate) -> CertificateInfo:
    return CertificateInfo(
        fingerprint=_fingerprint(certificate),
        subject=certificate.subject.rfc4514_string()[:500],
        issuer=certificate.issuer.rfc4514_string()[:500],
        serial=format(certificate.serial_number, 'x'),
        emails=_emails(certificate),
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
        pem=certificate.public_bytes(serialization.Encoding.PEM).decode(),
        is_ca=_is_ca(certificate),
    )


def _load_certificate(data: bytes) -> x509.Certificate:
    try:
        if b'-----BEGIN' in data:
            return x509.load_pem_x509_certificate(data)
        return x509.load_der_x509_certificate(data)
    except ValueError:
        raise SmimeError('certificate') from None


def _public(key: object) -> bytes:
    if not isinstance(key, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey)):
        raise SmimeError('key_type')
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _private_pem(key: object) -> str:
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise SmimeError('key_type')
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def _private_key(pem: str) -> rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise SmimeError('key_type')
    return key


# --- Signatures ---


def _signer_certificate(sid: Node, pool: Sequence[x509.Certificate]) -> x509.Certificate | None:
    if sid.tag == 0x30 and len(sid.children) == 2:
        issuer, serial = sid.children
        number = int.from_bytes(serial.value, 'big', signed=True)
        for certificate in pool:
            if certificate.serial_number == number and certificate.issuer.public_bytes() == issuer.raw:
                return certificate
        matching = [each for each in pool if each.serial_number == number]
        return matching[0] if len(matching) == 1 else None
    if sid.context and sid.number == 0:
        for certificate in pool:
            try:
                key_id = certificate.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
            except x509.ExtensionNotFound:
                continue
            if key_id == sid.value:
                return certificate
    return None


def _check_signature(
    certificate: x509.Certificate, algorithm: Node, digest: type[hashes.HashAlgorithm], signature: bytes, data: bytes
) -> bool:
    key = certificate.public_key()
    name = oid(algorithm.children[0])
    try:
        if isinstance(key, rsa.RSAPublicKey) and name in _RSA_WITH:
            key.verify(signature, data, padding.PKCS1v15(), (_RSA_WITH[name] or digest)())
            return True
        if isinstance(key, rsa.RSAPublicKey) and name == _RSA_PSS:
            pss_hash, mgf_hash, salt = _pss(algorithm)
            key.verify(signature, data, padding.PSS(padding.MGF1(mgf_hash()), salt), pss_hash())
            return True
        if isinstance(key, ec.EllipticCurvePublicKey) and name in _ECDSA_WITH:
            key.verify(signature, data, ec.ECDSA((_ECDSA_WITH[name] or digest)()))
            return True
    except InvalidSignature, ValueError, UnsupportedAlgorithm:
        return False
    return False


def _pss(algorithm: Node) -> tuple[type[hashes.HashAlgorithm], type[hashes.HashAlgorithm], int]:
    """RSASSA-PSS parameters (RFC 4055): hash, MGF1 hash and salt length; SHA-1 and 20 if left out."""
    hash_: type[hashes.HashAlgorithm] = hashes.SHA1
    mgf: type[hashes.HashAlgorithm] = hashes.SHA1
    salt = 20
    params = algorithm.children[1] if len(algorithm.children) > 1 else None
    for item in params.children if params is not None and params.tag == 0x30 else []:
        inner = item.children[0] if item.children else None
        if inner is None:
            continue
        if item.number == 0:
            hash_ = _DIGESTS.get(oid(inner.children[0]), hashes.SHA1)
        elif item.number == 1 and len(inner.children) > 1:
            mgf = _DIGESTS.get(oid(inner.children[1].children[0]), hashes.SHA1)
        elif item.number == 2:
            salt = int.from_bytes(inner.value, 'big')
    return hash_, mgf, salt


def _issued(child: x509.Certificate, parent: x509.Certificate) -> bool:
    try:
        child.verify_directly_issued_by(parent)
    except ValueError, TypeError, InvalidSignature, UnsupportedAlgorithm:
        return False
    return True


def _chain_trusted(
    signer: x509.Certificate, pool: Sequence[x509.Certificate], trusted: set[str], now: datetime
) -> bool:
    current, seen = signer, {_fingerprint(signer)}
    for _ in range(_CHAIN_MAX):
        if _fingerprint(current) in trusted:
            return True
        issuer = next(
            (each for each in pool if each.subject == current.issuer and _issued(current, each)),
            None,
        )
        if issuer is None or _fingerprint(issuer) in seen:
            return False
        if not issuer.not_valid_before_utc <= now <= issuer.not_valid_after_utc or not _is_ca(issuer):
            # A trusted certificate the organization added itself (no CA) counts only as itself.
            return False
        seen.add(_fingerprint(issuer))
        current = issuer
    return False


class CryptographySmime:
    def read_certificate(self, data: bytes) -> CertificateInfo:
        return info_of(_load_certificate(data))

    def read_pkcs12(self, data: bytes, password: str) -> tuple[CertificateInfo, str]:
        try:
            key, certificate, _ = pkcs12.load_key_and_certificates(data, password.encode() or None)
        except ValueError, TypeError, UnsupportedAlgorithm:
            raise SmimeError('pkcs12') from None
        if key is None or certificate is None:
            raise SmimeError('pkcs12')
        return info_of(certificate), _private_pem(key)

    def read_key(self, data: bytes, password: str, certificate: CertificateInfo) -> str:
        secret = password.encode() or None
        try:
            if b'-----BEGIN' in data:
                key = serialization.load_pem_private_key(data, password=secret)
            else:
                key = serialization.load_der_private_key(data, password=secret)
        except ValueError, TypeError, UnsupportedAlgorithm:
            raise SmimeError('key') from None
        pem = _private_pem(key)
        if _public(_private_key(pem).public_key()) != _public(_certificate(certificate.pem).public_key()):
            raise SmimeError('key_mismatch')
        return pem

    def sign(self, content: bytes, key: SigningKey) -> bytes:
        options = [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary]
        return (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(content)
            .add_signer(_certificate(key.certificate), _private_key(key.private_key), hashes.SHA256())
            .sign(serialization.Encoding.DER, options)
        )

    def encrypt(self, content: bytes, recipients: Sequence[str]) -> bytes:
        builder = pkcs7.PKCS7EnvelopeBuilder().set_data(content)
        try:
            for pem in dict.fromkeys(recipients):
                builder = builder.add_recipient(_certificate(pem))
            return builder.set_content_encryption_algorithm(algorithms.AES256).encrypt(
                serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]
            )
        except TypeError, ValueError, UnsupportedAlgorithm:
            raise SmimeError('recipient_key') from None

    def kind(self, data: bytes) -> Literal['enveloped', 'signed'] | None:
        try:
            content_type, _ = _content_info(data)
        except BerError:
            return None
        return {_ENVELOPED_DATA: 'enveloped', _SIGNED_DATA: 'signed'}.get(content_type)  # type: ignore[return-value]

    def decrypt(self, data: bytes, key: SigningKey) -> bytes | None:
        try:
            private_key = _private_key(key.private_key)
            if not isinstance(private_key, rsa.RSAPrivateKey):
                return None
            return pkcs7.pkcs7_decrypt_der(data, _certificate(key.certificate), private_key, [])
        except ValueError, TypeError, UnsupportedAlgorithm:
            return None

    def verify(self, data: bytes, content: bytes | None, trusted: Sequence[str], now: datetime) -> Verification:
        broken = Verification(intact=False, signer=None, trusted=False)
        try:
            content_type, signed = _content_info(data)
            if content_type != _SIGNED_DATA or signed is None or signed.tag != 0x30:
                return broken
            return self._verify(signed, content, trusted, now)
        except BerError, IndexError, ValueError:
            return broken

    def _verify(self, signed: Node, content: bytes | None, trusted: Sequence[str], now: datetime) -> Verification:
        parts = signed.children
        encapsulated = parts[2]
        if content is None:
            wrapper = next((each for each in encapsulated.children[1:] if each.context and each.number == 0), None)
            content = wrapper.children[0].octets() if wrapper is not None and wrapper.children else b''
            inside = content
        else:
            inside = None
        included: list[x509.Certificate] = []
        for item in parts[3:]:
            if item.context and item.number == 0:
                for each in item.children:
                    try:
                        included.append(x509.load_der_x509_certificate(each.raw))
                    except ValueError:
                        continue
        anchors = [_certificate(pem) for pem in trusted]
        signer_infos = parts[-1]
        if signer_infos.tag != 0x31 or not signer_infos.children:
            return Verification(intact=False, signer=None, trusted=False, content=inside)
        signer_info = signer_infos.children[0].children
        certificate = _signer_certificate(signer_info[1], [*included, *anchors])
        digest = _DIGESTS.get(oid(signer_info[2].children[0]))
        if certificate is None or digest is None:
            return Verification(intact=False, signer=None, trusted=False, content=inside)
        position = 3
        attributes = signer_info[3] if signer_info[3].context and signer_info[3].number == 0 else None
        if attributes is not None:
            position += 1
        algorithm, signature = signer_info[position], signer_info[position + 1].octets()
        hasher = hashes.Hash(digest())
        hasher.update(content)
        hashed = hasher.finalize()
        if attributes is not None:
            digests = [
                attribute.children[1].children[0].octets()
                for attribute in attributes.children
                if oid(attribute.children[0]) == _MESSAGE_DIGEST and attribute.children[1].children
            ]
            # The attributes are signed in their DER SET OF form, not with the [0] tag they carry here.
            data = b'\x31' + attributes.raw[1:]
            intact = digests == [hashed] and _check_signature(certificate, algorithm, digest, signature, data)
        else:
            intact = _check_signature(certificate, algorithm, digest, signature, content)
        pool = [*included, *anchors]
        anchored = _chain_trusted(certificate, pool, {_fingerprint(each) for each in anchors}, now)
        return Verification(
            intact=intact,
            signer=info_of(certificate),
            trusted=anchored and _for_email(certificate),
            content=inside,
        )
