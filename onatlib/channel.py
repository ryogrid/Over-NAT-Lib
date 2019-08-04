import sys
import socket
import traceback
import threading

class Channel:

    @staticmethod
    def create_channel(host="127.0.0.1", send_port=10100, recv_port=10200, recv_callback=None):
        channel_obj = Channel(host, send_port, recv_port, recv_callback)
        if channel_obj._all_connect_succes:
            return channel_obj
        else:
            return None

    @staticmethod
    def recv_data_th(sock, callback):
        while True:
            try:
                rcvmsg = sock.recv(1024)
                if rcvmsg == None or len(rcvmsg) == 0:
                    break
                else:
                    callback(rcvmsg)
            except:
                traceback.print_exc()
                print("recv_data_th exit", file=sys.stderr)
                break

    def __init__(self, host, send_port, recv_port, recv_callback):
        self._host = host
        self._send_port = send_port
        self._recv_port = recv_port
        self._recv_callback = recv_callback
        self._recv_with_handler = False
        self._send_sock = None
        self._recv_sock = None
        self._recv_th = None
        self._all_connect_succes = True

        if self.connect_to_send_port():
            if self.connect_to_recv_port():
                pass

        if self._recv_callback:
            self._redv_th = threading.Thread(target=Channel.recv_data_th, args=([self._recv_sock, self._recv_callback]), daemon=True)
            self._redv_th.start()

    def get_reader_sock(self):
        if self._recv_callback != None:
            return None
        return self._recv_sock

    def get_writer_sock(self):
        return self._send_sock

    def connect_to_send_port(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            client.connect((self._host, self._send_port))
        except:
            traceback.print_exc()
            self._all_connect_succes = False
            return False

        self._send_sock = client
        return True

    def connect_to_recv_port(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            client.connect((self._host, self._recv_port))
        except:
            traceback.print_exc()
            self._all_connect_succes = False
            return False

        self._recv_sock = client
        return True

    def all_sock_close(self):
        if self._send_sock:
            self._send_sock.close()
        if self._recv_sock:
            self._recv_sock.close()

