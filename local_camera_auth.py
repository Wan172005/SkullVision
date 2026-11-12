"""Authentication checks for a camera simulator on loopback only."""

import base64
import hashlib
import ipaddress
import re
import secrets
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from requests.utils import parse_dict_header


SOAP = 'http://www.w3.org/2003/05/soap-envelope'
DEVICE = 'http://www.onvif.org/ver10/device/wsdl'
WSSE = ('http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd')
WSU = ('http://docs.oasis-open.org/wss/2004/01/'
       'oasis-200401-wss-wssecurity-utility-1.0.xsd')
TOKEN_PROFILE = ('http://docs.oasis-open.org/wss/2004/01/'
                 'oasis-200401-wss-username-token-profile-1.0')
SOAP_PROFILE = ('http://docs.oasis-open.org/wss/2004/01/'
                'oasis-200401-wss-soap-message-security-1.0')


def _onvif_request(session, url, username=None, password=None):
    envelope = ET.Element(f'{{{SOAP}}}Envelope')
    if username is not None:
        header = ET.SubElement(envelope, f'{{{SOAP}}}Header')
        security = ET.SubElement(header, f'{{{WSSE}}}Security')
        token = ET.SubElement(security, f'{{{WSSE}}}UsernameToken')
        ET.SubElement(token, f'{{{WSSE}}}Username').text = username
        nonce = secrets.token_bytes(16)
        created = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        digest = hashlib.sha1(nonce + created.encode() + password.encode()).digest()
        ET.SubElement(token, f'{{{WSSE}}}Password',
                      Type=TOKEN_PROFILE + '#PasswordDigest').text = base64.b64encode(digest).decode()
        ET.SubElement(token, f'{{{WSSE}}}Nonce',
                      EncodingType=SOAP_PROFILE + '#Base64Binary').text = base64.b64encode(nonce).decode()
        ET.SubElement(token, f'{{{WSU}}}Created').text = created
    body = ET.SubElement(envelope, f'{{{SOAP}}}Body')
    ET.SubElement(body, f'{{{DEVICE}}}GetDeviceInformation')
    session.cookies.clear()
    response = session.post(
        url, data=ET.tostring(envelope, encoding='utf-8', xml_declaration=True),
        headers={'Content-Type': 'application/soap+xml; charset=utf-8'},
        timeout=(2, 3), allow_redirects=False)
    if response.status_code in (401, 403):
        return False
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise RuntimeError(f'ONVIF returned HTTP {response.status_code} without valid SOAP') from exc
    body = root.find(f'{{{SOAP}}}Body')
    if body is None:
        raise RuntimeError('ONVIF response has no SOAP 1.2 Body')
    fault = body.find(f'{{{SOAP}}}Fault')
    if fault is not None:
        codes = [n.text.rsplit(':', 1)[-1] for n in fault.iter(f'{{{SOAP}}}Value') if n.text]
        if any(c in ('NotAuthorized', 'FailedAuthentication') for c in codes):
            return False
        raise RuntimeError(f'ONVIF SOAP fault: {", ".join(codes) or "unknown"}')
    if response.status_code == 200 and body.find(f'{{{DEVICE}}}GetDeviceInformationResponse') is not None:
        return True
    raise RuntimeError(f'Unexpected ONVIF response: HTTP {response.status_code}')


def _read_rtsp(stream):
    status = stream.readline(8193)
    match = re.fullmatch(rb'RTSP/1\.0 (\d{3})[^\r\n]*\r\n', status)
    if not match:
        raise RuntimeError('Invalid RTSP status line')
    headers = {}
    size = len(status)
    while True:
        line = stream.readline(8193)
        size += len(line)
        if not line or size > 65536 or not line.endswith(b'\r\n'):
            raise RuntimeError('Invalid or oversized RTSP headers')
        if line == b'\r\n':
            break
        name, separator, value = line.decode('latin-1').partition(':')
        if not separator:
            raise RuntimeError('Malformed RTSP header')
        key = name.lower()
        headers[key] = ', '.join(filter(None, (headers.get(key), value.strip())))
    length = int(headers.get('content-length', '0'))
    if not 0 <= length <= 1024 * 1024:
        raise RuntimeError('Invalid RTSP body length')
    body = stream.read(length)
    if len(body) != length:
        raise RuntimeError('Truncated RTSP body')
    return int(match.group(1)), headers, body


def _rtsp_authorization(challenge, url, username, password):
    digest = re.search(r'(?:^|,\s*)Digest\s+(.+?)(?=,\s*(?:Basic|Digest)\s|$)',
                       challenge, re.IGNORECASE)
    if not digest:
        if re.search(r'(?:^|,\s*)Basic\s', challenge, re.IGNORECASE):
            return 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()
        raise RuntimeError('RTSP did not advertise Basic/Digest authentication')
    fields = parse_dict_header(digest.group(1))
    algorithm = fields.get('algorithm', 'MD5').upper()
    hashes = {'MD5': 'md5', 'SHA-256': 'sha256'}
    base_algorithm = algorithm.removesuffix('-SESS')
    if base_algorithm not in hashes:
        raise RuntimeError(f'Unsupported RTSP Digest algorithm: {algorithm}')
    realm, nonce = fields['realm'], fields['nonce']
    cnonce = secrets.token_hex(16)
    def hashed(value):
        return hashlib.new(hashes[base_algorithm], value.encode()).hexdigest()
    def quoted(value):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    ha1 = hashed(f'{username}:{realm}:{password}')
    if algorithm.endswith('-SESS'):
        ha1 = hashed(f'{ha1}:{nonce}:{cnonce}')
    ha2 = hashed(f'DESCRIBE:{url}')
    qop = fields.get('qop')
    if qop is not None and 'auth' not in [v.strip() for v in qop.split(',')]:
        raise RuntimeError('RTSP Digest requires an unsupported qop')
    response = hashed(f'{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}' if qop is not None
                      else f'{ha1}:{nonce}:{ha2}')
    parts = [f'username={quoted(username)}', f'realm={quoted(realm)}',
             f'nonce={quoted(nonce)}', f'uri={quoted(url)}',
             f'response={quoted(response)}', f'algorithm={algorithm}']
    if qop is not None:
        parts.extend(['qop=auth', 'nc=00000001', f'cnonce={quoted(cnonce)}'])
    elif algorithm.endswith('-SESS'):
        parts.append(f'cnonce={quoted(cnonce)}')
    if 'opaque' in fields:
        parts.append(f'opaque={quoted(fields["opaque"])}')
    return 'Digest ' + ', '.join(parts)


def _rtsp_request(url, host, port, username=None, password=None, return_response=False):
    with socket.create_connection((host, port), timeout=3) as sock:
        with sock.makefile('rb') as stream:
            def describe(cseq, authorization=None):
                message = f'DESCRIBE {url} RTSP/1.0\r\nCSeq: {cseq}\r\nAccept: application/sdp\r\n'
                if authorization:
                    message += f'Authorization: {authorization}\r\n'
                sock.sendall((message + '\r\n').encode())
                return _read_rtsp(stream)
            status, headers, body = describe(1)
            if status == 401 and username is not None:
                auth = _rtsp_authorization(headers.get('www-authenticate', ''), url, username, password)
                status, headers, body = describe(2, auth)
            if return_response:
                return status, headers, body
            if status in (401, 403):
                return False
            if status == 200 and headers.get('content-type', '').split(';')[0].strip() == 'application/sdp' and body.startswith(b'v=0'):
                return True
            raise RuntimeError(f'Unexpected RTSP DESCRIBE response: {status}')


def probe_rtsp_url(url, username=None, password=None):
    """Verify a stream description; optional known credentials are loopback-only."""
    parsed = urlparse(url)
    address = ipaddress.ip_address(parsed.hostname)
    if (parsed.scheme != 'rtsp' or parsed.username is not None or parsed.password is not None
            or parsed.fragment or any(c in url for c in ('\r', '\n'))):
        raise ValueError('Use an RTSP URL with a literal IP and no embedded credentials')
    if (username is None) != (password is None):
        raise ValueError('Supply both username and password, or neither')
    if username is not None:
        if not address.is_loopback:
            raise ValueError('Authenticated path verification is restricted to the loopback lab')
        if any(c in username + password for c in ('\r', '\n')):
            raise ValueError('Credentials must not contain line breaks')
    port = parsed.port or 554
    result = {'url': url, 'port': port, 'verified': False, 'status': None,
              'verification': 'DESCRIBE/SDP'}
    try:
        status, headers, body = _rtsp_request(
            url, parsed.hostname, port, username, password, return_response=True)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        result['reason'] = f'RTSP check failed: {exc}'
        return result
    result['status'] = status
    if status == 200:
        content_type = headers.get('content-type', '').split(';')[0].strip().lower()
        lines = body.decode('utf-8', errors='replace').splitlines()
        valid_sdp = (content_type == 'application/sdp' and bool(lines) and lines[0] == 'v=0'
                     and all(any(line.startswith(prefix) for line in lines)
                             for prefix in ('o=', 's=', 't='))
                     and any(re.match(r'm=(?:video|audio)\s+\d+(?:/\d+)?\s+\S+\s+\S+', line)
                             for line in lines))
        result['verified'] = valid_sdp
        result['reason'] = ('Valid audio/video SDP received; playback not tested' if valid_sdp
                            else 'RTSP 200 without a valid audio/video SDP; path not verified')
    elif status in (401, 403):
        result['reason'] = f'RTSP {status}: authentication/access denied; path existence not confirmed'
    elif status == 404:
        result['reason'] = 'RTSP 404: path not found'
    elif 300 <= status < 400:
        result['reason'] = f'RTSP {status}: redirect not followed; path not verified'
    else:
        result['reason'] = f'RTSP {status}: path not verified'
    return result


def check_local_camera_auth(protocol, url, usernames, passwords, on_attempt):
    """Return accepted fixtures; refuse remote hosts and unprotected resources."""
    parsed = urlparse(url)
    if protocol not in ('ONVIF', 'RTSP'):
        raise ValueError('Supported local protocols: ONVIF and RTSP')
    schemes = ('http', 'https') if protocol == 'ONVIF' else ('rtsp',)
    if (parsed.scheme not in schemes or not ipaddress.ip_address(parsed.hostname).is_loopback
            or parsed.username is not None or parsed.password is not None or parsed.fragment
            or any(c in url for c in ('\r', '\n'))):
        raise ValueError('Use a full URL with a literal loopback IP and no embedded credentials')
    if not parsed.path or parsed.path == '/':
        raise ValueError('Specify the ONVIF device endpoint or the full RTSP stream path')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80 if protocol == 'ONVIF' else 554)
    usernames, passwords = list(dict.fromkeys(usernames)), list(dict.fromkeys(passwords))
    total = len(usernames) * len(passwords)
    if total == 0:
        raise ValueError('Local lab check requires at least one username and password')
    if any('\r' in s or '\n' in s for s in usernames + passwords):
        raise ValueError('Credential entries must not contain line breaks')
    results = []
    with requests.Session() as session:
        session.trust_env = False
        def probe(username=None, password=None):
            if protocol == 'ONVIF':
                return _onvif_request(session, url, username, password)
            return _rtsp_request(url, parsed.hostname, port, username, password)
        if probe():
            raise RuntimeError('This operation works without authentication; no credentials tested')
        invalid = 'lab_invalid_' + secrets.token_hex(16)
        if probe(invalid, invalid):
            raise RuntimeError('Invalid credentials were accepted; no credentials tested')
        attempted = 0
        for username in usernames:
            for password in passwords:
                accepted = probe(username, password)
                attempted += 1
                on_attempt(attempted, total, accepted)
                if accepted:
                    results.append({'service': protocol + ' local lab', 'url': url,
                                    'port': port, 'username': username, 'password': password})
    return results
