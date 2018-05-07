import socketserver
import threading

from . import worker_manager

Dcommands = {
    'ping':worker_manager.ping,
    'waiting':worker_manager.waiting,
    'handled':worker_manager.hanled,
    'stop':worker_manager.stop
}

class TaskSocketServer(socketserver.BaseRequestHandler):
    
    def handle(self):
        
        try:
            data = self.request.recv(5000).strip() #like the pickled task field
        except Exception as e:
            response = (False, "SocketServer: {}".format(e).encode())
            self.request.send(response)
        
        
        if data in Dcommands.keys():
            try:
                worker_response = Dcommands[data]()
                if worker_response == 'Worker Off':
                    response = (False,worker_response.encode())
                else:
                    response = (True,worker_response.encode(),)
            except Exception as e:
                response =  (False,"TaskServer Command: {}".format(e).encode(),)                
        else:        
            try:
                worker_response = worker_manager.put_task(data) #a tuple
                response = worker_response
            except Exception as e:
                response =  (False,"TaskServer Put: {}".format(e).encode(),)
            
        try:    
            self.request.send(str(response))
        except Exception as e:
            self.request.send("SocketServer Response: {}".format(e).encode())
        
        
class TaskSocketServerThread(threading.Thread):
    
    def __init__(self,host,port):
        
        threading.Thread.__init__(self, name='tasks-socket-server')
        self.host = host
        self.port = port
        self.setDaemon(1)
        self.start()
        
    def socket_server(self):
        return self.server
    
    
    def run(self):
        
        self.server = socketserver.TCPServer((self.host,self.port), TaskSocketServer)
        
    
    
        