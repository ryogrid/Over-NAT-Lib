# coding: utf-8
import os
from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi, sleep
import traceback

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

def accept_and_later_msg_handle(environ, start_response):
    #TODO: need code checking whether each connection is alive by heartbeat msg send on signaling_app func
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

        print("recieved msg: " + msg)
        
        splited_msg = msg.split(":")
        channel_signiture = splited_msg[0]
        if channel_signiture.endswith("_chsig") == False:
            print("invalid message format. no channel signiture specified.")
            ws.send("invalid message format. no channel signiture specified.")
            break

        signaling_msg = ':'.join(splited_msg[1:])


        # new connection (first recieved message)
        if ws not in ws_list:
            # join already existed Channel or create new Channel
            try:
                if "join" in signaling_msg:
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

    dict_keys = channel_dict.keys()
    for ch_key in dict_keys:
        channel_dict[ch_key].dispose_if_empty()

def signaling_app(environ, start_response):
    clean_disconnected_client_ws_objs_and_channels()
    path = environ["PATH_INFO"]
    if path == "/":
        return accept_and_later_msg_handle(environ, start_response)
    else:
        raise Exception('path not found.')


print("Server is running on localhost:10000...")
server = pywsgi.WSGIServer(('0.0.0.0', 10000), signaling_app, handler_class=WebSocketHandler)
server.serve_forever()
