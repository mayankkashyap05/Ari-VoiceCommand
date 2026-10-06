import core.VoiceCommand as _core_voicecommand
from core.VoiceCommand import *


def __getattr__(name):
    return getattr(_core_voicecommand, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_voicecommand)))
