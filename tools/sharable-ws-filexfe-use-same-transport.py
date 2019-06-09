# coding: utf-8

import argparse
import asyncio
import logging
import time
import threading
import sys

# optional, for better performance
try:
    import uvloop
except ImportError:
    uvloop = None

import sys
import os
from os import path
#sys.path.append(path.dirname(path.abspath(__file__)) + "/../../")

from aiortcdc import RTCPeerConnection, RTCSessionDescription
#from aiortcdc.contrib.signaling_share_ws import add_signaling_arguments, create_signaling
from signaling_share_ws import add_signaling_arguments, create_signaling

force_exited = False
ocrtets = 0
read_fp = None
write_fp = None
loop = None

async def consume_signaling(pc, signaling):
    global force_exited
    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == 'offer':
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, str) and force_exited == False:
            pass
            #print("string recievd: " + obj)
        else:
            print('Exiting')
            break

def wrrite_file(message):
    global octets

    if message:
        octets += len(message)
        fp.write(message)
    else:
        elapsed = time.time() - start
        if elapsed == 0:
            elapsed = 0.001
        print('received %d bytes in %.1f s (%.3f Mbps)' % (
            octets, elapsed, octets * 8 / elapsed / 1000000))

def communicate_start(channel):
    global write_fp
    global read_fp
    # relay channel -> tap
    print("communicate start")
    channel.on('message')(write_fp.write)

    def file_reader(*args):
        global read_fp
        nonlocal channel
        print("called file_reader")
        data = read_fp.read(16384)
        if data:
            channel.send(data)
        else:
            print("all data readed.")

    # trans_loop = None
    # #loop = asyncio.get_event_loop()
    # if sys.platform == 'win32':
    #     trans_loop = asyncio.ProactorEventLoop()
    # else:
    #     trans_loop = asyncio.new_event_loop()
    trans_loog = asysncio.get_event_loop()
    trans_loop.add_reader(read_fp, file_reader)
    #trans_loop.run_forever()

async def run_answer(pc, signaling):
    await signaling.connect()
    await signaling.send("join")

    @pc.on('datachannel')
    def on_datachannel(channel):
        #channel_log(channel, '-', 'created by remote party')
        if channel.label == 'filexfer':
            communicate_start(channel)

    await consume_signaling(pc, signaling)


async def run_offer(pc, signaling):
    await signaling.connect()
    await signaling.send("join")

    channel = pc.createDataChannel('filexfer')
    #channel_log(channel, '-', 'created by local party')

    @channel.on('open')
    def on_open():
        communicate_start(channel)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)

# async def run_answer(pc, signaling, filename):
#     await signaling.connect()
#
#     @pc.on('datachannel')
#     def on_datachannel(channel):
#         global sctp_transport_established
#         start = time.time()
#         octets = 0
#         sctp_transport_established = True
#
#         @channel.on('message')
#         async def on_message(message):
#             nonlocal octets
#
#             if message:
#                 octets += len(message)
#                 fp.write(message)
#             else:
#                 elapsed = time.time() - start
#                 if elapsed == 0:
#                     elapsed = 0.001
#                 print('received %d bytes in %.1f s (%.3f Mbps)' % (
#                     octets, elapsed, octets * 8 / elapsed / 1000000))
#
#                 # say goodbye
#                 await signaling.send(None)
#
#     await signaling.send("join")
#     await consume_signaling(pc, signaling)
#
#
# async def run_offer(pc, signaling, fp):
#     await signaling.connect()
#     await signaling.send("join")
#
#     done_reading = False
#     channel = pc.createDataChannel('filexfer')
#
#     def send_data():
#         nonlocal done_reading
#         global sctp_transport_established
#
#         sctp_transport_established = True
#
#         while (channel.bufferedAmount <= channel.bufferedAmountLowThreshold) and not done_reading:
#             data = fp.read(16384)
#             channel.send(data)
#             if not data:
#                 done_reading = True
#
#     channel.on('bufferedamountlow', send_data)
#     channel.on('open', send_data)
#
#     # send offer
#     await pc.setLocalDescription(await pc.createOffer())
#     await signaling.send(pc.localDescription)
#
#     await consume_signaling(pc, signaling)

# async def exit_due_to_punching_fail():
#     print("hole punching to remote machine failed.")
#     print("exit.")
#     exit()

def ice_establishment_state():
    global force_exited
    while "failed" not in pc.iceConnectionState :
        print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(3)
    #signaling.send("sctp_establish_fail")
    if "failed" in pc.iceConnectionState:
        print("hole punching to remote machine failed.")
        force_exited = True
        try:
            loop.stop()
            loop.close()
        except:
            pass
        print("exit.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data channel file transfer')
    parser.add_argument('gid')
    parser.add_argument('role', choices=['send', 'receive'])
    parser.add_argument('filename')
    parser.add_argument('--verbose', '-v', action='count')
    add_signaling_arguments(parser)
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if uvloop is not None:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    signaling = create_signaling(args)
    pc = RTCPeerConnection()

    ice_state_th = threading.Thread(target=ice_establishment_state)
    ice_state_th.start()

    if args.role == 'send':
        read_fp = open(args.filename, 'rb')
        write_fp = open(args.filename + ".rsv", 'wb')
        coro = run_offer(pc, signaling)
    else:
        read_fp = open(args.filename, 'rb')
        write_fp = open(args.filename + ".rsv", 'wb')
        coro = run_answer(pc, signaling)

    try:
        loop = asyncio.get_event_loop()
        # if sys.platform == 'win32':
        #     loop = asyncio.ProactorEventLoop()
        # else:
        #     # run event loop
        #     loop = asyncio.get_event_loop()

        try:
            loop.run_until_complete(coro)
        except KeyboardInterrupt:
            pass
        finally:
            fp.close()
            loop.run_until_complete(pc.close())
            loop.run_until_complete(signaling.close())
    except:
        pass
