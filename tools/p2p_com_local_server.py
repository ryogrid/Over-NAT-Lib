# coding: utf-8

import argparse
import asyncio
import logging
import sys
import os
import threading
import datetime, time
import subprocess
import signal
from aiortcdc import RTCPeerConnection, RTCSessionDescription

#from os import path
#sys.path.append(path.dirname(path.abspath(__file__)) + "/../")

from onatlib.signaling_share_ws import create_signaling, add_signaling_arguments
import websocket
import traceback
import socket
import random
import string

try:
    import lsrvcommon
    from lsrvcommon import GlobalVals
    import sender
    import receiver
except:
    from . import lsrvcommon
    from .lsrvcommon import GlobalVals
    from . import sender
    from . import receiver

def ws_sub_receiver():
    def on_message(ws, message):
        #print(message,  file=sys.stderr)
        print("called on_message", file=sys.stderr)
        #print(message)

        if "receiver_connected" in message:
            if GlobalVals.remote_stdout_connected == False:
                print("receiver_connected")
            #print(fifo_q.getbuffer().nbytes)
            GlobalVals.remote_stdout_connected = True
        elif "receiver_disconnected" in message:
            GlobalVals.remote_stdout_connected = False
            GlobalVals.done_reading = False
        elif "sender_connected" in message:
            GlobalVals.remote_stdin_connected = True
        elif "sender_disconnected" in message:
            print("sender_disconnected")
            GlobalVals.remote_stdin_connected = False
            GlobalVals.is_received_client_disconnect_request = True

    def on_error(ws, error):
        print(error)

    def on_close(ws):
        print("### closed ###")

    def on_open(ws):
        print("app level ws (1) opend")
        try:
            if GlobalVals.args.role == 'send':
                ws.send(GlobalVals.args.gid + "rtos_chsig:join")
            else:
                ws.send(GlobalVals.args.gid + "stor_chsig:join")
        except:
            traceback.print_exc()

    ws = websocket.WebSocketApp(GlobalVals.ws_protcol_str + "://" + GlobalVals.args.signaling_host + ":" + str(GlobalVals.args.signaling_port) + "/",
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
    ws.on_open = on_open
    ws.run_forever()

def get_random_ID(length):
    dat = string.digits + string.digits + string.digits + \
            string.ascii_lowercase + string.ascii_uppercase

    return ''.join([random.choice(dat) for times in range(length)])


async def ice_establishment_state():
    #global force_exited
    while(GlobalVals.sctp_transport_established == False and "failed" not in GlobalVals.pc.iceConnectionState):
        print("ice_establishment_state: " + GlobalVals.pc.iceConnectionState, file=sys.stderr)
        await asyncio.sleep(1)
    if GlobalVals.sctp_transport_established == False:
        print("hole punching to remote machine failed.")
        GlobalVals.force_exited = True
        try:
            GlobalVals.loop.stop()
            GlobalVals.loop.close()
        except:
            pass
        print("exit.")

def work_as_parent():
    pass

async def send_keep_alive():
    while True:
        lsrvcommon.ws_sender_send_wrapper("keepalive")
        await asyncio.sleep(5)

async def parallel_by_gather():
    # execute by parallel
    def notify(order):
        print(order + " has just finished.")

    cors = None
    if GlobalVals.args.role == 'send':
        cors = [sender.run_offer(GlobalVals.pc, GlobalVals.signaling), sender.sender_server(), ice_establishment_state(), send_keep_alive()]
    else:
        cors = [receiver.run_answer(GlobalVals.pc, GlobalVals.signaling), ice_establishment_state(), send_keep_alive()]
    await asyncio.gather(*cors)
    return

def stdout_piper_th(role, proc):
    fileno = sys.stdout.fileno()
    with open(fileno, "wb", closefd=False) as stdout_fd:
        while not proc.poll():
            stdout_data = proc.stdout.readline()
            if stdout_data:
                stdout_fd.write(b''.join([role.encode(), ": ".encode(), stdout_data]))
                stdout_fd.flush()
            else:
                break

def stderr_piper_th(role, proc):
    fileno = sys.stderr.fileno()
    with open(fileno, "wb", closefd=False) as stderr_fd:
        while not proc.poll():
            stderr_data = proc.stderr.readline()
            if stderr_data:
                stderr_fd.write(b''.join([role.encode(), ": ".encode(), stderr_data]))
                stderr_fd.flush()
            else:
                break

def stdout_stderr_flusher_th(interval_sec):
    while True:
        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(interval_sec)

def get_relative_this_script_path():
    if os.name == 'nt':
        return __file__
    else:
        return os.getcwd() + "/" + __file__

def keyboard_interrupt_hundler():
    if GlobalVals.args.hierarchy == "parent":
        print("Ctrl-C keyboard interrupt received.")
        sys.stdout.flush()

        print("exit parent proc.")
        if os.name == 'nt':
            os.Kill(GlobalVals.sender_proc.pid, signal.CTRL_C_EVENT)
            os.Kill(GlobalVals.receiver_proc.pid, signal.CTRL_C_EVENT)
        else:
            os.Kill(GlobalVals.sender_proc.pid, signal.SIGINT)
            os.Kill(GlobalVals.receiver_proc.pid, signal.SIGINT)
        time.sleep(1)
    else:
        if GlobalVals.args.role == "send":
            print("exit send proc (child).")
        else:
            print("exit recv proc (child).")

    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(0)

def get_unixtime_microsec_part():
    cur = datetime.datetime.now()
    return cur.microsecond

def main():
    parser = argparse.ArgumentParser(description='Data channel file transfer')
    parser.add_argument('gid', default="", help="unique ID which should be shared by two users of p2p transport (if not specified, this program generate appropriate one)")
    parser.add_argument('--hierarchy', default="parent", choices=['parent', 'child'])
    parser.add_argument('--role', choices=['send', 'receive'])
    parser.add_argument('--name', choices=['tom', 'bob'])
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('--no-buffering', action='store_true')
    parser.add_argument('--send-stream-port', default=10100, type=int,
                        help='This local server make datachannel stream readable at this port')
    parser.add_argument('--recv-stream-port', default=10200, type=int,
                        help='This local server make datachannel stream readable at this port')
    parser.add_argument('--slide-stream-ports',
                        help='When you exec two process on same host, other side process should change streaming port', action='store_true')
    add_signaling_arguments(parser)
    args = parser.parse_args()
    GlobalVals.args = args

    # set seed from microsecond part of unixtime
    random.seed(get_unixtime_microsec_part())

    if args.gid == "please_gen":
        args.gid = get_random_ID(10)
        print("generated unique ID " + args.gid + ". you should share this with the other side user.")
        sys.exit(0)

    if len(args.gid) < 10:
        print("gid should have length at least 10 characters. I suggest use " + get_random_ID(10))
        sys.exit(0)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.secure_signaling == True:
        GlobalVals.ws_protcol_str = "wss"

    if args.hierarchy == 'parent':
        try:
            if args.name != "tom" and args.name != "bob":
                print("please pass --name argument. accebtable value is \\tom\\ or \\bob\\, which neeed different between communicate users (2users)")
                sys.exit(0)

            sender_cmd_args_list = []
            receiver_cmd_args_list = []

            # iprogram is converted to exe file
            if sys.argv[0] == "p2p_com_local_server.exe":
                sender_cmd_args_list.append("p2p_com_local_server.exe")
                receiver_cmd_args_list.append("p2p_com_local_server.exe")
            else:
                # if python_path == "":
                sender_cmd_args_list.append("python")
                receiver_cmd_args_list.append("python")

                sender_cmd_args_list.append(get_relative_this_script_path())
                receiver_cmd_args_list.append(get_relative_this_script_path())

            sender_cmd_args_list.append("--signaling")
            receiver_cmd_args_list.append("--signaling")
            sender_cmd_args_list.append("share-websocket")
            receiver_cmd_args_list.append("share-websocket")
            sender_cmd_args_list.append("--signaling-host")
            receiver_cmd_args_list.append("--signaling-host")
            sender_cmd_args_list.append(args.signaling_host)
            receiver_cmd_args_list.append(args.signaling_host)
            sender_cmd_args_list.append("--signaling-port")
            receiver_cmd_args_list.append("--signaling-port")
            sender_cmd_args_list.append(args.signaling_port)
            receiver_cmd_args_list.append(args.signaling_port)
            sender_cmd_args_list.append("--role")
            receiver_cmd_args_list.append("--role")
            sender_cmd_args_list.append("send")
            receiver_cmd_args_list.append("receive")
            if args.secure_signaling:
                sender_cmd_args_list.append("--secure-signaling")
                receiver_cmd_args_list.append("--secure-signaling")
            if args.slide_stream_ports:
                sender_cmd_args_list.append("--send-stream-port")
                receiver_cmd_args_list.append("--recv-stream-port")
                sender_cmd_args_list.append("10101")
                receiver_cmd_args_list.append("10201")
            if args.no_buffering:
                sender_cmd_args_list.append("--no-buffering")
                receiver_cmd_args_list.append("--no-buffering")
            if args.verbose:
                sender_cmd_args_list.append("-v")
                receiver_cmd_args_list.append("-v")
            sender_cmd_args_list.append("--hierarchy")
            receiver_cmd_args_list.append("--hierarchy")
            sender_cmd_args_list.append("child")
            receiver_cmd_args_list.append("child")
            if(args.name == "tom"):
                sender_cmd_args_list.append(args.gid + "conn1")
                receiver_cmd_args_list.append(args.gid + "conn2")
            else:
                sender_cmd_args_list.append(args.gid + "conn2")
                receiver_cmd_args_list.append(args.gid + "conn1")

            #if os.name != "nt":
            sender_cmd_args_list = " ".join(sender_cmd_args_list)
            receiver_cmd_args_list = " ".join(receiver_cmd_args_list)

            #print(sender_cmd_args_list)

            sender_proc = subprocess.Popen(sender_cmd_args_list, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sender_stdout_piper_th = threading.Thread(target=stdout_piper_th, daemon=True, args=(["sender_proc", sender_proc]))
            sender_stdout_piper_th.start()
            sender_stderr_piper_th = threading.Thread(target=stderr_piper_th, daemon=True, args=(["sender_proc", sender_proc]))
            sender_stderr_piper_th.start()

            receiver_proc = subprocess.Popen(receiver_cmd_args_list, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            receiver_stdout_piper_th = threading.Thread(target=stdout_piper_th, daemon=True, args=(["recv_proc", receiver_proc]))
            receiver_stdout_piper_th.start()
            receiver_stderr_piper_th = threading.Thread(target=stderr_piper_th, daemon=True, args=(["recv_proc", receiver_proc]))
            receiver_stderr_piper_th.start()

            GlobalVals.sender_proc = sender_proc
            GlobalVals.receiver_proc = receiver_proc

            receiver_proc.wait()
        except KeyboardInterrupt:
            keyboard_interrupt_hundler()
    else: #child
        signaling = create_signaling(args)
        GlobalVals.signaling = signaling
        pc = RTCPeerConnection()
        GlobalVals.pc = pc

        # this feature inner syori is nazo, so not use event loop
        ws_sub_recv_th = threading.Thread(target=ws_sub_receiver, daemon=True)
        ws_sub_recv_th.start()

        flusher_th = threading.Thread(target=stdout_stderr_flusher_th, daemon=True, args=([1]))
        flusher_th.start()

        if args.role == 'send':
            sender.setup_ws_sub_sender_for_sender_server()
            print("This local server is waiting connect request for sending your stream data to remote at " + str(args.send_stream_port) + " port.")
        elif args.role == 'receive':
            print("This local server is waiting connect request for passing stream data from remote to you at " + str(args.recv_stream_port) + " port.")
            receiver_th = threading.Thread(target=receiver.receiver_server, daemon=True)
            receiver_th.start()
        else:
            print("please pass --role {send|receive} option")

        try:
            # run event loop
            loop = asyncio.get_event_loop()
            GlobalVals.loop = loop
            loop.run_until_complete(parallel_by_gather())
        except KeyboardInterrupt:
            #traceback.print_exc()
            keyboard_interrupt_hundler()
        finally:
            loop.run_until_complete(pc.close())
            loop.run_until_complete(signaling.close())

if __name__ == '__main__':
    main()
