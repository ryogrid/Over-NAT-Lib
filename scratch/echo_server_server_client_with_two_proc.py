# coding: utf-8

import traceback
import sys
#import threading
import socket
import time
from multiprocessing import Process

def client_run():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect(("127.0.0.1", 11000))
        while True:
            try:
                inputed_line = input("Please type characters and press Retuen key: ")
                client.sendall(inputed_line.encode())
                recvmsg = client.recv(1024)
                print(recvmsg.decode())
            except:
                traceback.print_exc()
                print("echo client exit due to some exception occur.")
                break
    except:
        traceback.print_exc()

def server_run():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 11000))
    server.listen()

    while True:
        print('Waiting for connections...', file=sys.stderr)
        clientsock, client_address = server.accept()  # 接続されればデータを格納

        while True:
            data = clientsock.recv(1024)
            if data == None or len(data) == 0:
                break
            else:
                clientsock.sendall(data)

        clientsock.close()

if __name__ == '__main__':
    try:
        #threading.Thread(target=server_run, args=([]), daemon=True)
        p = Process(target=server_run, args=())
        p.start()
        time.sleep(2)
        client_run()
    except KeyboardInterrupt:
        sys.exit(0)
