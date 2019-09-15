# coding: utf-8

import asyncio
import sys
import threading
import websocket
import traceback

try:
    import lsrvcommon
    from lsrvcommon import GlobalVals
except:
    from . import lsrvcommon
    from .lsrvcommon import GlobalVals

# common
file_transfer_mode = False
queue_lock = threading.Lock()

# sender
sender_fifo_q = asyncio.Queue()
server_send = None
# except header data
sender_recv_bytes_from_client = 0
sender_client_eof_or_disconnected = False

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
            else:
                await signaling.close()

            print("wait join of receiver", file=sys.stderr)
            await asyncio.sleep(1)
        except:
            traceback.print_exc()
    await signaling.connect()
    await signaling.send("join")

    channel_sender = pc.createDataChannel('filexfer')

    async def send_data_inner():
        nonlocal channel_sender
        #global sctp_transport_established
        global sender_fifo_q
        global file_transfer_mode
        global queue_lock
        global sender_recv_bytes_from_client
        global sender_client_eof_or_disconnected

        # this line is needed?
        asyncio.set_event_loop(asyncio.new_event_loop())
        sent_bytes = 0

        while True:
            GlobalVals.sctp_transport_established = True
            while GlobalVals.remote_stdout_connected == False and file_transfer_mode == False:
                print("wait remote_stdout_connected", file=sys.stderr)
                await asyncio.sleep(1)

            print("start waiting buffer state is OK", file=sys.stderr)
            while channel_sender.bufferedAmount > channel_sender.bufferedAmountLowThreshold:
                #print("buffer info of channel: " + str(channel_sender.bufferedAmount) + " > " + str( channel_sender.bufferedAmountLowThreshold))
                await asyncio.sleep(1)

            print("start sending roop", file=sys.stderr)
            while channel_sender.bufferedAmount <= channel_sender.bufferedAmountLowThreshold:
                try:
                    data = None
                    is_empty = False
                    try:
                        queue_lock.acquire()
                        is_empty = sender_fifo_q.empty()
                        print("queue is empty? at send_data_inner: " + str(is_empty), file=sys.stderr)
                        if is_empty != True:
                            #print("queue object id" + str(id(sender_fifo_q)))
                            data = await sender_fifo_q.get()
                    except:
                        traceback.print_exc()
                    finally:
                        queue_lock.release()

                    if is_empty == True:
                         await asyncio.sleep(1)
                         continue

                    if data:
                        # if not current client puted data, do ignore
                        if data[0] != (GlobalVals.next_sender_handler_id - 1):
                            continue

                        sent_bytes += len(data[1])
                        print("send_data: " + str(len(data[1])))
                        sys.stdout.flush()
                        channel_sender.send(data[1])

                        # sender_server_handler received data from client are all sent
                        if sent_bytes == sender_recv_bytes_from_client and sender_client_eof_or_disconnected:
                            print("notify end of transfer")
                            channel_sender.send("finished".encode())
                            file_transfer_mode = False
                            sent_bytes = 0
                            sender_recv_bytes_from_client = 0
                            sender_client_eof_or_disconnected = False
                            GlobalVals.remote_stdout_connected = False
                            queue_lock.acquire()
                            sender_fifo_q = asyncio.Queue()
                            queue_lock.release()

                    await asyncio.sleep(0.01)
                except:
                    traceback.print_exc()

    async def send_data():
        print("datachannel established")
        sys.stdout.flush()
        await send_data_inner()

    #channel_sender.on('bufferedamountlow', send_data)
    channel_sender.on('open', send_data)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await lsrvcommon.consume_signaling(pc, signaling)

async def comm_type_check_of_client_head_data(byte_buf, reader, this_sender_handler_id):
    global sender_fifo_q
    global file_transfer_mode
    global queue_lock
    global sender_recv_bytes_from_client

    try:
        # wait remote server is connected with some program
        ret_buf = byte_buf
        head_2byte = b''
        is_checked_filetransfer = False

        while GlobalVals.remote_stdout_connected == False and file_transfer_mode == False:
            print("wait remote_stdout_connected", file=sys.stderr)
            if is_checked_filetransfer == False:
                rcvmsg = await reader.read(1)
                #print(rcvmsg)
                head_2byte = b''.join([head_2byte, rcvmsg])
                try:
                    if len(head_2byte) == 1:
                        if head_2byte.decode() == "s":
                            #print("first byte is *s*")
                            #sys.stdout.flush()
                            continue
                        else:
                            #print("not s")
                            #sys.stdout.flush()
                            is_checked_filetransfer = True
                except:
                    pass

                decoded_str = None
                if rcvmsg != None and len(head_2byte) == 2:
                    try:
                        decoded_str = head_2byte.decode()
                    except:
                        pass
                    if decoded_str == "sf":
                        try:
                            print("file transfer mode [" + str(this_sender_handler_id) + "]")
                            queue_lock.acquire()
                            await sender_fifo_q.put([this_sender_handler_id, head_2byte])
                            rcvmsg = await reader.read(3)
                            filename_bytes = int(rcvmsg.decode())
                            await sender_fifo_q.put([this_sender_handler_id, rcvmsg])
                            print(filename_bytes)
                            rcvmsg = await reader.read(filename_bytes)
                            print(rcvmsg.decode())
                            await sender_fifo_q.put([this_sender_handler_id, rcvmsg])
                            file_transfer_mode = True
                            is_checked_filetransfer = True
                            sender_recv_bytes_from_client += 2 + 3 + filename_bytes
                        except:
                            pass
                        finally:
                            queue_lock.release()
                        continue
                    else:
                        sender_recv_bytes_from_client += len(head_2byte)
                        ret_buf = b''.join([ret_buf, head_2byte])
                        is_checked_filetransfer = True
                else:
                    sender_recv_bytes_from_client += len(head_2byte)
                    ret_buf = b''.join([ret_buf, head_2byte])
                    is_checked_filetransfer = True

            await asyncio.sleep(1)
    except:
        traceback.print_exc()

    return ret_buf



async def sender_server_handler(reader, writer):
    global sender_fifo_q
    global file_transfer_mode
    global queue_lock
    global sender_client_eof_or_disconnected
    global sender_recv_bytes_from_client

    print('Local server writer port waiting for client connections...')

    byte_buf = b''
    #is_checked_filetransfer = False
    rcvmsg = None

    # reset not to send old client wrote data
    queue_lock.acquire()
    sender_fifo_q = asyncio.Queue()
    #await clear_queue(sender_fifo_q)
    queue_lock.release()

    this_sender_handler_id = GlobalVals.next_sender_handler_id
    this_sender_handler_id_str = str(this_sender_handler_id)
    GlobalVals.next_sender_handler_id += 1
    print("new client connected.")
    print("wake up new sender_server_handler [" + str(this_sender_handler_id_str) + "]")

    # check client needed special local server functionality
    # this function read data from socket and set appropriate value to global variables
    byte_buf = await comm_type_check_of_client_head_data(byte_buf, reader, this_sender_handler_id)

    # try:
    #     # wait remote server is connected with some program
    #     head_2byte = b''
    #     while GlobalVals.remote_stdout_connected == False and file_transfer_mode == False:
    #         print("wait remote_stdout_connected", file=sys.stderr)
    #         if is_checked_filetransfer == False:
    #             rcvmsg = await reader.read(1)
    #             #print(rcvmsg)
    #             head_2byte = b''.join([head_2byte, rcvmsg])
    #             try:
    #                 if len(head_2byte) == 1:
    #                     if head_2byte.decode() == "s":
    #                         #print("first byte is *s*")
    #                         #sys.stdout.flush()
    #                         continue
    #                     else:
    #                         #print("not s")
    #                         #sys.stdout.flush()
    #                         is_checked_filetransfer = True
    #             except:
    #                 pass
    #
    #             decoded_str = None
    #             if rcvmsg != None and len(head_2byte) == 2:
    #                 try:
    #                     decoded_str = head_2byte.decode()
    #                 except:
    #                     pass
    #                 if decoded_str == "sf":
    #                     try:
    #                         print("file transfer mode [" + this_sender_handler_id_str + "]")
    #                         queue_lock.acquire()
    #                         await sender_fifo_q.put([this_sender_handler_id, head_2byte])
    #                         rcvmsg = await reader.read(3)
    #                         filename_bytes = int(rcvmsg.decode())
    #                         await sender_fifo_q.put([this_sender_handler_id, rcvmsg])
    #                         print(filename_bytes)
    #                         rcvmsg = await reader.read(filename_bytes)
    #                         print(rcvmsg.decode())
    #                         await sender_fifo_q.put([this_sender_handler_id, rcvmsg])
    #                         file_transfer_mode = True
    #                         is_checked_filetransfer = True
    #                         sender_recv_bytes_from_client += 2 + 3 + filename_bytes
    #                     except:
    #                         pass
    #                     finally:
    #                         queue_lock.release()
    #                     continue
    #                 else:
    #                     sender_recv_bytes_from_client += len(head_2byte)
    #                     byte_buf = b''.join([byte_buf, head_2byte])
    #                     is_checked_filetransfer = True
    #             else:
    #                 sender_recv_bytes_from_client += len(head_2byte)
    #                 byte_buf = b''.join([byte_buf, head_2byte])
    #                 is_checked_filetransfer = True
    #
    #         await asyncio.sleep(1)
    try:
        while True:
            # if flag backed to False, end this handler because it means receiver side client disconnected
            if GlobalVals.remote_stdout_connected == False and file_transfer_mode == False:
                queue_lock.acquire()
                sender_fifo_q = asyncio.Queue()
                queue_lock.release()
                await asyncio.sleep(3)
            try:
                rcvmsg = await reader.read(5120)
                sender_recv_bytes_from_client += len(rcvmsg)

                byte_buf = b''.join([byte_buf, rcvmsg])
                print("received message from client[" + this_sender_handler_id_str + "]", file=sys.stderr)
                print(len(rcvmsg), file=sys.stderr)

                if GlobalVals.args.no_buffering != True:
                    # block sends until bufferd data amount is gleater than 100KB
                    if(len(byte_buf) <= 1024 * 512) and (rcvmsg != None and len(rcvmsg) > 0): #1MB
                        print("current bufferd byteds: " + str(len(byte_buf)), file=sys.stderr)
                        await asyncio.sleep(0.01)
                        continue
            except:
                traceback.print_exc()

            #print("len of recvmsg:" + str(len(recvmsg)))
            if rcvmsg == None or len(rcvmsg) == 0:
                #print(rcvmsg)
                if len(byte_buf) > 0:
                    queue_lock.acquire()
                    await sender_fifo_q.put([this_sender_handler_id, byte_buf])
                    queue_lock.release()
                    byte_buf = b''
                sender_client_eof_or_disconnected = True
                print("reached EOF or client disconnection [" + this_sender_handler_id_str + "]")
                return
            else:
                print("put bufferd bytes [" + this_sender_handler_id_str + "]: " + str(len(byte_buf)), file=sys.stderr)
                queue_lock.acquire()
                await sender_fifo_q.put([this_sender_handler_id, byte_buf])
                queue_lock.release()
                byte_buf = b''
            await asyncio.sleep(0.01)
    except:
        traceback.print_exc()

async def sender_server():
    global server_send

    try:
        server_send = await asyncio.start_server(
            sender_server_handler, '127.0.0.1', GlobalVals.args.send_stream_port)
    except:
        traceback.print_exc()

    async with server_send:
        await server_send.serve_forever()

def setup_ws_sub_sender_for_sender_server():
    GlobalVals.send_ws = websocket.create_connection(GlobalVals.ws_protcol_str +  "://" + GlobalVals.args.signaling_host + ":" + str(GlobalVals.args.signaling_port) + "/")
    print("sender app level ws (2) opend")
    GlobalVals.sub_channel_sig = GlobalVals.args.gid + "stor"
    lsrvcommon.ws_sender_send_wrapper("join")
