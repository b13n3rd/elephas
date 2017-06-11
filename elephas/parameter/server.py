import socket
from threading import Lock, Thread
import six.moves.cPickle as pickle
from flask import Flask, request
from multiprocessing import Process

from ..utils.sockets import determine_master
from ..utils.sockets import receive, send
from ..utils.serialization import dict_to_model
from ..utils.rwlock import RWLock


class BaseParameterServer(object):
    def __init__(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class HttpServer(BaseParameterServer):

    def __init__(self, master_network, optimizer, mode):
        self.master_network = master_network
        self.mode = mode
        self.master_url = None
        self.optimizer = optimizer

        self.lock = RWLock()
        self.pickled_weights = None
        self.weights = master_network.get_weights()

    def start(self):
        '''Start parameter server'''
        self.server = Process(target=self.start_flask_service)
        self.server.start()
        self.master_url = determine_master()

    def stop(self):
        '''Terminate parameter server'''
        self.server.terminate()
        self.server.join()

    def start_flask_service(self):
        '''Define service and run flask app'''
        app = Flask(__name__)
        self.app = app

        @app.route('/')
        def home():
            return 'Elephas'

        @app.route('/parameters', methods=['GET'])
        def handle_get_parameters():
            if self.mode == 'asynchronous':
                self.lock.acquire_read()
            self.pickled_weights = pickle.dumps(self.weights, -1)
            pickled_weights = self.pickled_weights
            if self.mode == 'asynchronous':
                self.lock.release()
            return pickled_weights

        @app.route('/update', methods=['POST'])
        def handle_update_parameters():
            delta = pickle.loads(request.data)
            if self.mode == 'asynchronous':
                self.lock.acquire_write()
            constraints = self.master_network.constraints
            if len(constraints) == 0:
                def empty(a):
                    return a
                constraints = [empty for x in self.weights]
            self.weights = self.optimizer.get_updates(self.weights, constraints, delta)
            if self.mode == 'asynchronous':
                self.lock.release()
            return 'Update done'

        self.app.run(host='0.0.0.0', debug=True,
                     threaded=True, use_reloader=False)


class SocketServer(object):
    def __init__(self, model, port=4000):
        self.model = dict_to_model(model)
        self.port = port
        self.socket = None
        self.runs = False
        self.connections = []
        self.lock = Lock()
        self.thread = None

    def start(self):
        if self.thread is not None:
            self.stop()
        self.thread = Thread(target=self.start_server)
        self.thread.start()

    def stop(self):
        self.stop_server()
        self.thread.join()
        self.thread = None

    def start_server(self):
        self.runs = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.listen(5)
        self.socket = sock
        self.run()

    def stop_server(self):
        self.runs = False
        if self.socket:
            for thread in self.connections:
                thread.join()
                del thread
            self.socket.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(("localhost", self.port))
                sock.close()
            except Exception:
                pass
        self.socket = None
        self.connections = []

    def update_parameters(self, socket):
        data = receive(socket)
        delta = data['delta']
        with self.lock:
            weights = self.model.get_weights() + delta
            self.model.set_weights(weights)

    def get_parameters(self, socket):
        with self.lock:
            weights = self.model.get_weights()
        send(socket, weights)

    def action_listener(self, connection):
        while self.runs:
            get_or_update = connection.recv(1).decode()
            if get_or_update == 'u':
                self.set_parameters(connection)
            elif get_or_update == 'g':
                self.get_parameters(connection)
            else:
                print('Not a valid action')

    def run(self):
        while self.runs:
            try:
                conn, addr = self.socket.accept()
                thread = Thread(target=self.action_listener, args=(conn, addr))
                thread.start()
                self.connections.append(thread)
            except Exception:
                pass