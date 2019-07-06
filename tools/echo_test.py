# coding: utf-8

import traceback
import sys
#import os


from os import path
#sys.path.append(path.dirname(path.abspath(__file__)) + "/../")

import argparse
from onatlib.channel import Channel

channel_to_p2p_serv = None

def print_message_handler(data):
    print(data.decode() + "\n")

def client_run():
    channel_to_p2p_serv = Channel.create_channel(recv_callback=print_message_handler)
    if channel_to_p2p_serv != None:
        writer_sock = channel_to_p2p_serv.get_writer_sock()
        while True:
            try:
                inputed_line = input("Please type characters and press Retuen key: ")
                writer_sock.sendall(inputed_line.encode())
            except:
                traceback.print_exc()
                print("echo client exit due to some exception occur.")
                break

def server_run():
    channel_to_p2p_serv = Channel.create_channel(send_port=10101, recv_port=10201)
    if channel_to_p2p_serv != None:
        writer_sock = channel_to_p2p_serv.get_writer_sock()
        reader_sock = channel_to_p2p_serv.get_reader_sock()
        while True:
            try:
                recvmsg = reader_sock.recv(1024)
                print(recvmsg.decode())
                writer_sock.sendall(recvmsg)
            except:
                traceback.print_exc()
                print("echo server exit due to some exception occur.")
                break

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='echo server and client')
    parser.add_argument('--role', choices=['client', 'server'])
    args = parser.parse_args()

    try:
        if args.role == "client":
            client_run()
        elif args.role == "server":
            server_run()
        else:
            print("unknown role specified.")
            print("exit.")
    except KeyboardInterrupt:
        sys.exit(0)
