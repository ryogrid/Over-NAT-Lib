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
fp = None

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
            print("string recievd: " + obj)
        else:
            print('Exiting')
            break

async def run_answer(pc, signaling, filename):
    await signaling.connect()
    await signaling.send("join")

    done_reading = False
    channel = pc.createDataChannel('filexfer2')
    is_first = True
    fp_read = None

    def send_data():
        nonlocal done_reading
        nonlocal is_first
        nonlocal fp_read

        if is_first:
            # re-open received file with read previledge
            fp.close()
            fp_read = open(args.filename, 'rb')
            print("start transfer.")
        elif is_fist: # first called
            is_first = True
            fp_read = fp
            print("start transfer.")

        while (channel.bufferedAmount <= channel.bufferedAmountLowThreshold) and not done_reading:
            data = fp_read.read(16384)
            channel.send(data)
            if not data:
                done_reading = True

    @pc.on('datachannel')
    def on_datachannel(channel):
        global channel_recv
        start = time.time()
        octets = 0
        printf("established transport to me. then start establish from me.")
        # channel_recv.on('bufferedamountlow', send_data)
        # channel_recv.on('open', send_data)

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
                    octets, elapsed, octets * 8 / elapsed / 1000000))

    await consume_signaling(pc, signaling)


async def run_offer(pc, signaling, fp):
    global channel_send

    await signaling.connect()
    await signaling.send("join")

    done_reading = False
    channel_send = pc.createDataChannel('filexfer1')

    @pc.on('datachannel')
    def on_datachannel(channel):
        start = time.time()
        octets = 0

        @channel.on('message')
        async def on_message(message):
            nonlocal octets

            fp_pong = open(args.filename + ".pong", 'wb')
            if message:
                octets += len(message)
                fp_pong.write(message)
            else:
                elapsed = time.time() - start
                if elapsed == 0:
                    elapsed = 0.001
                print('received %d bytes in %.1f s (%.3f Mbps)' % (
                    octets, elapsed, octets * 8 / elapsed / 1000000))

                # say goodbye
                await signaling.send(None)

    channel_send.on('bufferedamountlow', send_data)
    channel_send.on('open', send_data)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)

def force_exit():
    global force_exited
    global loop

    print("hole punching to remote machine failed.")
    force_exited = True
    try:
        loop.stop()
        loop.close()
    except:
        pass
    print("exit.")

# def establish_pc_from_receiver():
#     global channel
#
#     channel = pc.createDataChannel('filexfer2')
#     channel.on('bufferedamountlow', send_data)
#     channel.on('open', send_data)

def ice_establishment_state():
    global args
    global pc

    while "completed" not in pc.iceConnectionState and "failed" not in pc.iceConnectionState:
        print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(1)
    #signaling.send("sctp_establish_fail")
    if "failed" in pc.iceConnectionState:
        force_exit()
    else:
        pass
        if args.role == 'receive':
            establish_pc_from_receiver()

    while "new" not in pc.iceConnectionState:
        print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(1)
    
    while "completed" not in pc.iceConnectionState and "failed" not in pc.iceConnectionState:
        print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(1)
    if "failed" in pc.iceConnectionState:
        force_exit()

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
        fp = open(args.filename, 'rb')
        coro = run_offer(pc, signaling, fp)
    else:
        fp = open(args.filename, 'wb')
        coro = run_answer(pc, signaling, fp)

    try:
        # run event loop
        loop = asyncio.get_event_loop()
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
