import socket
import threading
import time

WSL_IP = "172.19.182.96"

def forward(src, dst):
    try:
        while True:
            data = src.recv(16384)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

def start_proxy(listen_port, target_ip, target_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", listen_port))
    server.listen(128)
    print(f"Proxy 0.0.0.0:{listen_port} -> {target_ip}:{target_port} started.")

    while True:
        try:
            client, addr = server.accept()
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.connect((target_ip, target_port))
            t1 = threading.Thread(target=forward, args=(client, target), daemon=True)
            t2 = threading.Thread(target=forward, args=(target, client), daemon=True)
            t1.start()
            t2.start()
        except Exception as e:
            try:
                client.close()
            except Exception:
                pass

def main():
    t_web = threading.Thread(target=start_proxy, args=(8000, WSL_IP, 8000), daemon=True)
    t_web.start()
    start_proxy(50051, WSL_IP, 50051)

if __name__ == "__main__":
    main()
