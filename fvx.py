#!/usr/bin/env python3

# FrugalVox: experimental, straightforward, no-nonsense IVR framework on top of pyVoIP (patched) and TTS engines
# Created by Luxferre in 2023, released into public domain
# Deps: PyYAML, NumPy, espeak-ng/flite/libttspico, patched pyVoIP (see https://github.com/tayler6000/pyVoIP/issues/107#issuecomment-1440231926)
# All configuration is in config.yaml

import sys
import os
import signal
import tempfile
import yaml
import wave, audioop
import time
from datetime import datetime # for logging
import traceback # for logging
import socket # for local IP detection
import numpy as np # for in-band DTMF detection and generation
import importlib.util # for action modules import
from pyVoIP.VoIP import VoIPPhone, InvalidStateError, CallState

# global parameters
progname = 'FrugalVox v0.0.2'
config = {} # placeholder for config object
configfile = './config.yaml' # default config yaml path (relative to the workdir)
if len(sys.argv) > 1:
    configfile = sys.argv[1]
configfile = os.path.realpath(configfile)
kernelroot = os.path.realpath(os.path.dirname(__file__)) # absolute path to the kernel directory
configroot = os.path.dirname(configfile)
sys.path.append(kernelroot) # make the kernel module findable
if configroot != kernelroot:
    sys.path.append(configroot) # make the modules in configuration directory findable
audio_buf_len = 160 # analyze this amount of raw audio data bytes
emptybuf = b'\x80' * audio_buf_len
DTMF_TABLE = {
    '1': [1209, 697],
    '2': [1336, 697],
    '3': [1477, 697],
    'A': [1633, 697],
    '4': [1209, 770],
    '5': [1336, 770],
    '6': [1477, 770],
    'B': [1633, 770],
    '7': [1209, 852],
    '8': [1336, 852],
    '9': [1477, 852],
    'C': [1633, 852],
    '*': [1209, 941],
    '0': [1336, 941],
    '#': [1477, 941],
    'D': [1633, 941]
}
ivrconfig = None # placeholder for IVR auth config
calls = {} # placeholder for all realtime call instances

# helper methods

def logevent(msg):
    dts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print('[%s] %s' % (dts, msg))

def load_audio(fname): # load audio data from a WAV PCM file, resampling it if necessary
    f = wave.open(fname, 'rb')
    outrate = 8000
    aparams = f.getparams()
    frames = aparams.nframes
    channels = aparams.nchannels
    inrate = aparams.framerate
    swidth = aparams.sampwidth
    data = f.readframes(frames)
    f.close()
    if channels > 1: # convert to mono
        data = audioop.tomono(data, swidth, 0.5, 0.5)
    if inrate > outrate or swidth > 1: # convert the sample rate and bit width at the same time
        rfactor = int(inrate / outrate) * swidth # only multiples of 8 KHz are supported
        out = bytearray()
        blen = len(data)
        bwidth = swidth << 3 # incoming bit width
        bfactor = 1 << (bwidth - 8) # factor to divide the biased sample value by to get a single byte
        for i in range(0, blen, swidth): # only add every `rfactor`th frame
            if (i % rfactor) == 0:
                if swidth == 1:
                    bval = data[i]
                else:
                    bval = int.from_bytes(bytes(data[i:i+swidth]), byteorder='little', signed=True)
                if bfactor > 1: # perform bit reduction if necessary
                    bval = int(round(bval / bfactor)) + 128
                if bval > 255: # handle clipping
                    bval = 255
                out.append(bval)
        data = bytes(out)
    return data

def load_yaml(fname): # load an object from a YAML file
    yf = open(fname, 'r')
    yc = yf.read()
    yf.close()
    return yaml.safe_load(yc)

def tts_to_file(text, fname, conf): # render the text to a file
    ecmd = conf['cmd'] % (fname, text)
    os.system(ecmd) # render to the temporary file

def tts_to_buf(text, conf): # render the text directly to a buffer
    fh, fname = tempfile.mkstemp('.wav', 'fvx-')
    os.close(fh)
    tts_to_file(text, fname, conf)
    buf = load_audio(fname)
    os.remove(fname)
    return buf

def gen_dtmf(f1, f2): # directly render two sine frequencies to a buffer (0.2 s duration and 8KHz sample rate hardcoded)
    nbuf = np.arange(0, 0.2, 1 / 8000) # init target signal buffer and then sum the sine signals
    return (127 + 61.44 * (np.sin(2 * np.pi * f1 * nbuf) + np.sin(2 * np.pi * f2 * nbuf))).astype(np.ubyte).tobytes()

def get_caller_addr(call): # extract caller's SIP address from the call request headers
    return call.request.headers['From']['address']

def get_callee_addr(call): # extract destination SIP address from the call request headers
    return call.request.headers['To']['address']

def flush_input_audio(call): # clear the call's RTP input buffer
    abuf = None
    for i in range(625): # because 625 * 160 = 100000 (pyVoIP's internal buffer size)
        abuf = call.read_audio(audio_buf_len, False)

def playbuf(buf, call): # properly play audio buffer on the call
    blen = len(buf) / 8000
    call.write_audio(buf)
    time.sleep(blen)

def playclips(clipset, call): # properly play clips on the call
    for clipname in clipset:
        playbuf(clips[clipname], call)

def hangup(call): # call hangup wrapper
    global calls
    if call.call_id in calls:
        del calls[call.call_id]
    try:
        call.hangup()
    except InvalidStateError:
        pass
    logevent('Call with %s terminated' % get_caller_addr(call))

# in-band DTMF detector

def isNumberInArray(array, number):
    offset = 5
    for i in range(number - offset, number + offset):
        if i in array:
            return True
    return False

def detect_dtmf(buf): # Detect a DTMF digit in the audio buffer using FFT
    data = np.frombuffer(buf, dtype=np.uint8)
    ftdata = np.fft.fft(data)
    ftlen = len(ftdata)
    for i in range(ftlen):
        ftdata[i] = int(np.absolute(ftdata[i]))
    lb = 20 * np.average(ftdata) # lower bound for filtering
    freqs = []
    for i in range(ftlen):
        if ftdata[i] > lb:
            freqs.append(i)
    for d, fpair in DTMF_TABLE.items(): # Detect and return the digit
        if isNumberInArray(freqs, fpair[0]) and isNumberInArray(freqs, fpair[1]):
            return d

# IVR command handler (for authenticated and authorized action runs)

def command_handler(act, modulefile, call, userid):
    global clips
    global calls
    global config
    actid = act[0]
    params = act[1:]
    logevent('Running action %s from the module %s with params (%s)' % (actid, modulefile, ', '.join(params)))
    (modname, ext) = os.path.splitext(os.path.basename(modulefile))
    spec = importlib.util.spec_from_file_location(modname, modulefile)
    actionmodule = importlib.util.module_from_spec(spec)
    sys.modules[modname] = actionmodule
    spec.loader.exec_module(actionmodule)
    actionmodule.run_action(actid, params, call, userid, config, clips, calls)

# main call handler

def main_call_handler(call): # call object as the argument
    global clips
    global ivrconfig
    global calls
    calls[call.call_id] = call # register the call in the list
    logevent('New incoming call from %s' % get_caller_addr(call))
    try:
        call.answer()
        authdone = True
        userid = '0000' # default for the unauthorized
        actionsallowed = '*'
        if ivrconfig['auth'] == True: # drop all permissions and prompt for the PIN
            authdone = False
            actionsallowed = {}
            playclips(ivrconfig['authpromptclips'], call)
        else: # prompt for the first command
            playclips(ivrconfig['cmdpromptclips'], call)
        cmdbuf = '' # command buffer
        cache_digit = None # in-band digit cache
        while call.state == CallState.ANSWERED: # main event loop
            audiobuf = call.read_audio(audio_buf_len, False) # nonblocking audio buffer read
            digit = call.get_dtmf() # get a single out-of-band DTMF digit
            if digit == '' and audiobuf != emptybuf: # no out-of-band digit, try in-band detection
                ib_digit = detect_dtmf(audiobuf)
                if ib_digit != cache_digit:
                    if ib_digit == None: # digit transmission ended
                        digit = cache_digit # save the digit
                        cache_digit = None  # reset the cache
                    else: # digit transmission started
                        cache_digit = ib_digit
            if digit == '#': # end of the command
                if authdone: # we're authenticated, let's authorize the action
                    actionparts = cmdbuf.split('*')
                    actionroot = actionparts[0]
                    letthrough = False
                    if actionsallowed == '*' or (actionroot in actionsallowed):
                        letthrough = True
                    if letthrough: # authorized
                        if actionroot in ivrconfig['actions']: # command exists
                            actionmod = os.path.realpath(os.path.join(configroot, ivrconfig['actions'][actionroot])) # resolve the action module file
                            command_handler(actionparts, actionmod, call, userid) # pass control to the command handler along with the call instance
                        else: # command doesn't exist, notify the caller
                            playclips(ivrconfig['cmdfailclips'], call)
                            logevent('Attempt to execute a non-existing action %s with the user ID %s' % (cmdbuf, userid))
                    else: # notify the caller that the command doesn't exist and log the event
                        playclips(ivrconfig['cmdfailclips'], call)
                        logevent('Attempt to execute an unauthorized action %s with the user ID %s' % (cmdbuf, userid))
                    playclips(ivrconfig['cmdpromptclips'], call) # prompt for the next command
                    flush_input_audio(call)
                else: # we expect the first command to be our user PIN
                    if cmdbuf in ivrconfig['users']: # PIN found, confirm auth and prompt for the command
                        authdone = True
                        userid = cmdbuf
                        actionsallowed = ivrconfig['users'][userid]
                        playclips(ivrconfig['cmdpromptclips'], call) # prompt for the next command
                    else: # PIN not found, alert the caller, log the failed entry and hang up
                        playclips(ivrconfig['authfailclips'], call)
                        logevent('Attempt to enter with invalid PIN %s' % cmdbuf)
                        hangup(call)
                cmdbuf = '' # clear command buffer
            elif digit != '': # append the digit to the command buffer
                cmdbuf += digit
        hangup(call)
    except InvalidStateError: # usually this means the call was hung up mid-action
        hangup(call)
    except SystemExit: # in case the service has been stopped or restarted
        hangup(call)
    except Exception as e:
        print('Unknown error: ', sys.exc_info())
        traceback.print_exc()
        hangup(call)

# signal handler for graceful process termination

def sighandler(signum, frame):
    global phone
    logevent('Stopping the SIP client...')
    phone.stop()
    logevent('SIP client stopped, bye!')

# entry point

if __name__ == '__main__':
    logevent('Starting %s' % progname)
    config = load_yaml(configfile)
    ivrconfig = config['ivr']
    logevent('Configuration loaded from %s' % configfile)
    clipDir = os.path.realpath(os.path.join(configroot, config['clips']['dir']))
    logevent('Loading static audio clips')
    clips = config['clips']['files']
    for k, fname in clips.items():
        clips[k] = load_audio(os.path.join(clipDir, fname))
    logevent('Rendering TTS phrases')
    for pname, phrase in config['tts']['phrases'].items():
        clips[pname] = tts_to_buf(phrase, config['tts'])
    logevent('Rendering DTMF clips')
    clips['dtmf'] = {}
    for digit, fpair in DTMF_TABLE.items():
        clips['dtmf'][digit] = gen_dtmf(fpair[0], fpair[1])
    logevent('All clips loaded to memory buffers from %s' % clipDir)
    logevent('Initializing SIP phone part')
    sip = config['sip']
    sipport = int(sip['port'])
    localname = socket.gethostname()
    localip = (([ip for ip in socket.gethostbyname_ex(localname)[2] if not ip.startswith('127.')] or [[(s.connect((sip['host'], sipport)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + [None])[0]
    if localip == None:
        localip = socket.gethostbyname(localname)
    logevent('Local IP detected: %s' % localip)
    phone = VoIPPhone(sip['host'], sipport, sip['username'], sip['password'], myIP=localip, rtpPortLow=int(sip['rtpPortLow']), rtpPortHigh=int(sip['rtpPortHigh']), callCallback=main_call_handler)
    # register the SIGINT and SIGTERM handlers to gracefully stop the phone instance
    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)
    phone.start()
    logevent('SIP client started')
