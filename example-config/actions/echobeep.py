# An example action script for FrugalVox
# Implements three actions: echo test, caller address readback and parameterized beep

import os, sys # example of using commonly available Python modules
from pyVoIP.VoIP import CallState # example of using an installation-specific module
from fvx import tts_to_buf, detect_dtmf, audio_buf_len, emptybuf, get_caller_addr, flush_input_audio, playbuf # example of using the FrugalVox kernel module (fvx)

def run_action(action_id, params, call_obj, user_id, config, clips, calls):
    if action_id == '32': # echo test: just enter 32#
        playbuf(tts_to_buf('Entering the echo test, press pound to return', config['tts']), call_obj)
        flush_input_audio(call_obj)
        cache_digit = None # in-band digit cache
        while call_obj.state == CallState.ANSWERED: # main event loop
            audiobuf = call_obj.read_audio(audio_buf_len, True) # blocking audio buffer read
            call_obj.write_audio(audiobuf) # echo the audio
            digit = call_obj.get_dtmf() # get a single out-of-band DTMF digit
            if digit == '' and audiobuf != emptybuf: # no out-of-band digit, try in-band detection
                ib_digit = detect_dtmf(audiobuf)
                if ib_digit != cache_digit:
                    if ib_digit == None: # digit transmission ended
                        digit = cache_digit # save the digit
                        cache_digit = None  # reset the cache
                    else: # digit transmission started
                        cache_digit = ib_digit
            if digit == '#':
                playbuf(tts_to_buf('Echo test ended', config['tts']), call_obj)
                return
    elif action_id == '24': # Caller ID readback: enter 24#
        playbuf(tts_to_buf('Your caller ID is %s' % get_caller_addr(call_obj), config['tts']), call_obj) # demonstration of the on-the-fly TTS
    else: # beep command: 22*3# tells to beep 3 times
        times = 1 # how many times we should beep
        if len(params) > 0:
            times = int(params[0])
        if times > 10: # limit beeps to 10
            times = 10
        # send the beeps
        playbuf((clips['beep']+(emptybuf*10)) * times, call_obj)
        return
