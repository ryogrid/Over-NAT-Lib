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

sctp_transport_established = False
force_exited = False

remote_stdout_connected = False
remote_stdout_connected = False
rw_buf = None
signaling = None
clientsock = None

async def consume_signaling(pc, signaling):
    global force_exited
    global remote_stdout_connected
    global remote_stin_connected

    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == 'offer':
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, str) and force_exited == False:
            print("string recievd: " + obj, file=sys.stderr)
            if "receiver_connected" in obj:
                remote_stdout_connected = True
                continue
            elif "receiver_disconnected" in obj:
                remote_stdout_connected = False
                continue
            if "sender_connected" in obj:
                remote_stdin_connected = True
                continue
            elif "sender_disconnected" in obj:
                remote_stdin_connected = False
                clientsock.close()
                continue
        else:
            print('Exiting', file=sys.stderr)
            break


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
                fp.write(message)
            else:
                elapsed = time.time() - start
                if elapsed == 0:
                    elapsed = 0.001
                print('received %d bytes in %.1f s (%.3f Mbps)' % (
                    octets, elapsed, octets * 8 / elapsed / 1000000), file=sys.stderr)

                # say goodbye
                await signaling.send(None)

    await signaling.send("join")
    await consume_signaling(pc, signaling)


async def run_offer(pc, signaling):
    while True:
        try:
            await signaling.connect()
            await signaling.send("joined_members")
            cur_num_str = await signaling.receive()
            print("cur_num_str: " + cur_num_str, file=sys.stderr)
            if "ignoalable error" in cur_num_str:
                pass
            elif cur_num_str != "0":
                await asyncio.sleep(2)
                break

            print("wait join of receiver", file=sys.stderr)
            await asyncio.sleep(1)
        except Exception as e:
            print(e, file=sys.stderr)
    await signaling.connect()
    await signaling.send("join")

    done_reading = False
    channel = pc.createDataChannel('filexfer')

    def send_data():
        nonlocal done_reading
        global sctp_transport_established

        sctp_transport_established = True

        while (channel.bufferedAmount <= channel.bufferedAmountLowThreshold) and not done_reading:
            data = rw_buf.read(1024)
            channel.send(data)
            if not data:
                done_reading = True

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

def getInMemoryBufferedRWPair():
    buf_size = 1024 * 1024 * 10
    read_buf = [0] * buf_size
    write_buf = [0] * buf_size
    return BufferedRWPair(BufferedReader(BytesIO(read_buf), buf_size), BufferedWriter(BytesIO(write_buf)), buf_size)

def work_as_parent():
    pass

def sender_server():
    global rw_buf

    #if not args.target:
    #    args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 10100))
    server.listen()

    rw_buf = getInMemoryBufferedRWPair()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()

            # wait remote server is connected with some program
            while remote_stdout_connected == False:
                time.sleep(1)

            while True:
                try:
                    rcvmsg = clientsock.recv(1024)
                except Exception as e:
                    print(e,  file=sys.stderr)
                    print("maybe client disconnect")
                    signaling.send("sender_disconnected")


                #print('Received -> %s' % (rcvmsg))
                if rcvmsg == None or len(rcvmsg) == 0:
                  break
                else:
                    rw_buf.write(rcvmsg)
        except Exception as e:
            print(e, file=sys.stderr)

    clientsock.close()

def receiver_server():
    global rw_buf

    #if not args.target:
    #    args.target = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 10200))
    server.listen()

    rw_buf = getInMemoryBufferedRWPair()

    print('Waiting for connections...', file=sys.stderr)
    while True:
        try:
            clientsock, client_address = server.accept()

            # wait remote server is connected with some program
            while remote_stdout_connected == False:
                time.sleep(1)

            while True:
                try:
                    rcvmsg = rw_buf.read(1024)
                except Exception as e:
                    print(e,  file=sys.stderr)

                #print('Received -> %s' % (rcvmsg))
                if rcvmsg == None or len(rcvmsg) == 0:
                  break
                else:
                    clientsock.sendall(rcvmsg)
        except Exception as e:
            print(e, file=sys.stderr)

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

        if args.role == 'send':
            #fp = open(args.filename, 'rb')
            sender_th = threading.Thread(target=sender_server())
            sender_th.start()
            coro = run_offer(pc, signaling)
        else:
            #fp = open(args.filename, 'wb')
            receiver_th = threading.Thread(target=receiver_server())
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
