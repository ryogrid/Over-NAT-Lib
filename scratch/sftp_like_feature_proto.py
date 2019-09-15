# coding: utf-8

import traceback
import sys
import socket
import time
import os
from multiprocessing import Process
from fs.osfs import OSFS

last_send_command = ""

def client_handle_msg(msg):
    if last_send_command == "pwd":
        print(msg.decode())
    elif last_send_command == "ls":
        print(msg.decode())

def client_run():
    global last_send_command

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect(("127.0.0.1", 11000))
        while True:
            try:
                inputed_line = input("Please type command and press Retuen key: ")
                last_send_command = inputed_line

                client.sendall(inputed_line.encode())
                recvmsg = client.recv(1024)
                client_handle_msg(recvmsg)
                #print(recvmsg.decode())
            except:
                traceback.print_exc()
                print("echo client exit due to some exception occur.")
                break
    except:
        traceback.print_exc()

receiver_fs = None

def setup_pyfilesystem_object():
    global receiver_fs

    #receiver_fs = OSFS(os.getcwd())
    receiver_fs = OSFS("~/")

def handle_pwd(cmd_str):
    url = receiver_fs.geturl("./")
    url = url.replace("file://", "")
    url = url.replace("\\.\\", "")
    return url.encode()

def convert_to_appropriate_size_sting(size):
    GB = float(1024 * 1024 * 1024)
    MB = float(1024 * 1024)
    KB = float(1024)

    formated_size = None
    if size > GB:
        formated_size = "{:03.4f} GB".format(size / GB)
    elif size > MB:
        formated_size = "{:03.4f} MB".format(size / MB)
    elif size > KB:
        formated_size = "{:03.4f} MB".format(size / KB)
    else:
        formated_size = "{:7d}  B".format(size)

    return "{:>11}".format(formated_size)

def handle_ls(cmd_str):
    ret_str_file = ""
    ret_str_dir = ""
    dir_obj_infos = receiver_fs.scandir("./", namespaces = ["basic", "details"])
    for info in dir_obj_infos:
        if info.is_dir:
            ret_str_dir += "           {0:<10}\n".format(info.name)
        else:
            ret_str_file += "{0} {1:<10} \n".format(convert_to_appropriate_size_sting(info.size), info.name)

    return (ret_str_file + ret_str_dir).encode()

# return binary data
def server_handle_msg(msg):
    global receiver_fs

    cmd = msg.decode()
    if cmd.startswith("pwd"):
        return handle_pwd(cmd)
    elif cmd.startswith("ls"):
        return handle_ls(cmd)

def server_run():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 11000))
    server.listen()

    setup_pyfilesystem_object()
    while True:
        print('Waiting for connections...', file=sys.stderr)
        clientsock, client_address = server.accept()  # 接続されればデータを格納

        while True:
            data = clientsock.recv(1024)
            if data == None or len(data) == 0:
                break
            else:
                resp = server_handle_msg(data)
                clientsock.sendall(resp)
                #clientsock.sendall(data)

        clientsock.close()

def pyfs_scratch():
    # home_fs = OSFS("~/")
    home_fs = OSFS("/")
    # home_fs = OSFS("C:/")

    print(home_fs.listdir("../"))
    # print(home_fs.tree(max_levels = 0, dirs_first = True))
    dir_obj_infos = home_fs.scandir("../")
    for info in dir_obj_infos:
        if info.is_dir:
            print("[dir]  {}".format(info.name))
        else:
            print("[file] {} {} MB".format(info.name, info.size / float(1024 * 1024)))

if __name__ == '__main__':
    try:
        p = Process(target=server_run, args=())
        p.start()
        time.sleep(2)
        client_run()
    except KeyboardInterrupt:
        sys.exit(0)