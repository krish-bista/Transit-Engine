import socket
import threading
import sys

TARGET_HOST = "172.19.182.96"
TARGET_PORT = 8000
LISTEN_PORT = 8000

def forward(src, dst):
    try:
        while True:
            data = src.recv(8192)
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

def handle_client(client_socket):
    try:
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.connect((TARGET_HOST, TARGET_PORT))
        t1 = threading.Thread(target=forward, args=(client_socket, target_socket), daemon=True)
        t2 = threading.Thread(target=forward, args=(target_socket, client_socket), daemon=True)
        t1.start()
        t2.start()
    except Exception:
        try:
            client_socket.close()
        except Exception:
            pass

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", LISTEN_PORT))
    server.listen(128)
    print(f"Relay listening on 0.0.0.0:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}")
    while True:
        client, addr = server.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()

if __name__ == "__main__":
    main()
