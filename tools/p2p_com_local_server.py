# coding: utf-8

import argparse
import asyncio
import logging
import socket
import sys
import threading
import time
import queue
import json
#from io import BytesIO

from aiortcdc import RTCPeerConnection, RTCSessionDescription

from signaling_share_ws import add_signaling_arguments, create_signaling

# application level ws communication
import websocket
import traceback

sctp_transport_established = False
force_exited = False

#channel_sender = None
remote_stdout_connected = False
remote_stdin_connected = False
fifo_q = queue.Queue()
signaling = None
clientsock = None
client_address = None
send_ws = None
sub_channel_sig = None
is_remote_node_exists_on_my_send_room = False

async def consume_signaling(pc, signaling):
    global force_exited
    global remote_stdout_connected
    global remote_stin_connected

    while True:
        try:
            obj = await signaling.receive()

            if isinstance(obj, RTCSessionDescription):
                await pc.setRemoteDescription(obj)

                if obj.type == 'offer':
                    # send answer
                    await pc.setLocalDescription(await pc.createAnswer())
                    await signaling.send(pc.localDescription)
            elif isinstance(obj, str) and force_exited == False:
                #print("string recievd: " + obj, file=sys.stderr)
                continue
            else:
                print('Exiting', file=sys.stderr)
                break
        except:
            traceback.print_exc()


async def run_answer(pc, signaling):
    await signaling.connect()

    @pc.on('datachannel')
    def on_datachannel(channel):
        global sctp_transport_established
        start = time.time()
        octets = 0
        sctp_transport_established = True
        print("datachannel established")

        @channel.on('message')
        async def on_message(message):
            nonlocal octets
            global clientsock

            try:
                print("message event fired")
                if len(message) > 0:
                    octets += len(message)
                    if clientsock != None:
                        clientsock.sendall(message)
                else:
                    elapsed = time.time() - start
                    if elapsed == 0:
                        elapsed = 0.001
                    print('received %d bytes in %.1f s (%.3f Mbps)' % (
                        octets, elapsed, octets * 8 / elapsed / 1000000), file=sys.stderr)
                    if clientsock != None:
                        clientsock.close()
            except:
                traceback.print_exc()
                if clientsock:
                    clientsock.close()
                ws_sender_send_wrapper("receiver_disconnected")
                # say goodbye
                #await signaling.send(None)

    await signaling.send("join")
    await consume_signaling(pc, signaling)

async def run_offer(pc, signaling):
    while True:
        try:
            await signaling.connect()
            await signaling.send("joined_members")

            cur_num_str = await signaling.receive()
            #print("cur_num_str: " + cur_num_str, file=sys.stderr)
            if "ignoalable error" in cur_num_str:
                pass
            elif cur_num_str != "0":
                await asyncio.sleep(2)
                break

            #print("wait join of receiver", file=sys.stderr)
            await asyncio.sleep(1)
        except:
            traceback.print_exc()
    await signaling.connect()
    await signaling.send("join")

    channel_sender = pc.createDataChannel('filexfer')

    async def send_data_inner():
        nonlocal channel_sender
        global sctp_transport_established
        global fifo_q
        global remote_stdout_connected
        global clientsock

        # this line is needed?
        asyncio.set_event_loop(asyncio.new_event_loop())

        while True:
            sctp_transport_established = True
            while remote_stdout_connected == False:
                print("wait remote_std_connected")
                await asyncio.sleep(1)

            print("start waiting buffer state is OK")
            while channel_sender.bufferedAmount > channel_sender.bufferedAmountLowThreshold:
                print("buffer info of channel: " + str(channel_sender.bufferedAmount) + " > " + str( channel_sender.bufferedAmountLowThreshold))
                await asyncio.sleep(1)

            print("start sending roop")
            while channel_sender.bufferedAmount <= channel_sender.bufferedAmountLowThreshold:
                try:
                    data = None
                    try:
                        print("try get data from queue")
                        data = fifo_q.get(block=True, timeout=5)
                        print("got get data from queue")
                    except queue.Empty:
                        pass

                    # data = fifo_q.getvalue()
                    if data:
                        if type(data) is "str" and data == "finished":
                            print("notify end of transfer")
                            #channel_sender.send(data)
                            ws_sender_send_wrapper("sender_disconnected")
                        else:
                            print("send_data:" + str(len(data)))
                            channel_sender.send(data)

                    if clientsock == None:
                        channel_sender.send(bytes("", encoding="utf-8"))
                        remote_stdout_connected = False
                        break

                    await asyncio.sleep(0.01)
                except:
                    traceback.print_exc()

    async def send_data():
        #send_data_inner_th = threading.Thread(target=send_data_inner)
        #send_data_inner_th.start()
        await send_data_inner()

    #channel_sender.on('bufferedamountlow', send_data)
    channel_sender.on('open', send_data)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)

def ice_establishment_state():
    global force_exited
    while(sctp_transport_established == False and "failed" not in pc.iceConnectionState):
        #print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(1)
    if sctp_transport_established == False:
        print("hole punching to remote machine failed.", file=sys.stderr)
        force_exited = True
        try:
            loop.stop()
            loop.close()
        except:
            pass
        print("exit.")

# app level websocket sending should anytime use this (except join message)
def ws_sender_send_wrapper(msg):
    send_ws.send(sub_channel_sig + "_chsig:" + msg)

# app level websocket sending should anytime use this
def ws_sender_recv_wrapper():
    return send_ws.recv()

def work_as_parent():
    pass

def sender_server():
    global fifo_q
    global clientsock

    asyncio.set_event_loop(asyncio.new_event_loop())

    #if not args.target:
    #    args.target = '0.0.0.0'
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 10100))
        server.listen()
    except:
        traceback.print_exc()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()
            print("new client connected.")

            # wait remote server is connected with some program
            while remote_stdout_connected == False:
                print("wait remote_stdout_connected", file=sys.stderr)
                time.sleep(1)

            while True:
                rcvmsg = None
                try:
                    rcvmsg = clientsock.recv(2048)
                    print("received message from client")
                    print(len(rcvmsg))
                except:
                    traceback.print_exc()
                    print("maybe client disconnect")
                    if clientsock:
                        clientsock.close()
                        clientsock = None
                    ws_sender_send_wrapper("sender_disconnected")

                #print("len of recvmsg:" + str(len(recvmsg)))
                if rcvmsg == None or len(rcvmsg) == 0:
                    print("break")
                    fifo_q.put("finished")
                    break
                else:
                    print("fifo_q.write(rcvmsg)")
                    fifo_q.put(rcvmsg)
                time.sleep(0.01)
            #send_data()
        except:
            traceback.print_exc()
            if clientsock:
                clientsock.close()
                clientsock = None
            # except Exception as e:
        #     print(e, file=sys.stderr)

def receiver_server():
    global fifo_q
    global clientsock, client_address
    global is_remote_node_exists_on_my_send_room

    #if not args.target:
    #    args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 10200))
    server.listen()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()
            print("new client connected.", file=sys.stderr)
            # wait until remote node join to my send room
            while is_remote_node_exists_on_my_send_room == False:
                ws_sender_send_wrapper("joined_members_sub")
                message = ws_sender_recv_wrapper()
                splited = message.split(":")
                member_num = int(splited[1])
                if member_num >= 2:
                    is_remote_node_exists_on_my_send_room = True
                time.sleep(3)
            ws_sender_send_wrapper("receiver_connected")
        #     while True:
        #         try:
        #             rcvmsg = fifo_q.read(1024)
        #         except Exception as e:
        #             print(e,  file=sys.stderr)
        #
        #         #print('Received -> %s' % (rcvmsg))
        #         if rcvmsg == None or len(rcvmsg) == 0:
        #           break
        #         else:
        #             clientsock.sendall(rcvmsg)
        except:
            traceback.print_exc()
            ws_sender_send_wrapper("receiver_disconnected")
            #print(e, file=sys.stderr)

def send_keep_alive():
    #logging.basicConfig(level=logging.FATAL)
    while True:
        ws_sender_send_wrapper("keepalive")
        time.sleep(5)

def setup_ws_sub_sender():
    global send_ws
    global sub_channel_sig
    send_ws = websocket.create_connection("ws://" + args.signaling_host + ":" + str(args.signaling_port) + "/")
    print("sender app level ws opend")
    if args.role == 'send':
        sub_channel_sig = args.gid + "stor"
    else:
        sub_channel_sig = args.gid + "rtos"
    ws_sender_send_wrapper("join")

    ws_keep_alive_th = threading.Thread(target=send_keep_alive)
    ws_keep_alive_th.start()

# def ws_sub_receiver():
#     global remote_stdout_connected
#     global remote_stdin_connected
#     global done_reading
#     global clientsock
#     global is_remote_node_exists_on_my_send_room
#
#     ws = websocket.create_connection("ws://" + args.signaling_host + ":" + str(args.signaling_port) + "/")
#     print("receiver app level ws opend")
#     try:
#         if args.role == 'send':
#             ws.send(args.gid + "rtos_chsig:join")
#         else:
#             ws.send(args.gid + "stor_chsig:join")
#     except:
#         traceback.print_exc()
#
#     while True:
#         message = ws.recv()
#         print("recieved message as ws_sub_receiver")
#         print(message)
#
#         if "receiver_connected" in message:
#             print("receiver_connected")
#             #print(fifo_q.getbuffer().nbytes)
#             remote_stdout_connected = True
#             # if fifo_q.getbuffer().nbytes != 0:
#             #     send_data()
#         elif "receiver_disconnected" in message:
#             remote_stdout_connected = False
#             done_reading = False
#         elif "sender_connected" in message:
#             remote_stdin_connected = True
#         elif "sender_disconnected" in message:
#             remote_stdin_connected = False
#             if clientsock:
#                 clientsock.close()
#                 clientsock = None
#         elif "member_count" in message: # respons of joined_members_sub
#             splited = message.split(":")
#             member_num = int(splited[1])
#             if member_num >= 2:
#                 is_remote_node_exists_on_my_send_room = True

def ws_sub_receiver():
    def on_message(ws, message):
        global remote_stdout_connected
        global remote_stdin_connected
        global done_reading
        global clientsock
        global is_remote_node_exists_on_my_send_room

        #print(message,  file=sys.stderr)
        print("called on_message")
        print(message)

        if "receiver_connected" in message:
            print("receiver_connected")
            #print(fifo_q.getbuffer().nbytes)
            remote_stdout_connected = True
            # if fifo_q.getbuffer().nbytes != 0:
            #     send_data()
        elif "receiver_disconnected" in message:
            remote_stdout_connected = False
            done_reading = False
        elif "sender_connected" in message:
            remote_stdin_connected = True
        elif "sender_disconnected" in message:
            print("sender_disconnected")
            remote_stdin_connected = False
            if clientsock:
                time.sleep(5)
                print("disconnect clientsock")
                clientsock.close()
                clientsock = None
        # elif "member_count" in message: # respons of joined_members_sub
        #     splited = message.split(":")
        #     member_num = int(splited[1])
        #     if member_num >= 2:
        #         is_remote_node_exists_on_my_send_room = True

    def on_error(ws, error):
        print(error)

    def on_close(ws):
        print("### closed ###")

    def on_open(ws):
        print("receiver app level ws opend")
        try:
            if args.role == 'send':
                ws.send(args.gid + "rtos_chsig:join")
            else:
                ws.send(args.gid + "stor_chsig:join")
        except:
            traceback.print_exc()

    #logging.basicConfig(level=logging.DEBUG)
    #websocket.enableTrace(True)
    ws = websocket.WebSocketApp("ws://" + args.signaling_host + ":" + str(args.signaling_port) + "/",
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
    ws.on_open = on_open
    ws.run_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data channel file transfer')
    parser.add_argument('hierarchy', choices=['parent', 'child'])
    parser.add_argument('gid')
    #parser.add_argument('filename')
    parser.add_argument('--role', choices=['send', 'receive'])
    parser.add_argument('--verbose', '-v', action='count')
    add_signaling_arguments(parser)
    args = parser.parse_args()

    colo = None
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    #logging.basicConfig(level=logging.FATAL)

    if args.hierarchy == 'parent':
        colo = work_as_parent()
    else:
        signaling = create_signaling(args)
        pc = RTCPeerConnection()

        ice_state_th = threading.Thread(target=ice_establishment_state)
        ice_state_th.start()

        setup_ws_sub_sender()
        ws_sub_recv_th = threading.Thread(target=ws_sub_receiver)
        ws_sub_recv_th.start()

        if args.role == 'send':
            #fp = open(args.filename, 'rb')
            sender_th = threading.Thread(target=sender_server)
            sender_th.start()
            coro = run_offer(pc, signaling)
        else:
            #fp = open(args.filename, 'wb')
            receiver_th = threading.Thread(target=receiver_server)
            receiver_th.start()
            coro = run_answer(pc, signaling)

    loop = None
    try:
        # run event loop
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(coro)
        except:
            traceback.print_exc()
        finally:
            #fp.close()
            loop.run_until_complete(pc.close())
            loop.run_until_complete(signaling.close())
    except:
        traceback.print_exc()
