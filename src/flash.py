#!/usr/bin/env python3

from enum import Enum
import argparse
import platform
import sys

from can import Message, Notifier, BufferedReader
import bincopy


class XCPCommands(Enum):
    """Some codes for relevant xcp commands"""
    CONNECT = 0xFF
    DISCONNECT = 0xFE
    GET_COMM_MODE_INFO = 0xFB
    GET_ID = 0xFA
    SET_MTA = 0xF6
    UPLOAD = 0xF5
    PROGRAM_START = 0xD2
    PROGRAM_CLEAR = 0xD1
    PROGRAM = 0xD0
    PROGRAM_RESET = 0xCF
    PROGRAM_NEXT = 0xCA


class XCPResponses(Enum):
    """xcp response codes"""
    SUCCESS = 0xFF
    ERROR = 0xFE


class XCPErrors:
    """xcp error codes and their messages"""
    ERR_CMD_SYNCH = 0x00
    ERR_CMD_BUSY = 0x10
    ERR_DAQ_ACTIVE = 0x11
    ERR_PGM_ACTIVE = 0x12
    ERR_CMD_UNKNOWN = 0x20
    ERR_CMD_SYNTAX = 0x21
    ERR_OUT_OF_RANGE = 0x22
    ERR_WRITE_PROTECTED = 0x23
    ERR_ACCESS_DENIED = 0x24
    ERR_ACCESS_LOCKED = 0x25
    ERR_PAGE_NOT_VALID = 0x26
    ERR_MODE_NOT_VALID = 0x27
    ERR_SEGMENT_NOT_VALID = 0x28
    ERR_SEQUENCE = 0x29
    ERR_DAQ_CONFIG = 0x2A
    ERR_MEMORY_OVERFLOW = 0x30
    ERR_GENERIC = 0x31
    ERR_VERIFY = 0x32

    error_messages = {
        ERR_CMD_SYNCH: "Command processor synchronization.",
        ERR_CMD_BUSY: "Command was not executed.",
        ERR_DAQ_ACTIVE: "Command rejected because DAQ is running.",
        ERR_PGM_ACTIVE: "Command rejected because PGM is running.",
        ERR_CMD_UNKNOWN: "Unknown command or not implemented optional command.",
        ERR_CMD_SYNTAX: "Command syntax invalid.",
        ERR_OUT_OF_RANGE: "Command syntax valid but command parameter(s) out of range.",
        ERR_WRITE_PROTECTED: "The memory location is write protected.",
        ERR_ACCESS_DENIED: "The memory location is not accessible.",
        ERR_ACCESS_LOCKED: "Access denied, Seed & Key are required.",
        ERR_PAGE_NOT_VALID: "Selected page is not available.",
        ERR_MODE_NOT_VALID: "Selected page mode is not available.",
        ERR_SEGMENT_NOT_VALID: "Selected segment is not valid.",
        ERR_SEQUENCE: "Sequence error.",
        ERR_DAQ_CONFIG: "DAQ configuration is not valid.",
        ERR_MEMORY_OVERFLOW: "Memory overflow error",
        ERR_GENERIC: "Generic error.",
        ERR_VERIFY: "The slave internal program verify routine detects an error."
    }


class XCPFlash:
    """A Tool for flashing devices like electronic control units via the xcp-protocol."""

    _reader = None
    _bus = None
    _notifier = None
    _tx_id = 0
    _rx_id = 0
    _conn_mode = 0
    _data_len = 0
    _max_data_prg = 0
    _max_data = 8

    def __init__(self, tx_id, rx_id, connection_mode=0, channel=None):
        """Sets up a CAN bus instance with a filter and a notifier.

        :param tx_id:
            Id for outgoing messages
        :param rx_id:
            Id for incoming messages
        :param connection_mode:
            Connection mode for the xcp-protocol. Only set if a custom mode is needed.
        :param channel:
            The channel for the can adapter. Only needed for Usb2can on Windows.
        """

        self._reader = BufferedReader()
        if platform.system() == "Windows":
            from can.interfaces.usb2can import Usb2canBus
            self._bus = Usb2canBus(channel=channel)
        else:
            from can.interface import Bus
            self._bus = Bus()
        self._bus.set_filters(
            [{"can_id": rx_id, "can_mask": rx_id + 0x100, "extended": False}])
        self._notifier = Notifier(self._bus, [self._reader])
        self._tx_id = tx_id
        self._rx_id = rx_id
        self._conn_mode = connection_mode

    @staticmethod
    def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='█'):
        """Print a progress bar to the console.

        :param iteration:
            Actual iteration of the task
        :param total:
            Total iteration for completing the task
        :param prefix:
            Text before the progress bar
        :param suffix:
            Text after the progress bar
        :param decimals:
            Number of decimal places for displaying the percentage
        :param length:
            Line length for the progress bar
        :param fill:
            Char to fill the bar
        """
        percent = ("{0:." + str(decimals) + "f}").format(100 *
                                                         (iteration / float(total)))
        filled_length = int(length * iteration // total)
        bar = fill * filled_length + '-' * (length - filled_length)
        sys.stdout.write('\r{} |{}| {}% {}'.format(
            prefix, bar, percent, suffix))
        if iteration == total:
            print()

    def send_can_msg(self, msg, wait=True, timeout=30):
        """Send a message via can

        Send a message over the can-network and may wait for a given timeout for a response.

        :param msg:
            Message to send
        :param wait:
            True if the program should be waiting for a response, False otherwise
        :param timeout:
            Timeout for waiting for a response
        :return:
            The response if wait is set to True, nothing otherwise
        """

        self._bus.send(msg)
        if wait:
            try:
                return self.wait_for_response(timeout, msg)
            except ConnectionAbortedError as err:
                raise err

    def wait_for_response(self, timeout, msg=None):
        """Waiting for a response

        :param timeout:
            Time to wait
        :param msg:
            The message which was send. Set this only if a retry should be made in case of a timeout.
        :return:
            The response from the device
        :raises: ConnectionAbortedError
            if the response is an error
        """

        tries = 1
        while True:
            if tries == 5:
                raise ConnectionAbortedError("Timeout")
            received = self._reader.get_message(timeout)
            if received is None and msg is not None:
                self.send_can_msg(msg, False)
                tries += 1
                continue
            if received is None:
                continue
            if received.arbitration_id == self._rx_id and received.data[0] == XCPResponses.SUCCESS.value:
                return received
            elif received.arbitration_id == self._rx_id and received.data[0] == XCPResponses.ERROR.value:
                raise ConnectionAbortedError(received.data[1])
            elif msg is not None:
                self.send_can_msg(msg, False)

    def execute(self, command, **kwargs):
        """Execute a command

        Builds the can-message to execute the given command and sends it to the device.

        :param command:
            The xcp-command to be executed
        :param kwargs:
            Needed arguments for the command.
                :command SET_MTA:
                    'addr_ext' and 'addr'
                :command PROGRAM_CLEAR:
                    'range'
                :command PROGRAM:
                    'size' and 'data'
        :return: response of the command if waited for
        """

        msg = Message(arbitration_id=self._tx_id,
                      is_extended_id=False, data=bytes(8))
        msg.data[0] = command.value
        if command == XCPCommands.CONNECT:
            msg.data[1] = self._conn_mode
            response = self.send_can_msg(msg)
            self._max_data = response.data[4] << 8
            self._max_data += response.data[5]
            return response
        if command == XCPCommands.DISCONNECT:
            return self.send_can_msg(msg)
        if command == XCPCommands.SET_MTA:
            msg.data[3] = kwargs.get('addr_ext', 0)
            for i in range(4, 8):
                msg.data[i] = (kwargs['addr'] & (
                    0xFF000000 >> (8 * (i - 4)))) >> (8 * (7 - i))
            return self.send_can_msg(msg)
        if command == XCPCommands.PROGRAM_START:
            response = self.send_can_msg(msg)
            max_dto_prg = response.data[3]
            max_bs = response.data[4]
            self._data_len = (max_dto_prg - 2) * max_bs
            self._max_data_prg = max_dto_prg - 2
            return response
        if command == XCPCommands.PROGRAM_CLEAR:
            for i in range(4, 8):
                msg.data[i] = (kwargs['range'] & (
                    0xFF000000 >> (8 * (i - 4)))) >> (8 * (7 - i))
            return self.send_can_msg(msg)
        if command == XCPCommands.PROGRAM or command == XCPCommands.PROGRAM_NEXT:
            msg.data[1] = kwargs["size"]
            position = 2
            for data in kwargs["data"]:
                msg.data[position] = data
                position += 1
            return self.send_can_msg(msg, kwargs['size'] <= self._max_data_prg)
        if command == XCPCommands.PROGRAM_RESET:
            return self.send_can_msg(msg)

    def program(self, data):
        """Program the device

        Program the device with the given firmware

        :param data:
            the firmware as byte-array
        """
        print("flashing new firmware...")
        bytes_send = 0
        while bytes_send < len(data):
            send_length = self._data_len
            if bytes_send % 10000 <= self._data_len:
                self.print_progress_bar(bytes_send, len(data),
                                        prefix="Progress:",
                                        suffix="Complete")
                sys.stdout.flush()
            if send_length > len(data) - bytes_send:
                send_length = len(data) - bytes_send
            self.execute(XCPCommands.PROGRAM, size=send_length,
                         data=data[bytes_send:bytes_send + self._max_data_prg])
            send_length -= self._max_data_prg
            bytes_send += min(send_length, self._max_data_prg)
            while send_length > 0:
                self.execute(XCPCommands.PROGRAM_NEXT, size=send_length,
                             data=data[bytes_send:bytes_send + self._max_data_prg])
                bytes_send += min(send_length, self._max_data_prg)
                send_length -= self._max_data_prg
        self.print_progress_bar(bytes_send, len(data),
                                prefix="Progress:",
                                suffix="Complete")
        self.execute(XCPCommands.PROGRAM_RESET)

    def clear(self, start_addr, length):
        """Clear the memory of the device

        Erase all contents of a given range in the device memory.

        :param start_addr:
            Start address of the range
        :param length:
            Length of the range
        """
        print("erasing device (this may take several minutes)...")
        self.execute(XCPCommands.PROGRAM_START)
        self.execute(XCPCommands.SET_MTA, addr=start_addr)
        self.execute(XCPCommands.PROGRAM_CLEAR, range=length)

    def connect(self):
        """Connect to the device

        :raises: ConnectionError
            if the device doesn't support flash programming or the address granularity is > 1
        """
        print("connecting...")
        response = self.execute(XCPCommands.CONNECT)
        if not response.data[1] & 0b00010000:
            raise ConnectionError(
                "Flash programming not supported by the connected device")
        if response.data[2] & 0b00000110:
            raise ConnectionError("Address granularity > 1 not supported")

    def disconnect(self):
        """Disconnect from the device"""
        print("disconnecting..")
        self.execute(XCPCommands.DISCONNECT)

    def __call__(self, start_addr, data):
        """Flash the device

        Do all the necessary steps for flashing, including connecting to the device and clearing the memory.

        :param start_addr:
            Start address for the firmware
        :param data:
            The firmware as byte-array
        """

        try:
            self.connect()
            self.clear(start_addr, len(data))
            self.program(data)
        except ConnectionAbortedError as err:
            if err.args[0] == "Timeout":
                print("\nConnection aborted: Timeout")
            else:
                print("\nConnection aborted: {}".format(
                    XCPErrors.error_messages[err.args[0]]))
        except ConnectionError as err:
            print("\nConnection error: {}".format(err))
        finally:
            try:
                self.disconnect()
            except ConnectionAbortedError as err:
                if err.args[0] == "Timeout":
                    print("\nConnection aborted: Timeout")
                else:
                    print("\nConnection aborted: {}".format(
                        XCPErrors.error_messages[err.args[0]]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", type=str, help=".s19 firmware file")
    parser.add_argument("--txid", dest="transmission_id", type=str,
                        required=True, help="Message ID for sending (HEX)")
    parser.add_argument("--rxid", dest="response_id", type=str, required=True,
                        help="Message ID for receiving (HEX)")
    parser.add_argument("--mode", dest="conn_mode", type=str, required=False, default="00",
                        help="Connection mode for xcp-session")
    parser.add_argument("--channel", dest="channel", type=str, required=False, default="ED000200",
                        help="Channel for USB2can adapter on Windows")
    args = parser.parse_args()

    f = bincopy.BinFile(args.firmware)

    xcp_flash = XCPFlash(int(args.transmission_id, 16), int(
        args.response_id, 16), int(args.conn_mode, 16), args.channel)
    xcp_flash(f.minimum_address, f.as_binary())

    sys.exit(0)
