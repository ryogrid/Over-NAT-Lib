# coding: utf-8
import os
from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi, sleep
import traceback
import copy
import time
import argparse

ws_list = []
channel_dict = {}

class Channel(object):

    def __init__(self, channel_sig):
        self.users = []
        self.channel_sig = channel_sig

    def join(self, user_ws):
        if user_ws not in self.users:
            if len(self.users) < 2:
                print("joined to " + self.channel_sig)
                self.users.append(user_ws)
            else:
                print("chanel member capacity is already full")
                raise Exception("chanel member capacity is already full")

    def remove(self, user_ws):
        if user_ws in self.users:
            self.users.remove(user_ws)

    def delegate_msg(self, user_ws, msg):
        print("msg delegated: " + msg)
        remove_list = []
        for s in self.users:
            try:
                if s != user_ws:
                    s.send(msg)
#                else:
#                    s.send("ok")
            except:
                # Possibility to execute code when connection is closed
                print("a client disconnected.")
                #traceback.print_exc()
                remove_list.append(s)
                next
        for s in remove_list:
            self.users.remove(s)
        self.dispose_if_empty()

    def dispose_if_empty(self):
        global channel_dict
        if len(self.users) == 0:
            del channel_dict[self.channel_sig]

# a call handles single client forever
def accept_and_later_msg_handle(environ, start_response):
    global ws_list
    global channel_dict

    ws = environ['wsgi.websocket']
    #print('new client connected! member-num =>' + str(len(ws_set)))
    remove_list = []
    while True:
        if len(remove_list) > 0:
            for s in remove_list:
                ws_list.remove(s)
            remove_list = []

        msg = ws.receive()
        if msg is None:
            break

        if msg.endswith("_chsig:keepalive"):
            continue

        print("recieved msg: " + msg)

        splited_msg = msg.split(":")
        channel_signiture = splited_msg[0]
        if channel_signiture.endswith("_chsig") == False:
            print("invalid message format. no channel signiture specified.")
            ws.send("invalid message format. no channel signiture specified.")
            break

        signaling_msg = ':'.join(splited_msg[1:])

        # though already joined, handle this message
        if "joined_members_sub" in signaling_msg:
            resp_msg = None
            if channel_signiture in channel_dict:
                resp_msg = str(len(channel_dict[channel_signiture].users))
            else:
                resp_msg = str(0)
            # print("send response of joined_message: " + "{ \"members\":" + resp_msg + "}")
            # ws.send("{ \"members\":" + resp_msg + "}")
            print("send response of joined_message: " + "member_count:" + resp_msg )
            ws.send("member_count:" + resp_msg)
            continue

        # new connection (first recieved message)
        if ws not in ws_list:
            # join already existed Channel or create new Channel
            try:
                if "joined_members" in signaling_msg: # for websocket of asyncio
                    resp_msg = None
                    if channel_signiture in channel_dict:
                        resp_msg = str(len(channel_dict[channel_signiture].users))
                    else:
                        resp_msg = str(0)
                    print("send response of joined_message: " + "{ \"members\":" + resp_msg + "}")
                    ws.send("{ \"members\":" + resp_msg + "}")
                    # time.sleep(2)
                    break
                    # continue
                elif "receiver_connected" in signaling_msg:
                    print("receiver_connected msg received")
                    ws.send("receiver_connected")
                    continue
                elif "receiver_disconnected" in signaling_msg:
                    print("receiver_disconnected msg received")
                    ws.send("receiver_disconnected")
                    continue
                elif "sender_connected" in signaling_msg:
                    print("sender_connected msg received")
                    ws.send("sender_connected")
                    continue
                elif "sender_disconnected" in signaling_msg:
                    print("sender_disconnected msg received")
                    ws.send("sender_disconnected")
                    continue
                elif "join" in signaling_msg:
                    if channel_signiture in channel_dict:
                        channel_dict[channel_signiture].join(ws)
                    else:
                        new_channel = Channel(channel_signiture)
                        new_channel.join(ws)
                        channel_dict[channel_signiture] = new_channel
                    ws_list.append(ws)
                    continue
                else:
                    print("new connection (first message), but not invalid message" + signaling_msg)
                    break
            except:
                print("join to " + channel_signiture + " is denided.")
                traceback.print_exc()
                #ws.send("NG")
                #ws.send("join to " + channel_signiture + " is denided.")
                break

        if ws in ws_list:
            try:
                channel_dict[channel_signiture].delegate_msg(ws, signaling_msg)
            except:
                print("delegate msg to " + channel_signiture + " failed.")
                traceback.print_exc()
                #ws.send("NG")
                #ws.send("join to " + channel_signiture + " is denided.")
                break

def clean_disconnected_client_ws_objs_and_channels():
    global ws_list
    global channel_dict

    try:
        remove_list = []
        for s in ws_list:
            try:
                s.send("check_alive_msg")
            except:
                # Possibility to execute code when connection is closed
                print("disconnected client found.")
                #traceback.print_exc()
                remove_list.append(s)
                next
        for s in remove_list:
            ws_list.remove(s)
            for channel_sig in channel_dict.keys():
                channel_obj = channel_dict[channel_sig]
                print("user remove len (BEFORE):" + str(len(channel_obj.users)))
                channel_obj.users.remove(s)
                print("user remove len (AFTER):" + str(len(channel_obj.users)))

        dict_keys = copy.copy(list(channel_dict.keys()))
        for ch_key in dict_keys:
            channel_dict[ch_key].dispose_if_empty()
        print("finished clean_disconnected_client_ws_objs_and_channels")
    except Exception as e:
        print(e)

def signaling_app(environ, start_response):
    #clean_disconnected_client_ws_objs_and_channels()
    path = environ["PATH_INFO"]
    if path == "/":
        return accept_and_later_msg_handle(environ, start_response)
    else:
        raise Exception('path not found.')



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='WebRTC datachannel signaling server with websocket protcol')
    parser.add_argument('--secure',
                        help='Signaling communication is encrypted', action='store_true')
    args = parser.parse_args()

    print("Server is running on localhost:10000...")
    server = None
    if args.secure == True:
        server = pywsgi.WSGIServer(('0.0.0.0', 10000), signaling_app, handler_class=WebSocketHandler,
                                   keyfile='privkey.pem', certfile='fullchain.pem')
    else:
        server = pywsgi.WSGIServer(('0.0.0.0', 10000), signaling_app, handler_class=WebSocketHandler)

    server.serve_forever()
