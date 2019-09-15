# coding: utf-8

import sys
from aiortcdc import RTCSessionDescription
import traceback

class GlobalVals:
    # -----parent-----
    sender_proc = None
    receiver_proc = None

    # -----common (sender, receiver)-----
    signaling = None
    sub_channel_sig = None
    pc = None
    args = None
    ws_protcol_str = "ws"
    send_ws = None
    force_exited = False
    next_sender_handler_id = 0

    # -----sender-----
    sctp_transport_established = False

    # -----receiver-----
    remote_stdout_connected = False

    # below has write access but does not have read access
    is_received_client_disconnect_request = False
    done_reading = False
    remote_stdin_connected = False

async def consume_signaling(pc, signaling):
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

