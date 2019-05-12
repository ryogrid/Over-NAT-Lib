import os
from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi, sleep

# from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
# from collections import OrderedDict

ws_set = set()

user_hash = {} # ws => name
user_list = [] # contains names

def accept_and_later_msg_handle(environ, start_response):
    global user_list
    global user_hash
    global ws_set

    ws = environ['wsgi.websocket']
    ws_set.add(ws)
    print('new client connected! member-num =>' + str(len(ws_set)))
    while True:
        msg = ws.receive()
        if msg is None:
            break
        for s in ws_set:
            try:
                s.send(msg)
            except Exception:
                import traceback
                traceback.print_exc()

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

def signaling_app(environ, start_response):
    path = environ["PATH_INFO"]
    if path == "/":
        return accept_and_later_msg_handle(environ, start_response)
    else:
        raise Exception('path not found.')

print("Server is running on localhost:10000...")
server = pywsgi.WSGIServer(('0.0.0.0', 10000), signaling_app, handler_class=WebSocketHandler)
server.serve_forever()

# WebSocketServer(
#     ('127.0.0.1', 10000),
#     Resource(OrderedDict([('', SignalingApplication)]))
# ).serve_forever()
