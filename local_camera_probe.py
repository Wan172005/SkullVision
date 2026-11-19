"""Bounded, unauthenticated HTTP diagnostics for a loopback camera lab."""

import asyncio
import ipaddress
import math
import socket
import xml.etree.ElementTree as ET

SOAP = 'http://www.w3.org/2003/05/soap-envelope'
DEVICE = 'http://www.onvif.org/ver10/device/wsdl'
CAPABILITIES_REQUEST = (
    f'<s:Envelope xmlns:s="{SOAP}" xmlns:d="{DEVICE}"><s:Body>'
    '<d:GetCapabilities><d:Category>All</d:Category></d:GetCapabilities>'
    '</s:Body></s:Envelope>').encode('utf-8')

TCP_PORTS = range(1, 65536)
WSL_LAB_ADDRESS = '172.27.100.182'


def _local_ipv4_addresses():
    import netifaces
    return {entry['addr'] for interface in netifaces.interfaces()
            for entry in netifaces.ifaddresses(interface).get(netifaces.AF_INET, [])
            if 'addr' in entry}


def is_local_lab_address(host):
    """Allow loopback and the requested WSL address only while locally assigned."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if str(address) != WSL_LAB_ADDRESS:
        return False
    try:
        return str(address) in _local_ipv4_addresses()
    except (ImportError, OSError, ValueError):
        return False


async def _connect_local_port(host, port, timeout):
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.setblocking(False)
        await asyncio.wait_for(
            asyncio.get_running_loop().sock_connect(connection, (host, port)), timeout)


def scan_local_tcp_ports(host, timeout=15.0, connection_timeout=0.2, on_progress=None):
    """Check every TCP port on a numeric loopback IP within a total deadline."""
    address = ipaddress.ip_address(host)
    if not is_local_lab_address(host):
        raise ValueError('All-port lab discovery requires loopback or the configured WSL IP assigned to this machine')
    for value in (timeout, connection_timeout):
        if not math.isfinite(value) or not 0 < value <= 30:
            raise ValueError('Timeout must be greater than zero and at most 30 seconds')
    summary = {'checked': 0, 'total': len(TCP_PORTS), 'open_ports': [],
               'timeout_ports': [], 'deadline_reached': False}

    async def run():
        ports = iter(TCP_PORTS)
        async def worker():
            for port in ports:
                try:
                    await _connect_local_port(str(address), port, connection_timeout)
                    summary['open_ports'].append(port)
                except asyncio.TimeoutError:
                    summary['timeout_ports'].append(port)
                except OSError:
                    pass
                summary['checked'] += 1
                if on_progress and summary['checked'] % 2000 == 0:
                    on_progress(summary['checked'], summary['total'])
        workers = [asyncio.create_task(worker()) for _ in range(min(128, len(TCP_PORTS)))]
        try:
            await asyncio.wait_for(asyncio.gather(*workers), timeout)
        except asyncio.TimeoutError:
            summary['deadline_reached'] = True
        finally:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    asyncio.run(run())
    summary['open_ports'].sort()
    summary['timeout_ports'].sort()
    summary['unchecked'] = summary['total'] - summary['checked']
    if on_progress:
        on_progress(summary['checked'], summary['total'])
    return summary


async def _read_http(host, port, path='/', payload=None):
    reader, writer = await asyncio.open_connection(host, port)
    try:
        authority = f'[{host}]' if ':' in host else host
        method = 'POST' if payload is not None else 'GET'
        extra = ''
        if payload is not None:
            extra = (f'Content-Length: {len(payload)}\r\n'
                     f'Content-Type: application/soap+xml; charset=utf-8; action="{DEVICE}/GetCapabilities"\r\n')
        writer.write((f'{method} {path} HTTP/1.1\r\nHost: {authority}:{port}\r\n'
                      f'{extra}Connection: close\r\nUser-Agent: SkullVision-Local-Lab\r\n\r\n').encode('ascii')
                     + (payload or b''))
        await writer.drain()
        raw_headers = await reader.readuntil(b'\r\n\r\n')
        lines = raw_headers.decode('latin-1').split('\r\n')
        version, code, *_ = lines[0].split()
        if version not in ('HTTP/1.0', 'HTTP/1.1') or not code.isdigit():
            raise ValueError('Response is not HTTP/1.0 or HTTP/1.1')
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                name, value = line.split(':', 1)
                headers[name.lower()] = value.strip()
        body = b''
        if code == '200' and headers.get('content-length') != '0':
            if payload is None:
                body = await reader.read(16384)
            elif headers.get('transfer-encoding', '').lower() == 'chunked':
                while True:
                    size = int((await reader.readline()).split(b';', 1)[0].strip(), 16)
                    if not size:
                        break
                    if size < 0 or len(body) + size > 65536:
                        raise ValueError('ONVIF response exceeds 64 KiB')
                    body += await reader.readexactly(size)
                    if await reader.readexactly(2) != b'\r\n':
                        raise ValueError('Invalid HTTP chunk ending')
            elif 'content-length' in headers:
                size = int(headers['content-length'])
                if not 0 <= size <= 65536:
                    raise ValueError('ONVIF response exceeds 64 KiB')
                body = await reader.readexactly(size)
            else:
                while chunk := await reader.read(4096):
                    body += chunk
                    if len(body) > 65536:
                        raise ValueError('ONVIF response exceeds 64 KiB')
        return {'status': int(code), 'headers': headers,
                'sample': body.decode('utf-8', errors='replace'), 'error': None}
    finally:
        writer.close()


def probe_local_camera(host, port, timeout=3.0):
    """GET / then read-only ONVIF probe; loopback only, with one total deadline."""
    address = ipaddress.ip_address(host)
    if not is_local_lab_address(host):
        raise ValueError('Local camera diagnostics require loopback or the configured WSL IP assigned to this machine')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535')
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('Timeout must be greater than zero and at most 30 seconds')

    async def check():
        result = await _read_http(str(address), port)
        result.update(onvif_verified=False, onvif_status=None, onvif_error=None)
        if result['status'] in (401, 403):
            return result
        try:
            onvif = await _read_http(str(address), port, '/onvif/device_service', CAPABILITIES_REQUEST)
            result['onvif_status'] = onvif['status']
            if onvif['status'] == 200:
                root = ET.fromstring(onvif['sample'])
                for soap_ns in (SOAP, 'http://schemas.xmlsoap.org/soap/envelope/'):
                    node = root.find(f'{{{soap_ns}}}Body/{{{DEVICE}}}GetCapabilitiesResponse/{{{DEVICE}}}Capabilities')
                    if root.tag == f'{{{soap_ns}}}Envelope' and node is not None:
                        result['onvif_verified'] = True
                        break
                if not result['onvif_verified']:
                    result['onvif_error'] = 'HTTP 200 without an ONVIF GetCapabilitiesResponse'
        except (OSError, ValueError, ET.ParseError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError) as exc:
            result['onvif_error'] = str(exc)
        return result

    async def run():
        return await asyncio.wait_for(check(), timeout)

    try:
        return asyncio.run(run())
    except asyncio.TimeoutError:
        reason = f'Timeout after {timeout:g}s on {host}:{port}; HTTP result unknown'
    except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        reason = f'HTTP check failed on {host}:{port}: {exc}'
    return {'status': None, 'headers': {}, 'sample': '', 'error': reason}
