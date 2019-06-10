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

sctp_transport_established = False
force_exited = False
channel = None
done_reading = False
ping_recv_finished = False

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

def send_data():
    global done_reading
    global fp
    global ping_recv_finished

    fp_send = fp
    if args.role == 'receive' and ping_recv_finished == False: # first, when not as handller called
        # re-open received file with read previledge
        fp.close()
        fp_send = open(args.filename, 'rb')
        fp = fp_send
        channel.on('bufferedamountlow', send_data)
        ping_recv_finished = True

    while (channel.bufferedAmount <= channel.bufferedAmountLowThreshold) and not done_reading:
        data = fp_send.read(16384)
        channel.send(data)
        if not data:
            done_reading = True

async def run_answer(pc, signaling, filename):
    global channel
    global done_reading

    await signaling.connect()
    await signaling.send("join")

    done_reading = False
    channel = pc.createDataChannel('filexfer2')

    @pc.on('datachannel')
    def on_datachannel(channel):
        global sctp_transport_established
        start = time.time()
        octets = 0
        sctp_transport_established = True

        @channel.on('message')
        async def on_message(message):
            nonlocal octets
            global ping_recv_finished

            if message:
                octets += len(message)
                fp.write(message)
            else:
                elapsed = time.time() - start
                if elapsed == 0:
                    elapsed = 0.001
                print('received %d bytes in %.1f s (%.3f Mbps)' % (
                    octets, elapsed, octets * 8 / elapsed / 1000000))

                print("start pong transfer.")
                #channel.on('open', send_data)
                send_data()
                # say goodbye
                # await signaling.send(None)

    await consume_signaling(pc, signaling)


async def run_offer(pc, signaling, fp):
    global channel

    await signaling.connect()
    await signaling.send("join")

    done_reading = False
    channel = pc.createDataChannel('filexfer1')

    @pc.on('datachannel')
    def on_datachannel(channel):
        global sctp_transport_established
        start = time.time()
        octets = 0
        sctp_transport_established = True
        fp_pong = None

        @channel.on('message')
        async def on_message(message):
            nonlocal octets
            nonlocal fp_pong

            if fp_pong == None:
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

    channel.on('bufferedamountlow', send_data)
    channel.on('open', send_data)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)

# async def exit_due_to_punching_fail():
#     print("hole punching to remote machine failed.")
#     print("exit.")
#     exit()

def ice_establishment_state():
    global force_exited

    while(sctp_transport_established == False and "failed" not in pc.iceConnectionState):
        #print("ice_establishment_state: " + pc.iceConnectionState)
        time.sleep(1)
    #signaling.send("sctp_establish_fail")
    if sctp_transport_established == False:
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
