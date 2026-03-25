import asyncio
import subprocess
import sys
import socket


def get_target_ip():
    wsl_ip = subprocess.run(['wsl', 'hostname', '-I'], capture_output=True, text=True).stdout.strip().split()[0]
    try:
        local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        local_ips = []
    if wsl_ip in local_ips:
        return '127.0.0.1'  # mirrored mode
    return wsl_ip  # NAT mode


def parse_ports(args):
    ports = []
    for arg in args:
        if ':' in arg:
            ext, intern = arg.split(':', 1)
            ports.append((int(ext), int(intern)))
        else:
            p = int(arg)
            ports.append((p, p))
    return ports


async def pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def handle_client(local_reader, local_writer, target_ip, target_port):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(target_ip, target_port)
        await asyncio.gather(
            pipe(local_reader, remote_writer),
            pipe(remote_reader, local_writer),
        )
    except Exception as e:
        print(f"[porta {target_port}] Erro: {e}")
    finally:
        local_writer.close()


async def start_proxy(listen_port, target_port, target_ip):
    servers = []
    # IPv4
    s4 = await asyncio.start_server(
        lambda r, w: handle_client(r, w, target_ip, target_port),
        '0.0.0.0', listen_port
    )
    servers.append(s4)
    # IPv6
    try:
        s6 = await asyncio.start_server(
            lambda r, w: handle_client(r, w, target_ip, target_port),
            '::', listen_port
        )
        servers.append(s6)
        print(f"  :{listen_port}  ->  {target_ip}:{target_port}  (IPv4 + IPv6)")
    except Exception:
        print(f"  :{listen_port}  ->  {target_ip}:{target_port}  (IPv4 only)")
    return servers


async def main(ports):
    target_ip = get_target_ip()
    mode = 'mirrored' if target_ip == '127.0.0.1' else 'NAT'
    print(f"\nModo: {mode} (destino: {target_ip})")
    print("Redirecionando:")

    all_servers = []
    for listen, target in ports:
        servers = await start_proxy(listen, target, target_ip)
        all_servers.extend(servers)

    print("\nProxy rodando. Ctrl+C para parar.\n")

    await asyncio.gather(*[s.serve_forever() for s in all_servers])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python wsl_proxy.py 3000 8000")
        print("     python wsl_proxy.py 3000:3001 8000:8001")
        sys.exit(1)

    ports = parse_ports(sys.argv[1:])

    try:
        asyncio.run(main(ports))
    except KeyboardInterrupt:
        print("\nProxy encerrado.")
