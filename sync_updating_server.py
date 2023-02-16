#!/usr/bin/env python
"""
Pymodbus Synchronous Server Example
--------------------------------------------------------------------------

The synchronous server is implemented in pure python without any third
party libraries (unless you need to use the serial protocols which require
pyserial). This is helpful in constrained or old environments where using
twisted is just not feasible. What follows is an example of its use:
"""
# --------------------------------------------------------------------------- #
# import the various server implementations
# --------------------------------------------------------------------------- #
#from pymodbus.server.sync import StartTcpServer
#from pymodbus.server.sync import StartUdpServer
from pymodbus.server.async import StartSerialServer

from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSparseDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext

from pymodbus.transaction import ModbusRtuFramer, ModbusBinaryFramer

from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian

# --------------------------------------------------------------------------- #
# import the twisted libraries we need
# --------------------------------------------------------------------------- #
from twisted.internet.task import LoopingCall

# --------------------------------------------------------------------------- #
# import modules to read ZTATZ api/P1 meter
# --------------------------------------------------------------------------- #
import json
import urllib

# --------------------------------------------------------------------------- #
# configure the service logging
# --------------------------------------------------------------------------- #
import logging
FORMAT = ('%(asctime)-15s %(threadName)-15s'
          ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
log = logging.getLogger()
log.setLevel(logging.ERROR)

# --------------------------------------------------------------------------- #
# define your callback process
# --------------------------------------------------------------------------- #


def updating_writer(a):
    """ A worker process that runs every so often and
    updates live values of the context. It should be noted
    that there is a race condition for the update.

    :param arguments: The input arguments to the call
    """
    try:
        #apiurl = 'http://192.168.0.216/json/apiV1p1data.php?order=desc&limit=1&outputmode=object'
        apiurl = 'http://192.168.0.216/api/v1/smartmeter?order=desc&limit=1&json=object'
        url = urllib.urlopen(apiurl).read()
        result_temp = json.loads(url)  # result is now a dict
    except:
        print("Cannot Open Api URL")
    else:
        result = result_temp[0]

        currentimport = float(result['CONSUMPTION_W'])
        currentexport = float(result['PRODUCTION_W'])
        forwardactiveenergy = float(result['CONSUMPTION_KWH_HIGH']) + float(result['CONSUMPTION_KWH_LOW'])
        reverseactiveenergy = float(result['PRODUCTION_KWH_LOW']) + float(result['PRODUCTION_KWH_LOW'])
        totalcurrent = currentimport - currentexport
        totalactiveenergy = forwardactiveenergy - reverseactiveenergy

        log.debug('Current Importing: ' + str(currentimport))
        log.debug('Current Exporting: ' + str(currentexport))
        log.debug('updating the context')

        context = a[0]
        readregister = 0x03
        writeregister = 0x10
        slave_id = 0x01
        address1 = 0x4012 # Flow of the Current RV FV (ASCII)
        address2 = 0x500A # Current of Flow (FLOAT ABCD)
        address3 = 0x5012 # Total active power KW Float ABCD)
        address4 = 0x6000 # Total active energy kWh Float
        address5 = 0x600c # Forward Active Energy kWH Float
        address6 = 0x6018 # Reverse Active Energy kWh Float


        #values1 = context[slave_id].getValues(register, address1, count=1)
        if currentimport > currentexport:
            values1 = 'FW'
        else:
            values1 = 'RV'

        # Build payload
        builder1 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                    wordorder=Endian.Big)
        builder1.add_string(values1)
        payload1 = builder1.to_registers()
        context[slave_id].setValues(writeregister, address1, payload1)
        log.debug("new values: " + str(values1))
        log.debug("new imp values: " + str(round(currentimport/230,2)))
        log.debug("new exp values: " + str(round(currentexport/230,2)))

        #values2 = context[slave_id].getValues(register, address2, count=2)
        if currentimport > currentexport:
            values2 = round(currentimport / 230,2) # Calculate A from Kwh assume 230 volts
        else:
            values2 = round(currentexport / 230,2) # Calculate A from Kwh, assume 230 volts
        log.debug("new values: " + str(values2))
        # Build payload
        builder2 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
        builder2.add_32bit_float(values2)
        payload2 = builder2.to_registers()
        context[slave_id].setValues(writeregister, address2, payload2)

        builder3 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
        builder3.add_32bit_float(round(totalcurrent/1000,2))
        payload3 = builder3.to_registers()
        context[slave_id].setValues(writeregister, address3, payload3)

        builder4 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
        builder4.add_32bit_float(round(totalactiveenergy,2))
        payload4 = builder4.to_registers()
        context[slave_id].setValues(writeregister, address4, payload4)

        builder5 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
        builder5.add_32bit_float(round(forwardactiveenergy,2))
        payload5 = builder5.to_registers()
        context[slave_id].setValues(writeregister, address5, payload5)

        builder6 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                        wordorder=Endian.Big)
        builder6.add_32bit_float(round(reverseactiveenergy,2))
        payload6 = builder6.to_registers()
        context[slave_id].setValues(writeregister, address6, payload6)

        readvalues = context[slave_id].getValues(0x03,0x4000,0x12)
        log.debug("Values from datastore: " + str(readvalues))

def prefil_registers(a):
    context=a[0]
    # Values to be filled:
    # 4000 SERIAL NUMBER, length 2, 13070001 HEX
    # 4002 MeterCode, length 1, 0102 HEX
    # 4003 Meter ID, Length 1, 0001
    # 4004 Baud, Length 1, 9600
    # 4005 Protocol Version, Lenth 2, 3.2
    # 4007 Software Version, Length 2, 1.18
    # 4009 Hardware Version, Length 2, 1.03
    # 400B Meter Amps, Length 1, 45
    # 400D S0 Rate, Length 2, 1000
    # 400F Combination Code, Length 1, 10 (Forward - Reverse)
    # 4010 LCD LifeCycle, Lenght 1, 01 HEX
    # 4011 Parity Setting, Length 1, 01
    # 4012 Current Direction, Lenght 1, FW ASCII

    builder = BinaryPayloadBuilder(byteorder=Endian.Big,
                                   wordorder=Endian.Big)
    builder.add_32bit_float(0x13070001)
    builder.add_16bit_int(0x0102)
    builder.add_16bit_int(1)
    builder.add_16bit_int(9600)
    builder.add_32bit_float(3.2)
    builder.add_32bit_float(1.18)
    builder.add_32bit_float(1.03)
    builder.add_16bit_int(45)
#    builder.add_16bit_int(0)
    payload = builder.to_registers()
    context[0x01].setValues(0x10, 0x4000, payload)
    # Skip Address
    builder2 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                   wordorder=Endian.Big)
    builder2.add_32bit_float(1000)
    builder2.add_16bit_int(10)
    builder2.add_16bit_int(0x10)
    builder2.add_16bit_int(01)
    builder2.add_string('FW')
    payload2 = builder2.to_registers()
    context[0x01].setValues(0x10, 0x400D, payload2)

    # 5000
    builder3 = BinaryPayloadBuilder(byteorder=Endian.Big,
                                   wordorder=Endian.Big)
    builder3.add_32bit_float(230)
    builder3.add_32bit_float(230)
    builder3.add_32bit_float(230)
    builder3.add_32bit_float(230)
    builder3.add_32bit_float(50)
    payload3 = builder3.to_registers()
    context[0x01].setValues(0x10, 0x5000, payload3)

def run_server():
    # ----------------------------------------------------------------------- #
    # initialize your data store
    # ----------------------------------------------------------------------- #
    # The datastores only respond to the addresses that they are initialized to
    # Therefore, if you initialize a DataBlock to addresses of 0x00 to 0xFF, a
    # request to 0x100 will respond with an invalid address exception. This is
    # because many devices exhibit this kind of behavior (but not all)::
    #
    #     block = ModbusSequentialDataBlock(0x00, [0]*0xff)
    #
    # Continuing, you can choose to use a sequential or a sparse DataBlock in
    # your data context.  The difference is that the sequential has no gaps in
    # the data while the sparse can. Once again, there are devices that exhibit
    # both forms of behavior::
    #
    #     block = ModbusSparseDataBlock({0x00: 0, 0x05: 1})
    #     block = ModbusSequentialDataBlock(0x00, [0]*5)
    #
    # Alternately, you can use the factory methods to initialize the DataBlocks
    # or simply do not pass them to have them initialized to 0x00 on the full
    # address range::
    #
    #     store = ModbusSlaveContext(di = ModbusSequentialDataBlock.create())
    #     store = ModbusSlaveContext()
    #
    # Finally, you are allowed to use the same DataBlock reference for every
    # table or you may use a separate DataBlock for each table.
    # This depends if you would like functions to be able to access and modify
    # the same data or not::
    #
    #     block = ModbusSequentialDataBlock(0x00, [0]*0xff)
    #     store = ModbusSlaveContext(di=block, co=block, hr=block, ir=block)
    #
    # The server then makes use of a server context that allows the server to
    # respond with different slave contexts for different unit ids. By default
    # it will return the same context for every unit id supplied (broadcast
    # mode).
    # However, this can be overloaded by setting the single flag to False and
    # then supplying a dictionary of unit id to context mapping::
    #
    #     slaves  = {
    #         0x01: ModbusSlaveContext(...),
    #         0x02: ModbusSlaveContext(...),
    #         0x03: ModbusSlaveContext(...),
    #     }
    #     context = ModbusServerContext(slaves=slaves, single=False)
    #
    # The slave context can also be initialized in zero_mode which means that a
    # request to address(0-7) will map to the address (0-7). The default is
    # False which is based on section 4.4 of the specification, so address(0-7)
    # will map to (1-8)::
    #
    #     store = ModbusSlaveContext(..., zero_mode=True)
    # ----------------------------------------------------------------------- #
    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0x4000, [0] * 0x6006),
        co=ModbusSequentialDataBlock(0x4000, [0] * 0x6006),
        hr=ModbusSequentialDataBlock(0x4000, [0] * 0x6006),
        ir=ModbusSequentialDataBlock(0x4000, [0] * 0x6006))

    context = ModbusServerContext(slaves={1: store}, single=False)

    # ----------------------------------------------------------------------- #
    # initialize the server information
    # ----------------------------------------------------------------------- #
    # If you don't set this or any fields, they are defaulted to empty strings.
    # ----------------------------------------------------------------------- #
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Pymodbus'
    identity.ProductCode = 'PM'
    identity.VendorUrl = 'http://github.com/riptideio/pymodbus/'
    identity.ProductName = 'Pymodbus Server'
    identity.ModelName = 'Pymodbus Server'
    identity.MajorMinorRevision = '1.5'

    # ----------------------------------------------------------------------- #
    # run the server you want
    # ----------------------------------------------------------------------- #
    time = 10  # 5 seconds delay
    loop = LoopingCall(f=updating_writer, a=(context,))
    loop.start(time, now=False) # initially delay by time

    prefil_registers(a=(context,))

    # RTU:
    StartSerialServer(context, framer=ModbusRtuFramer, identity=identity,
                       port='/dev/ttyUSB0', timeout=.005, baudrate=9600)

if __name__ == "__main__":
    run_server()
