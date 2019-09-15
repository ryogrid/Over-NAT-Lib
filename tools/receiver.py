# coding: utf-8

import asyncio
import sys
import threading
import time

import websocket
import traceback
import socket

try:
    import lsrvcommon
    from lsrvcommon import GlobalVals
except:
    from . import lsrvcommon
    from .lsrvcommon import GlobalVals

# common
file_transfer_mode = False
queue_lock = threading.Lock()

# receiver
receiver_fifo_q = asyncio.Queue()
server_rcv = None
file_transfer_phase = 0
cur_recv_clientsock = None
is_remote_node_exists_on_my_send_room = False
client_address = None

# app level websocket sending should anytime use this
def ws_sender_recv_wrapper():
    if GlobalVals.send_ws:
        return GlobalVals.send_ws.recv()
    else:
        return None

async def run_answer(pc, signaling):
    await signaling.connect()

    @pc.on('datachannel')
    def on_datachannel(channel):
        global sctp_transport_established
        start = time.time()
        #octets = 0
        sctp_transport_established = True
        print("datachannel established")
        sys.stdout.flush()
        is_checked_filetransfer = False
        fp = None
        file_transfer_filename = None

        @channel.on('message')
        async def on_message(message):
            global file_transfer_phase
            global file_transfer_mode
            global receiver_fifo_q
            global queue_lock
            global sender_recv_bytes_from_client
            nonlocal is_checked_filetransfer
            nonlocal fp
            nonlocal file_transfer_filename

            print("message event fired", file=sys.stderr)
            print("message received from datachannel: " + str(len(message)), file=sys.stderr)

            if is_checked_filetransfer == False:
                decoded_str = None
                if message != None and len(message) == 2:
                    try:
                        decoded_str = message.decode()
                    except:
                        is_checked_filetransfer = True

                    if decoded_str != None and decoded_str == "sf":
                        #await receiver_fifo_q.put(message)
                        file_transfer_phase = 1
                        return
                    else:
                        is_checked_filetransfer = True

                if file_transfer_phase == 1:
                    #await receiver_fifo_q.put(message)
                    try:
                        decoded_str = message.decode()
                        print("filename bytes: " + decoded_str)
                        file_transfer_phase = 2
                        return
                    except:
                        traceback.print_exc()

                if file_transfer_phase == 2:
                    try:
                        print(message.decode())
                        file_transfer_filename = message.decode()
                        fp = open(file_transfer_filename, "wb")
                    except:
                        traceback.print_exc()
                    file_transfer_mode = True
                    is_checked_filetransfer = True
                    file_transfer_phase = 0
                    return

            if file_transfer_mode == True:
                try:
                    if len(message) > 0:
                        if len(message) == 8 and message.decode() == "finished":
                            fp.flush()
                            fp.close()
                            fp = None
                            is_checked_filetransfer = False
                            file_transfer_phase = 0
                            file_transfer_mode = False
                            return
                        else:
                            print("write " + str(len(message)) + " bytes to " + file_transfer_filename)
                            fp.write(message)
                except:
                    traceback.print_exc()
            else:
                try:
                    if len(message) > 0:
                        if len(message) == 8 and message.decode() == "finished":
                            is_checked_filetransfer = False
                            file_transfer_phase = 0
                            file_transfer_mode = False
                            print("put data to queue: " + str(len(message)))
                            queue_lock.acquire()
                            await receiver_fifo_q.put(message)
                            return
                        else:
                            print("put data to queue: " + str(len(message)))
                            queue_lock.acquire()
                            await receiver_fifo_q.put(message)
                except:
                    traceback.print_exc()
                    lsrvcommon.ws_sender_send_wrapper("receiver_disconnected")
                    # say goodbye
                    #await signaling.send(Nne)
                finally:
                    queue_lock.release()

    await signaling.send("join")
    await lsrvcommon.consume_signaling(pc, signaling)

async def receiver_server_handler(clientsock):
    global receiver_fifo_q
    global is_remote_node_exists_on_my_send_room
    global cur_recv_clientsock

    this_sender_handler_id = GlobalVals.next_sender_handler_id
    this_sender_handler_id_str = str(this_sender_handler_id)
    GlobalVals.next_sender_handler_id += 1

    print("new receiver server_handler wake up [" + this_sender_handler_id_str + "]")
    # clear queue for avoiding read left data on queue
    queue_lock.acquire()
    receiver_fifo_q = asyncio.Queue()
    queue_lock.release()
    is_already_send_receiver_connected = False

    while True:
        try:
            while is_remote_node_exists_on_my_send_room == False:
                GlobalVals.send_ws = websocket.create_connection(
                    GlobalVals.ws_protcol_str + "://" + GlobalVals.args.signaling_host + ":" + str(GlobalVals.args.signaling_port) + "/")
                GlobalVals.sub_channel_sig = GlobalVals.args.gid + "rtos"
                lsrvcommon.ws_sender_send_wrapper("joined_members_sub")

                message = ws_sender_recv_wrapper()
                #print("response of joined_members_sub: " + message)
                splited = message.split(":")
                member_num = int(splited[1])
                if member_num >= 1:
                    is_remote_node_exists_on_my_send_room = True
                    lsrvcommon.ws_sender_send_wrapper("join")
                    #ws_sender_send_wrapper("receiver_connected")
                    #print("new client connected")
                else:
                    GlobalVals.send_ws.close()
                    GlobalVals.send_ws = None
                    await asyncio.sleep(3)

            if is_already_send_receiver_connected == False:
                lsrvcommon.ws_sender_send_wrapper("receiver_connected")
                is_already_send_receiver_connected = True

            data = None
            is_empty = False
            try:
                queue_lock.acquire()
                is_empty = receiver_fifo_q.empty()
                print("queue is empty? at receiver_server_handler [" + this_sender_handler_id_str + "]: " + str(is_empty), file=sys.stderr)
                if is_empty != True:
                    data = await receiver_fifo_q.get()
                    print("got get data from queue[" + this_sender_handler_id_str + "]", file=sys.stderr)
            except:
                traceback.print_exc()
                #break
                return
            finally:
                queue_lock.release()

            if is_empty == False:
                await asyncio.sleep(1)

            if data:
                print("send_data [" + this_sender_handler_id_str + "]: " + str(len(data)))
                if len(data) == 8: # maybe "finished message"
                    decoded_str = ""
                    try:
                        decoded_str = data.decode()
                    except:
                        pass

                    if decoded_str == "finished":
                        clientsock.close()
                        return

                clientsock.sendall(data)
            await asyncio.sleep(0.01)
        except:
            print(type(clientsock))
            print(clientsock)
            traceback.print_exc()
            print("client disconnected.[" + this_sender_handler_id_str + "]")

# use global variable
def async_coloutin_loop_run__for_sock_th(clientsock):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(receiver_server_handler(clientsock))

def receiver_server():
    global server_rcv
    global cur_recv_clientsock

    server_rcv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_rcv.bind(("127.0.0.1", GlobalVals.args.recv_stream_port))
    server_rcv.listen()

    while True:
        if cur_recv_clientsock == None:
            print('Local server reader port waiting for client connections...')
        clientsock, client_address = server_rcv.accept()
        print("new client accepted.")

        # though there is already communicating client, accept new client
        if cur_recv_clientsock == None:
            print("new client connected.")
        else:
            print("already client exist.")
            print("disconnect old connection.")
            try:
                cur_recv_clientsock.close()
            except:
                traceback.print_exc()
        cur_recv_clientsock = clientsock

        thread = threading.Thread(target=async_coloutin_loop_run__for_sock_th, daemon=True, args=([clientsock]))
        thread.start()
