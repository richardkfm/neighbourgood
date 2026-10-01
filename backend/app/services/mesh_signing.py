"""Signatures on BLE mesh messages.

Every browser holds a non-extractable ECDSA P-256 key pair and registers the
public key (per user and device) while online. Outgoing mesh messages carry
``author_user_id``, ``key_id`` and ``sig``; the server verifies ``sig`` with the
author's registered key and then attributes the content to the author rather
than to whoever relayed and synced it.

Signing format v1 — implemented identically in
``frontend/src/lib/bluetooth/signing.ts`` (shared test vector in
``backend/tests/test_mesh_signing.py`` and ``frontend/tests/mesh-signing.test.mjs``):

    signing input = UTF-8( "NG-MESH-SIG-V1\\n" + canonical_json({
        "author_user_id": int, "community_id": int, "data": object,
        "id": str, "ts": int, "type": str }) )
    signature     = ECDSA P-256 / SHA-256, IEEE P1363 (r || s, 64 bytes), base64url without padding
    key_id        = base64url-without-padding( SHA-256( SubjectPublicKeyInfo DER ) ) (43 chars)

canonical_json:
    null / true / false  -> ``null`` / ``true`` / ``false``
    string               -> ``"`` + escaped + ``"``; escape ``"`` and ``\\`` with a
                            backslash, U+0008/0009/000A/000C/000D as ``\\b \\t \\n \\f \\r``,
                            other U+0000..U+001F as ``\\u00xx`` (lowercase hex), all other
                            characters literally. Lone surrogates are invalid.
    number               -> must be finite. Integral values must lie within
                            ±(2^53 − 1) and are written as plain decimal integers
                            (``-0`` → ``0``). Other values use the ECMAScript
                            Number::toString format (shortest round-trip digits;
                            exponent form ``1e-7`` / ``1.5e+25`` outside 1e-6 ≤ |x| < 1e21).
    array                -> ``[`` + elements joined by ``,`` + ``]``
    object               -> keys sorted by their UTF-8 bytes (= code point order),
                            ``{`` + ``"key":value`` joined by ``,`` + ``}``
    No whitespace anywhere; nesting deeper than 32 levels is invalid.
"""

import base64
import hashlib
import json
import math

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

SIGNING_PREFIX = "NG-MESH-SIG-V1\n"
MAX_SAFE_INTEGER = 2**53 - 1
MAX_DEPTH = 32
# Proof of possession signed when registering a key, bound to the account
REGISTRATION_PREFIX = "NG-MESH-KEY-V1\n"


class CanonicalizationError(ValueError):
    pass


def _es_number(value: float) -> str:
    """Format a finite, non-integral float like ECMAScript Number::toString."""
    sign = "-" if value < 0 else ""
    mantissa, _, exp_part = repr(abs(value)).partition("e")
    int_part, _, frac_part = mantissa.partition(".")
    digits = int_part + frac_part
    n = len(int_part) + (int(exp_part) if exp_part else 0)
    stripped = digits.lstrip("0")
    n -= len(digits) - len(stripped)
    digits = stripped.rstrip("0") or "0"
    k = len(digits)
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        exp = ("+" if e >= 0 else "-") + str(abs(e))
        out = digits + "e" + exp if k == 1 else digits[0] + "." + digits[1:] + "e" + exp
    return sign + out


def _canonical_number(value: int | float) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non-finite number")
        if value.is_integer():
            value = int(value)
        else:
            return _es_number(value)
    if abs(value) > MAX_SAFE_INTEGER:
        raise CanonicalizationError("integer outside the safe range")
    return str(value)


def _canonical_string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogate
        raise CanonicalizationError("string is not well-formed Unicode") from exc
    return json.dumps(value, ensure_ascii=False)


def canonical_json(value, _depth: int = 0) -> str:
    if _depth > MAX_DEPTH:
        raise CanonicalizationError("nesting too deep")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v, _depth + 1) for v in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise CanonicalizationError("object keys must be strings")
        encoded = {k: _canonical_string(k) for k in value}
        keys = sorted(value, key=lambda k: k.encode("utf-8"))
        return "{" + ",".join(encoded[k] + ":" + canonical_json(value[k], _depth + 1) for k in keys) + "}"
    raise CanonicalizationError(f"unsupported type {type(value).__name__}")


def signing_input(
    *, msg_type: str, community_id: int, ts: int, msg_id: str, data: dict, author_user_id: int
) -> bytes:
    payload = {
        "author_user_id": author_user_id,
        "community_id": community_id,
        "data": data,
        "id": msg_id,
        "ts": ts,
        "type": msg_type,
    }
    return (SIGNING_PREFIX + canonical_json(payload)).encode("utf-8")


def registration_input(user_id: int, key_id: str) -> bytes:
    return f"{REGISTRATION_PREFIX}{user_id}\n{key_id}".encode("utf-8")


# ── Encoding helpers ─────────────────────────────────────────────


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    text = text.strip()
    if not text or len(text) > 4096:
        raise ValueError("bad base64")
    std = text.replace("-", "+").replace("_", "/")
    return base64.b64decode(std + "=" * (-len(std) % 4), validate=True)


def key_id_for(spki_der: bytes) -> str:
    return b64url_encode(hashlib.sha256(spki_der).digest())


# ── Public keys ──────────────────────────────────────────────────


class InvalidPublicKey(ValueError):
    pass


def _load_jwk(jwk: dict) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or "d" in jwk:
        raise InvalidPublicKey("JWK must be a public EC P-256 key")
    try:
        x = b64url_decode(str(jwk["x"]))
        y = b64url_decode(str(jwk["y"]))
    except (KeyError, ValueError) as exc:
        raise InvalidPublicKey("JWK x/y missing or not base64url") from exc
    if len(x) != 32 or len(y) != 32:
        raise InvalidPublicKey("JWK x/y must be 32 bytes")
    try:
        return ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()
        ).public_key()
    except ValueError as exc:  # point not on the curve
        raise InvalidPublicKey("not a point on P-256") from exc


def parse_public_key(public_key: str | dict) -> tuple[ec.EllipticCurvePublicKey, bytes]:
    """Parse a P-256 public key given as base64/base64url SPKI DER or a JWK.

    Returns the key and its canonical SPKI DER encoding. Raises InvalidPublicKey.
    """
    if isinstance(public_key, dict):
        key = _load_jwk(public_key)
    else:
        text = public_key.strip()
        if text.startswith("{"):
            try:
                jwk = json.loads(text)
            except ValueError as exc:
                raise InvalidPublicKey("malformed JWK") from exc
            if not isinstance(jwk, dict):
                raise InvalidPublicKey("malformed JWK")
            key = _load_jwk(jwk)
        else:
            try:
                der = b64url_decode(text)
                loaded = serialization.load_der_public_key(der)
            except (ValueError, TypeError) as exc:
                raise InvalidPublicKey("not a DER SubjectPublicKeyInfo") from exc
            if not isinstance(loaded, ec.EllipticCurvePublicKey) or not isinstance(
                loaded.curve, ec.SECP256R1
            ):
                raise InvalidPublicKey("key must be ECDSA P-256")
            key = loaded
    spki = key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return key, spki


def load_spki(spki_b64: str) -> ec.EllipticCurvePublicKey:
    key = serialization.load_der_public_key(b64url_decode(spki_b64))
    assert isinstance(key, ec.EllipticCurvePublicKey)
    return key


def verify_p1363(public_key: ec.EllipticCurvePublicKey, signature_b64: str, message: bytes) -> bool:
    """Verify a base64url IEEE P1363 (r || s) ECDSA-SHA256 signature."""
    try:
        raw = b64url_decode(signature_b64)
    except ValueError:
        return False
    if len(raw) != 64:
        return False
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:], "big")
    try:
        public_key.verify(encode_dss_signature(r, s), message, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError):
        return False
    return True
