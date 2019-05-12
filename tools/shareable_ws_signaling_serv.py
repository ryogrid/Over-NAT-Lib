import os
from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi, sleep
import traceback

# from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
# from collections import OrderedDict

ws_set = set()

# user_hash = {} # ws => name
# user_list = [] # contains names

def accept_and_later_msg_handle(environ, start_response):
    # global user_list
    # global user_hash

    #TODO: need code checking whether each connection is alive by heartbeat msg send on signaling_app func
    global ws_set

    ws = environ['wsgi.websocket']
    ws_set.add(ws)
    print('new client connected! member-num =>' + str(len(ws_set)))
    remove_list = []
    while True:
        if len(remove_list) > 0:
            for s in remove_list:
                ws_set.remove(s)
            remove_list = []

        msg = ws.receive()
        if msg is None:
            break
        for s in ws_set:
            try:
                s.send(msg)
            except:
                # Possibility to execute code when connection is closed
                print("a client disconnected.")
                #traceback.print_exc()
                remove_list.append(s)
                next

    #     user_name = msg.split(":")[0]
    #     if (not (ws in user_hash)) or (ws in user_hash and user_hash[ws] == "init"):
    #         user_hash[ws] = user_name
    #         if user_name != "init":
    #             user_list.append(user_name)
    #     if ws in user_hash and user_name not in user_list:
    #         if user_name != "init":
    #             user_list.append(user_name)
    #     remove = set()
    #     name = msg.split(":")[0]
    #     pure_text = msg.split(":")[1]
    #     try:
    #         handle_commands(name, pure_text)
    #     except Exception:
    #         import traceback
    #         traceback.print_exc()
    #         return
    #     for s in ws_set:
    #         try:
    #             if s in user_hash:
    #                 user_name = user_hash[s]
    #             else:
    #                 user_name = "init"
    #
    #             if user_name != "init":
    #                 make_enable_open(user_list.index(user_name))
    #             s.send(msg + "," + gen_table(user_name, msg))
    #             make_all_close()
    #         except Exception:
    #             import traceback
    #             traceback.print_exc()
    #             remove.add(s)
    #     for s in remove:
    #         ws_set.remove(s)
    # print 'exit!', len(ws_set)

def clean_disconnected_client_ws_objs():
    global ws_set

    remove_list = []
    for s in ws_set:
        try:
            s.send("check_alive_msg")
        except:
            # Possibility to execute code when connection is closed
            print("disconnected client found.")
            #traceback.print_exc()
            remove_list.append(s)
            next
    for s in remove_list:
        ws_set.remove(s)

def signaling_app(environ, start_response):
    clean_disconnected_client_ws_objs()
    path = environ["PATH_INFO"]
    if path == "/":
        return accept_and_later_msg_handle(environ, start_response)
    else:
        raise Exception('path not found.')


print("Server is running on localhost:10000...")
server = pywsgi.WSGIServer(('0.0.0.0', 10000), signaling_app, handler_class=WebSocketHandler)
server.serve_forever()
