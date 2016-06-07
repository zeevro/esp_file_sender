import websocket
import serial
import sys
import time
import os
import binascii
import tqdm


CHUNK_SIZE = 150
TEST_PY = False


def ctrl(key):
    return chr(ord(key.upper()) - ord('A') + 1)


class MyEsp(object):
    def command(self, data='', delay=None):
        delay = delay or self.DEFAULT_DELAY
        self.write(data + '\r')
        time.sleep(delay)
        res = self.read_all()
        #sys.stdout.write(res)
        #print 'RES', repr(res)
        return res

    def reset_esp(self):
        self.write(ctrl('c'))
        self.command(ctrl('d'), 1.5)
        self.command()
        assert self.command().endswith('>>> '), 'Bad reset!'

    def prepare_transfer(self):
        self.command('import ubinascii')
        self.write(ctrl('e'))
        self.write('def w(d):\n')
        self.write('    return f.write(ubinascii.a2b_base64(d))\n')
        self.write(ctrl('d'))
        self.command()
    
    def transfer_chunk(self, chunk):
        assert len(chunk) <= CHUNK_SIZE, 'Chunk is too big!'
        return '...' not in self.command("w('%s')" % binascii.b2a_base64(chunk))


class EspSerial(serial.Serial, MyEsp):
    DEFAULT_DELAY = .1


class EspWebSocket(websocket.WebSocket, MyEsp):
    DEFAULT_DELAY = 0

    write = websocket.WebSocket.send
    read_all = websocket.WebSocket.recv

    def __init__(self, url, password):
        super(EspWebSocket, self).__init__()
        self.connect(url)
        self.read_all()
        self.command(password)


def work(sources, webrepl_url, webrepl_password, uart_port_name, uart_baud=115200):
    try:
        if webrepl_url:
            port = EspWebSocket(webrepl_url, webrepl_password)
        else:
            port = EspSerial(uart_port_name, uart_baud)

        #print 'Performing reset...'
        #port.reset_esp()

        print 'Preparing...'
        port.prepare_transfer()

        for source_path in sources:
            dest_path = os.path.split(source_path)[1]
            try:
                port.command("f = open('%s', 'wb')" % dest_path)

                progress_bar = tqdm.tqdm(ncols=100, desc=source_path, total=os.stat(source_path).st_size, unit='B', unit_scale=True)

                with open(source_path, 'rb') as in_f:
                    while True:
                        buf = in_f.read(CHUNK_SIZE)
                        if not buf:
                            break
                        if not port.transfer_chunk(buf):
                            # TODO: Try again with higher command delay
                            progress_bar.close()
                            print '%s FAILED!' % source_path
                            port.write('\x03')
                            break
                        progress_bar.update(len(buf))
            except Exception as e:
                print e
            finally:
                progress_bar.close()
                port.command('f.close()')
    except Exception as e:
        print e
    finally:
        port.close()

    print 'Done.'


def main():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('-u', '--url', help='WebREPL URL')
    parser.add_argument('-w', '--password', help='WebREPL password')
    parser.add_argument('-p', '--port', help='UART port name')
    parser.add_argument('-b', '--baud', help='UART baud rate', type=int, default=115200)
    parser.add_argument('sources', help='Files to transfer', nargs='+')

    args = parser.parse_args()

    sys.stderr.encoding = 'utf8'

    work(args.sources, args.url, args.password, args.port, args.baud)

if __name__ == '__main__':
    main()
