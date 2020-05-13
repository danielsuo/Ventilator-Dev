from vent.io.devices import I2CDevice, be16_to_native
from abc import ABC, abstractmethod
from random import random

import time
import numpy as np


class Sensor(ABC):
    """ Abstract base Class describing generalized sensors. Defines a mechanism for limited internal storage of recent
    observations and methods to pull that data out for external use.
    """
    _DEFAULT_STORED_OBSERVATIONS = 128

    def __init__(self):
        """ Upon creation, calls update() to ensure that if get is called there will be something to return."""
        self._data = np.zeros(
            self._DEFAULT_STORED_OBSERVATIONS,
            dtype=np.float16
        )
        self._i = 0
        self._data_length = self._DEFAULT_STORED_OBSERVATIONS
        self._last_timestamp = -1

    def update(self) -> float:
        """ Make a sensor reading, verify that it makes sense and store the result internally. Returns True if reading
        was verified and False if something went wrong.
        """
        value = self._read()
        if self._verify(value):
            self.__store_last(value)
            self._last_timestamp = time.time()
        return self._verify(value)

    def get(self) -> float:
        """ Return the most recent sensor reading."""
        if self._last_timestamp == -1:
            raise RuntimeWarning('get() called before update()')
        return self._data[(self._i - 1) % self._data_length]

    def age(self) -> float:
        """ Returns the time in seconds since the last sensor update, or -1 if never updated."""
        if self._last_timestamp == -1:
            return -1.0
        else:
            return time.time() - self._last_timestamp

    def reset(self):
        """ Resets the sensors internal memory. May be overloaded by subclasses to extend functionality specific to a
        device.
        """
        self._data = np.zeros(self.data_length, dtype=np.float16)
        self._i = 0

    @property
    def data(self) -> np.ndarray:
        """ Locally-stored observations.
        Note: ndarray.astype(bool) returns an equivalent sized array
        with True for each nonzero element and False everywhere else.

        Returns:
            np.ndarray: an ndarray of observations arranged oldest to newest. Result has length equal to the lessor
                of self.n and the number of observations.
        made.
        """
        rolled = np.roll(self._data, self.data_length - self._i)
        return rolled[rolled.astype(bool)]

    @property
    def data_length(self) -> int:
        """ Returns the number of observations kept in the Sensor's internal ndarray. Once the ndarray has been filled,
        the sensor begins overwriting the oldest elements of the ndarray with new observations such that the size of the
        internal storage stays constant.
        """
        return self._data_length

    @data_length.setter
    def data_length(self, new_data_length):
        """ Set a new length for stored observations. Clears existing
        observations and resets.

        Args:
            new_data_length (int): The new length of internal observation storage
        """
        self._data_length = new_data_length
        self.reset()

    def _read(self) -> float:
        """ Calls _raw_read and scales the result before returning it."""
        return self._convert(self._raw_read())

    @abstractmethod
    def _verify(self, value):
        """ Validate reading and throw exception/alarm if sensor does not appear to be working correctly.
        """
        raise NotImplementedError('Subclass must implement _verify()')

    @abstractmethod
    def _convert(self, raw):
        """ Converts a raw reading from a sensor in whatever format the device communicates with into a meaningful
        result.
        """
        raise NotImplementedError('Subclass must implement _raw_read()')

    @abstractmethod
    def _raw_read(self):
        """ Requests a new observation from the device and returns the raw result in whatever format/units the device
        communicates with.
        """
        raise NotImplementedError('Subclass must implement _raw_read()')

    def __store_last(self, value):
        """ Takes a value and stores it in self.data. Increments

        Args:
            value (float): Sensor reading to store.
        """
        self._data[self._i] = value
        self._i = (self._i + 1) % self.data_length


class AnalogSensor(Sensor):
    """ Generalized class describing an analog sensor attached to the ADS1115 analog to digital converter. Inherits from
    the sensor base class and extends with functionality specific to analog sensors attached to the ADS1115. If
    instantiated without a subclass, conceptually represents a voltmeter with a normalized output.
    """
    _DEFAULT_offset_voltage = 0
    _DEFAULT_output_span = 5
    _DEFAULT_CALIBRATION = {
        'offset_voltage': _DEFAULT_offset_voltage,
        'output_span': _DEFAULT_output_span,
        'conversion_factor': 1
    }

    def __init__(self, adc, **kwargs):
        """ Links analog sensor on the ADC with configuration options specified. If no options are specified, it assumes
        the settings currently on the ADC.

        Args:
            adc (vent.io.devices.ADS1115): The adc object to which the AnalogSensor is attached
            **kwargs: `field=value` - see vent.io.devices.ADS1115 for additional documentation. Strongly suggested to
                specify `MUX=adc_pin` here unless you know what you're doing.
        """
        super().__init__()
        self.adc = adc
        if 'MUX' not in (kwargs.keys()):
            raise TypeError(
                'User must specify MUX for AnalogSensor creation'
            )
        kwargs = {key: kwargs[key] for key in kwargs.keys() - ('pig',)}
        self._check_and_set_attr(**kwargs)

    def calibrate(self, **kwargs):
        """ Sets the calibration of the sensor, either to the values contained in the passed tuple or by some routine;
        the current routine is pretty rudimentary and only calibrates offset voltage.

        Args:
            **kwargs: calibration_field=value, where calibration field is one of the following: 'offset_voltage',
                output_span' or 'conversion_factor'
        """
        # FIXME
        if kwargs:
            for fld, val in kwargs.items():
                if fld in self._DEFAULT_CALIBRATION.keys():
                    setattr(self, fld, val)
        else:
            for _ in range(50):
                self.update()
                # PRINT FOR DEBUG / HARDWARE TESTING
                print(
                    "Analog Sensor Calibration @ {:6.4f}".format(self.data[self.data.shape[0] - 1]),
                    end='\r'
                )
                time.sleep(.1)
            self.offset_voltage = np.min(self.data[-50:])
            # PRINT FOR DEBUG / HARDWARE TESTING
            print("Calibrated low-end of AnalogSensor @",
                  ' %6.4f V' % self.offset_voltage)

    def _read(self) -> float:
        """ Returns a value in the range of 0 - 1 corresponding to a fraction of the full input range of the sensor."""
        return self._convert(self._raw_read())

    def _verify(self, value) -> bool:
        """ Checks to make sure sensor reading was indeed in [0, 1].

        Args:
            value (float): Sensor reading to validate
        """
        report = bool(0 <= value / self.conversion_factor <= 1)
        if not report:
            # FIXME: Right now this just expands the calibration range whenever bounds are exceeded, because we're not
            #  familiar enough with our sensors to know when we should really be rejecting values. This approach should
            #  work for debugging/R&D purposes but really ought to be thought through and/or replaced for production.
            #  For example, negative voltages are probably bad. voltages about VDD (~5V) are also probably bad. There is
            #  some expected drift around offset voltage and output span, however, and that drift is going to change
            #  depending on the sensor in question; i.e., voltages between offset_voltage and zero may or may not be ok,
            #  and voltages above the offset+span that do not exceed VDD may or may not be ok as well.
            self.offset_voltage = min(self.offset_voltage, value)
            self.output_span = max(self.output_span, value - self.offset_voltage)
            print('Warning: AnalogSensor calibration adjusted')
        return report

    def _convert(self, raw) -> float:
        """ Scales raw voltage into the range 0 - 1.

        Args:
            raw (float): The raw sensor reading to convert.
        """
        return (
                self.conversion_factor * (raw - getattr(self, 'offset_voltage'))
                / (getattr(self, 'output_span'))
        )

    def _raw_read(self) -> float:
        """ Builds kwargs from configured fields to pass along to adc, then calls adc.read_conversion(), which returns
        a raw voltage.
        """
        fields = self.adc.USER_CONFIGURABLE_FIELDS
        kwargs = dict(zip(
            fields,
            (getattr(self, field) for field in fields)
        ))
        return self.adc.read_conversion(**kwargs)

    def _fill_attr(self):
        """ Examines self to see if there are any fields identified as user configurable or calibration that have not
        been write (i.e. were not passed to __init__ as **kwargs). If a field is missing, grabs the default value either
        from the ADC or from _DEFAULT_CALIBRATION and sets it as an attribute.
        """
        for cfld in self.adc.USER_CONFIGURABLE_FIELDS:
            if not hasattr(self, cfld):
                setattr(
                    self,
                    cfld,
                    getattr(self.adc.config, cfld).unpack(self.adc.cfg)
                )
        for dcal, value in self._DEFAULT_CALIBRATION.items():
            if not hasattr(self, dcal):
                setattr(self, dcal, value)

    def _check_and_set_attr(self, **kwargs):
        """ Checks to see if arguments passed to __init__ are recognized as user configurable or calibration fields. If
        so, write the value as an attribute like: self.KEY = VALUE. Keeps track of how many attributes are write in this
        way; if at the end there unknown arguments leftover, raises a TypeError; otherwise, calls _fill_attr() to fill
        in fields that were not passed as arguments.

        Args:
            **kwargs: `field=value` - see vent.io.devices.ADS1115 for additional documentation
        """
        allowed = (
            *self.adc.USER_CONFIGURABLE_FIELDS,
            *self._DEFAULT_CALIBRATION.keys(),
        )
        result = 0
        for fld, val in kwargs.items():
            if fld in allowed:
                setattr(self, fld, val)
                result += 1
        if result != len(kwargs):
            raise TypeError('AnalogSensor was passed unknown field(s)', kwargs.items(), allowed)
        self._fill_attr()


class SFM3200(Sensor, I2CDevice):
    """ I2C Inspiratory flow sensor manufactured by Sensirion AG. Range: +/- 250 SLM
    Datasheet:
         https://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/ ...
            ... 5_Mass_Flow_Meters/Datasheets/Sensirion_Mass_Flow_Meters_SFM3200_Datasheet.pdf
    """
    _DEFAULT_ADDRESS = 0x40
    _FLOW_OFFSET = 32768
    _FLOW_SCALE_FACTOR = 120

    def __init__(self, address=_DEFAULT_ADDRESS, i2c_bus=1, pig=None):
        """
        Args:
            address (int): The I2C Address of the SFM3200 (usually 0x40)
            i2c_bus (int): The I2C Bus to use (usually `1` on the Raspberry Pi)
            pig (PigpioConnection): pigpiod connection to use; if not specified, a new one is established
        """
        I2CDevice.__init__(self, address, i2c_bus, pig)
        Sensor.__init__(self)
        self.reset()
        self._start()

    def reset(self):
        """ Extended to add device specific behavior: Asks the sensor to perform a soft reset. 80 ms soft reset time."""
        super().reset()
        self.write_device(0x2000)
        time.sleep(.08)

    def _start(self):
        """ Device specific:Sends the 'start measurement' command to the sensor. Start-up time once command has been
        recieved is 'less than 100ms'
        """
        self.write_device(0x1000)
        time.sleep(.1)

    def _verify(self, value) -> bool:
        """ No further verification needed for this sensor. Onboard chip handles all that. Could throw in a CRC8 checker
        instead of discarding them in _convert().

        Args:
            value (float): The sensor reading to verify.
        """
        return True

    def _convert(self, raw) -> float:
        """ Overloaded to replace with device-specific protocol. Convert raw int to a flow reading having type float
        with units slm. Implementation differs from parent for clarity and consistency with source material.

        Source:
          https://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/ ...
            ... 5_Mass_Flow_Meters/Application_Notes/Sensirion_Mass_Flo_Meters_SFM3xxx_I2C_Functional_Description.pdf

        Args:
            raw (int): The raw value read from the SFM3200
        """
        return (raw - self._FLOW_OFFSET) / self._FLOW_SCALE_FACTOR

    def _raw_read(self) -> int:
        """ Performs an read on the sensor, converts received bytearray, discards the last two bytes (crc values - could
        implement in future), and returns a signed int converted from the big endian two complement that remains.
        """
        return be16_to_native(self.read_device(4))


class SimSensor(Sensor):
    def __init__(self, low=0, high=100, pig=None):
        """ TODO
        Stub simulated sensor.

        Args:
            low: Lower-bound of possible sensor values
            high: Upper-bound of possible sensor values
            pig (PigpioConnection): Ignored.
        """
        super().__init__()
        self.low = low
        self.high = high

    def _verify(self, value) -> bool:
        """ Usually verifies sensor readings but occasionally misbehaves.

        Args:
            value (float): The sensor reading to verify
        """
        if random() > .999:
            return False
        else:
            return True

    def _convert(self, raw) -> float:
        """ Does nothing for a simulated sensor. Returns what it is passed.

        Args:
            raw (float): The raw value to convert
        """
        return raw

    def _raw_read(self) -> float:
        """ Initializes randomly, otherwise does a random walk-ish thing."""
        if self._i == 0:
            return self.low + random() * self.high
        else:
            return self.get() + random() * (self.high / 100)
