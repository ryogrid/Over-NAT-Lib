import sys
import socket
import argparse
from threading import Thread
import platform

def server_loop():
    if not args.target:
        args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((args.target, args.port))
    server.listen(1)

    print('Waiting for connections...')
    clientsock, client_address = server.accept() #接続されればデータを格納

    print(clientsock)
    print(client_address)
    print(platform.system())
    # if platform.system() == "Windows":
    #     import os, msvcrt
    #     msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    fileno = sys.stdout.fileno()
    with open(fileno, "wb", closefd=False) as f:
        while True:
            rcvmsg = clientsock.recv(1024)
            #print('Received -> %s' % (rcvmsg))
            if rcvmsg == None or len(rcvmsg) == 0:
              break
            else:
                f.write(rcvmsg)
                #sys.stdout.write(rcvmsg.decode())
            #sys.stdout.write(rcvmsg)
        # print('Type message...')
        # s_msg = input().replace('b', '').encode('utf-8')
        # if s_msg == '':
        #   break
        # print('Wait...')

    clientsock.close()


def client_loop():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((args.target, args.port))

        # if platform.system() == "Windows":
        #     print("set stdin mode to binary")
        #     import os, msvcrt
        #     msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        fileno = sys.stdin.fileno()
        with open(fileno, "rb", closefd=False) as f:
            while True:
                #data = sys.stdin.read()
                data = f.read(1024)
                if data == None or len(data) == 0:
                    break
                else:
                    client.send(data)
                    #client.send(data.encode())
    except Exception as e:
        print(e)
        print('Exception! Exiting.')
        client.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                description='BHP Net Tool',
                epilog='''\
Examples:
    pync.py -t 192.168.0.1 -p 100100 -c -t 127.0.0.1 -p 10000
    pync.py -t 192.168.0.1 -p 100100 -s -p 10000
    echo 'ABCDEFGHI' | python pync.py -t 192.168.0.1 -p 10000''')

parser.add_argument('-c', '--client', help='run as client', action='store_true')
parser.add_argument('-s', '--server', help='listen on [host]:[port] for incoming connections', action='store_true')
parser.add_argument('-t', '--target', default=None)
parser.add_argument('-p', '--port', default=None, type=int, required=True)
args = parser.parse_args()

if args.client and args.target and args.port:
    client_loop()
elif args.server and args.port:
    server_loop()
else:
    parser.print_help()
    sys.exit(1)
