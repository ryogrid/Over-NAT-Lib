import sys
import socket
import argparse
import traceback
from io import BufferedRWPair, BufferedWriter, BufferedReader, BytesIO

def server_loop():
    if not args.target:
        args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((args.target, args.port))
    server.listen(1)

    print('Waiting for connections...', file=sys.stderr)
    clientsock, client_address = server.accept() #接続されればデータを格納

    fileno = sys.stdout.fileno()
    with open(fileno, "wb", closefd=False) as f:
        while True:
            rcvmsg = clientsock.recv(1024)
            #print('Received -> %s' % (rcvmsg))
            if rcvmsg == None or len(rcvmsg) == 0:
              break
            else:
                f.write(rcvmsg)

    clientsock.close()

def distributer_loop():
    if not args.target:
        args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((args.target, args.port))
    server.listen()
    while True:
        print('Waiting for connections...', file=sys.stderr)
        clientsock, client_address = server.accept() #接続されればデータを格納

        with open(args.file, "rb") as f:
            while True:
                data = f.read(1024)
                #print('Received -> %s' % (rcvmsg))
                if data == None or len(data) == 0:
                    break
                else:
                    clientsock.sendall(data)

        clientsock.close()

def client_loop():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((args.target, args.port))

        fileno = sys.stdin.fileno()
        with open(fileno, "rb", closefd=False) as f:
            #if args.filename != "":
            if len(args.filename) >= 1:
                client.sendall("sendfile".encode())
                fname_bytes = len(args.filename.encode())
                print(fname_bytes)
                fname = '{0:02d}'.format(fname_bytes)
                client.sendall(fname.encode())
                client.sendall(args.filename.encode())
            while True:
                data = f.read(4096)
                if data == None or len(data) == 0:
                    break
                else:
                    ret = client.sendall(data)
                    print("send: " + str(len(data)))

    except Exception as e:
        print(e)
        print('Exception! Exiting.')
        client.close()

def receiver_loop():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((args.target, args.port))

        fileno = sys.stdout.fileno()
        with open(fileno, "wb", closefd=False) as f:
            while True:
                rcvmsg = client.recv(4096)
                #print('Received -> %s' % (rcvmsg))
                if rcvmsg == None or len(rcvmsg) == 0:
                    break
                # if len(rcvmsg) == 8:
                #     decoded_str = None
                #     try:
                #         decoded_str = rcvmsg.decode()
                #     except:
                #         f.write(rcvmsg)
                #         continue
                #         # print(rcvmsg, file=sys.stderr)
                #         # traceback.print_exc()
                #     if decoded_str != None and decoded_str == "finished":
                #         f.flush()
                #         client.close()
                #         sys.exit(0)
                #     if rcvmsg == None or len(rcvmsg) == 0:
                #         break
                #     # print(rcvmsg, file=sys.stderr)
                #     # print('break', file=sys.stderr)
                else:
                    f.write(rcvmsg)
    except Exception as e:
        print(e, file=sys.stderr)
        print('Exception! Exiting.', file=sys.stderr)
        client.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                description='BHP Net Tool',
                epilog='''\
Examples:
    type hoge.mp4 | python pync.py -c -t 127.0.0.1 -p 10000
    python pync.py -r -t 127.0.0.1 -p 10100 > bar.mp4
    python pync.py -s -p 10000 > foo.mp4
    python pync.py -d -p 10100 -f bar.mp4
    ''')

parser.add_argument('-c', '--client', help='run as client (sender)', action='store_true')
parser.add_argument('-s', '--server', help='listen on [host]:[port] for incoming connections', action='store_true')
parser.add_argument('-r', '--receiver', help='run as client (receiver)', action='store_true')
parser.add_argument('-d', '--distributer', help='listen on [host]:[port] for incoming connections and send specified file contents to client', action='store_true')
parser.add_argument('-f', '--filename', default="", help='when send file, specify filename which is used on remote machine (contents uses data from stdin)')
parser.add_argument('-t', '--target', default="127.0.0.1")
parser.add_argument('-p', '--port', default=None, type=int, required=True)
args = parser.parse_args()

if args.client and args.port != 0:
    client_loop()
elif args.receiver and args.target and args.port:
    receiver_loop()
elif args.server and args.port:
    server_loop()
elif args.distributer and args.port and args.file:
    distributer_loop()
else:
    parser.print_help()
    sys.exit(1)
