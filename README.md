# XCP-flash

This is a tool for flashing embedded devices such as electronic control
units (ECUs) via the ["Universal Measurement and Calibration Protocol" (XCP)](https://en.wikipedia.org/wiki/XCP_(protocol))
over CAN. Support for certain devices, for instance with an
`address granularity > 1`,  might be limited, though. Please let us know
if you experience any problems.

XCP-flash has been tested with [USB2CAN](https://www.8devices.com/products/usb2can)
by 8devices, but can be easily customized to work with other adapters as
long as they are supported by [python-can](https://github.com/hardbyte/python-can)
and [can-utils](https://github.com/linux-can/can-utils).

## Install

For installing XCP-flash one merely needs to clone the git repository
and execute the `bin/env.sh` script from the root directory.

```
$ git clone [repo] xcp-flash
$ cd xcp-flash
$ bin/env.sh
```

### Dependencies

Next to `python3` the tool requires the following two libraries, which
however are automatically installed when executing the above commands.

- python-can
- bincopy

## Usage

The tool can be run either using the `bin/xcp-flash` script or by
executing `python3 src/flash.py` and expects a binary file in `.s32` or
`.hex` format as input. Similar file formats can be used if they are
transmitted byte-by-byte and are supported by
[bincopy](https://github.com/eerimoq/bincopy).

```
usage: flash.py [-h] --txid TRANSMISSION_ID --rxid RESPONSE_ID
                [--mode CONN_MODE] [--channel CHANNEL]
                firmware
```

### Example

For flashing a firmware file `firmware.s32` execute
```
bin/xcp-flash --txid 7C7 --rxid 7C8 firmware.s32
```

On Windows USB2CAN adapters need an additional channel/serialnumber:
```
bin/xcp-flash --txid 7C7 --rxid 7C8 --channel ED000200 firmware.s32
```
