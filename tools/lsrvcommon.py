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

class GlobalVals:
    signaling = None
    sub_channel_sig = None

    loop = None
    pc = None
    signaling = None
    colo = None
    sender_proc = None
    receiver_proc = None
    args = None
    ws_protcol_str = "ws"

    sctp_transport_established = False
    send_ws = None
    force_exited = False
    next_sender_handler_id = 0
    remote_stdout_connected = False
    remote_stdin_connected = False
    done_reading = False
    is_received_client_disconnect_request = False


async def consume_signaling(pc, signaling):
    #global force_exited
    #global remote_stdout_connected
    #global remote_stin_connected

    while True:
        try:
            obj = await signaling.receive()

            if isinstance(obj, RTCSessionDescription):
                await pc.setRemoteDescription(obj)

                if obj.type == 'offer':
                    # send answer
                    await pc.setLocalDescription(await pc.createAnswer())
                    await signaling.send(pc.localDescription)
            elif isinstance(obj, str) and GlobalVals.force_exited == False:
                #print("string recievd: " + obj, file=sys.stderr)
                continue
            else:
                print('Exiting', file=sys.stderr)
                break
        except:
            traceback.print_exc()

# app level websocket sending should anytime use this (except join message)
def ws_sender_send_wrapper(msg):
    if GlobalVals.send_ws:
        GlobalVals.send_ws.send(GlobalVals.sub_channel_sig + "_chsig:" + msg)

