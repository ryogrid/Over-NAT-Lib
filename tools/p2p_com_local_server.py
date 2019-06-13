# coding: utf-8

import argparse
import asyncio
import logging
import socket
import sys
import threading
import time
from io import BufferedRWPair, BufferedWriter, BufferedReader, BytesIO

from aiortcdc import RTCPeerConnection, RTCSessionDescription

from signaling_share_ws import add_signaling_arguments, create_signaling

# application level ws communication
import websocket

sctp_transport_established = False
force_exited = False

channel = None
remote_stdout_connected = False
remote_stdin_connected = False
rw_buf = None
signaling = None
clientsock = None
client_address = None
done_reading = False
send_ws = None

async def consume_signaling(pc, signaling):
    global force_exited
    global remote_stdout_connected
    global remote_stin_connected
    global clientsock

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
                print("string recievd: " + obj, file=sys.stderr)
                continue
            else:
                print('Exiting', file=sys.stderr)
                break
        except Exception as e:
            print(e, file=sys.stderr)


async def run_answer(pc, signaling):
    await signaling.connect()

    @pc.on('datachannel')
    def on_datachannel(channel):
        global sctp_transport_established
        start = time.time()
        octets = 0
        sctp_transport_established = True

        @channel.on('message')
        async def on_message(message):
            nonlocal octets

            if message:
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

                # say goodbye
                #await signaling.send(None)

    await signaling.send("join")
    await consume_signaling(pc, signaling)

def send_data():
    global done_reading
    global sctp_transport_established

    sctp_transport_established = True

    while (channel.bufferedAmount <= channel.bufferedAmountLowThreshold) and not done_reading and remote_stdout_connected:
        print("send_data", file=sys.stderr)
        data = rw_buf.read(1024)
        #data = rw_buf.getvalue()
        channel.send(data)
        if not data:
              done_reading = True

async def run_offer(pc, signaling):
    global channel

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
        except Exception as e:
            print(e, file=sys.stderr)
    await signaling.connect()
    await signaling.send("join")

    #done_reading = False
    channel = pc.createDataChannel('filexfer')

    channel.on('bufferedamountlow', send_data)
    channel.on('open', send_data)

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

# def getInMemoryBufferedRWPair():
#     buf_size = 1024 * 1024 * 10
#     read_buf = bytearray(buf_size)
#     write_buf = bytearray(buf_size)
#     return BufferedRWPair(BufferedReader(BytesIO(read_buf), buf_size), BufferedWriter(BytesIO(write_buf)), buf_size)

def work_as_parent():
    pass

def sender_server():
    global rw_buf

    #if not args.target:
    #    args.target = '0.0.0.0'
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 10100))
        server.listen()
        # server.setsockopt(
        #     socket.SOL_SOCKET,
        #     socket.SO_RCVBUF,
        #     1024)
    except Exception as e:
        print(e, file=sys.stderr)

    rw_buf = BytesIO()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()
            print("new client connected.")

            # # wait remote server is connected with some program
            while remote_stdout_connected == False:
                print("wait remote_stdout_connected", file=sys.stderr)
                time.sleep(1)

            while True:
                recvmsg = None
                try:
                    rcvmsg = clientsock.recv(1024)
                    print("received message from client")
                    print(len(rcvmsg))
                except Exception as e:
                    print(e,  file=sys.stderr)
                    print("maybe client disconnect")
                    signaling.send("sender_disconnected")


                #print('Received -> %s' % (rcvmsg))
                if rcvmsg == None or len(rcvmsg) == 0:
                  break
                else:
                    rw_buf.write(rcvmsg)
            send_data()
        except Exception as e:
            print(e, file=sys.stderr)

    clientsock.close()

def receiver_server():
    global rw_buf
    global client_sock, client_address

    #if not args.target:
    #    args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 10200))
    server.listen()

    #rw_buf = getInMemoryBufferedRWPair()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()
            print("new client connected.")

        #     while True:
        #         try:
        #             rcvmsg = rw_buf.read(1024)
        #         except Exception as e:
        #             print(e,  file=sys.stderr)
        #
        #         #print('Received -> %s' % (rcvmsg))
        #         if rcvmsg == None or len(rcvmsg) == 0:
        #           break
        #         else:
        #             clientsock.sendall(rcvmsg)
        except Exception as e:
             print(e, file=sys.stderr)

def ws_send_wrapper(msg):
    if args.role == 'send':
        send_ws.send(args.gid + "stor" + "_chsig:" + msg)
    else:
        send_ws.send(args.gid + "rtos" + "_chsig:" + msg)

def send_keep_alive():
    while True:
        ws_send_wrapper(send_ws, "keepalive")
        time.sleep(5)

def setup_ws_sub_sender():
    global send_ws
    send_ws = websocket.create_connection("ws://" + args.signalng_host + ":" + str(args.signaling_port) + "/")
    ws_send_wrapper("join")

    ws_keep_alive_th = threading.Thread(target=send_keep_alive)
    ws_keep_alive_th.start()

def ws_sub_receiver():
    def on_message(ws, message):
        global remote_stdout_connected
        global remote_stdin_connected
        global done_reading

        print(message,  file=sys.stderr)

        if "receiver_connected" in message:
            remote_stdout_connected = True
            if rw_buf.getbuffer().nbytes != 0:
                send_data()
        elif "receiver_disconnected" in message:
            remote_stdout_connected = False
            done_reading = False
        elif "sender_connected" in message:
            remote_stdin_connected = True
        elif "sender_disconnected" in message:
            remote_stdin_connected = False
            clientsock.close()

    def on_error(ws, error):
        print(error)

    def on_close(ws):
        print("### closed ###")

    def on_open(ws):
        print("receiver app level ws opend")
        if args.role == 'send':
            ws.send(args.gid + "stor" + "_chsig:join")
        else:
            ws.send(args.gid + "rtos" + "_chsig:join")

    websocket.enableTrace(True)
    ws = websocket.WebSocketApp("ws://" + args.signalng_host + ":" + str(args.signaling_port) + "/",
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

    if args.hierarchy == 'parent':
        colo = work_as_parent()
    else:
        signaling = create_signaling(args)
        pc = RTCPeerConnection()

        ice_state_th = threading.Thread(target=ice_establishment_state)
        ice_state_th.start()

        setup_ws_sub_sender()
        send_ws_th = threading.Thread(target=ws_sub_receiver)
        send_ws_th.start()

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

    try:
        # run event loop
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(coro)
        except KeyboardInterrupt:
            pass
        finally:
            #fp.close()
            loop.run_until_complete(pc.close())
            loop.run_until_complete(signaling.close())
    except:
        pass
