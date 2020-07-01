import time
import importlib
from datetime import datetime

from itertools import count
from vent.alarm import AlarmType, AlarmSeverity

class Alarm:
    """
    Class used by the program to control and coordinate alarms.

    Parameterized by a :class:`Alarm_Rule` and managed by :class:`Alarm_Manager`
    """


    id_counter = count()
    """
    :class:`itertools.count`: used to generate unique IDs for each alarm
    """

    def __init__(self,
                 alarm_type: AlarmType,
                 severity: AlarmSeverity,
                 start_time: float = None,
                 latch: bool = True,
                 persistent: bool = True,
                 value=None,
                 message=None):
        """
        Attributes:
            id (int): unique alarm ID

        Args:
            alarm_type :
            severity:
            start_time:
            value (int, float): optional - numerical value that generated the alarm
            message (str): optional - override default text generated by :class:`~vent.gui.alarm_manager.AlarmManager`
        """


        self.id = next(Alarm.id_counter) # type: int

        assert isinstance(severity, AlarmSeverity)
        self._severity = severity

        assert isinstance(alarm_type, AlarmType)
        self._alarm_type = alarm_type

        if start_time is None:
            self.start_time = time.time()
        else:
            assert isinstance(start_time, float)
            self.start_time = start_time

        self.active = True
        if self.severity == AlarmSeverity.OFF:
            self.active = False

        self.end_time = None
        self.value = value
        self.message = message
        self.latch = latch
        self.persistent = persistent

        # if not managed:
        #     self.manager.register_alarm(self)

    # @property
    # def manager(self):
    #     """
    #     have ta do it this janky way to avoid circular imports
    #     """
    #     try:
    #         return Alarm_Manager()
    #     except:
    #         # import into the module namespace
    #         manager_module = importlib.import_module('vent.alarm.alarm_manager')
    #         globals()['Alarm_Manager'] = getattr(manager_module, 'Alarm_Manager')
    #         return Alarm_Manager()

    @property
    def severity(self) -> AlarmSeverity:
        # no setter, don't want to be able to change after instantiation
        return self._severity

    @property
    def alarm_type(self) -> AlarmType:
        return self._alarm_type



    def deactivate(self):
        if not self.active:
            return

        self.end_time = time.time()
        self.active = False
        # make sure the manager deactivates us.
        # manager checks if this has already been done so doesn't recurse
        #self.manager.deactivate_alarm(self)

    def __str__(self) -> str:
        """
        Loggable representation of alarm

        Returns:
            str
        """

        if self.end_time is None:
            end_time = ""
        else:
            end_time = datetime.fromtimestamp(self.end_time).isoformat()

        alarm_str = "ALARM: {id} - {name} - SEVERITY: {severity} - START_TIME: {start_time} - END_TIME: {end_time}".format(
            id = self.id,
            name = self.alarm_type.name,
            start_time = datetime.fromtimestamp(self.start_time).isoformat(),
            end_time = end_time,
            severity = self.severity.name
        )
        return alarm_str
