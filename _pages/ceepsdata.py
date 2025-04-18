from dataclasses import dataclass
from typing import List


@dataclass
class readingQuality:
    readingQualityType: str


@dataclass
class intervalReading:
    timestamp: str
    value: float
    readingQualities: List[readingQuality]


@dataclass
class intervalBlock:
    readingType: str
    intervalReadings: List[intervalReading]


@dataclass
class ceepsdata:
    messageType: str
    usagePoint: str
    messageCreated: str
    deviceId: str
    intervalBlocks: List[intervalBlock]


def from_dict(data_class, data):
    if issubclass(data_class, list):
        return [from_dict(data_class.__args__[0], item) for item in data]
    else:
        return data_class(**data)


def object_hook(d):
    if 'messageType' in d:
        return from_dict(ceepsdata, d)
    elif 'readingType' in d:
        return from_dict(intervalBlock, d)
    elif 'timestamp' in d:
        return from_dict(intervalReading, d)
    elif 'readingQualityType' in d:
        return from_dict(readingQuality, d)
    else:
        return d
