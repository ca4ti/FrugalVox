# FrugalVox

A tiny VoIP IVR framework by hackers and for hackers.

## Features

- Small and nimble: the kernel is a single Python 3 file (~270 SLOC), and the configuration is a single YAML file
- Hackable: the kernel is well-commented and not so big, all the actions are full-featured Python scripts
- Written with plain telephony in mind, supporting both out-of-band and in-band DTMF command detection, as well as DTMF audio clip generation
- Comes with PIN-based authentication and action access control out of the box (optional but recommended)
- Comes with TTS integration out of the box, configured for eSpeakNG by default (optional)
- Container-ready
- Released into public domain

## Limitations

- Only UDP transport is supported for now (pyVoIP limitation)
- Only a single SIP server registration per instance is supported by design (if you need to receive incoming calls via multiple SIP accounts, you must spin up multiple FrugalVox instances)
- The format for top-level action commands is hardcoded (see the workflow section of this README)

## Running FrugalVox as a host application

### Dependencies 

- Python 3.8 or higher (3.10 recommended)
- pyVoIP 1.6.4, patched according to [this comment](https://github.com/tayler6000/pyVoIP/issues/107#issuecomment-1440231926) (also available as a `.whl` file in this repo)
- NumPy (mandatory, required for DTMF detection and generation)
- eSpeakNG (optional but used by the default TTS engine configuration)

For Python-side dependencies, just run `pip install -r requirements.txt` from the project directory. eSpeakNG (or other TTS engine of your choice, see the FAQ section) must be installed separately with your host OS package manager.

### Usage

Just run `python /path/to/fvx.py [your-config.yaml]`. Press Ctrl+C or otherwise terminate the process when you don't need it.

Make sure your `python` command is pointing to Python 3.8 or higher.

## Running FrugalVox in Docker

The Docker image encapsulates all the dependencies (including Python 3.10, three different TTS engines (see the FAQ section) and the patched pyVoIP package) but requires you to provide all the configuration and action scripts in a volume mounted from the host. In addition to this, the configuration file itself must be called `config.yaml` since the container is only going to be looking for this name.

### Building

From the source directory, run: `docker build -t frugalvox .` and the image called `frugalvox` will be built.

Alternatively, you can build the "slim" version of the image based on Alpine Linux, which will only contain the Pico TTS engine. For `x86_64` architecture, such an image will only weigh around 180 MiB. Do this using this command: `docker build -t frugalvox:slim -f Dockerfile.slim .`

### Running from the command line

The command to run the `frugalvox` image locally is:

```
docker run -d --rm -v /path/to/configdir:/opt/config --name frugalvox frugalvox
```

Note that the `/path/to/configdir` must be absolute. Use `$(pwd)` command to get the current working directory if your configuration directory path is relative to it.

### Running from Docker Compose

Add this to your `compose.yaml`, replacing `$PWD/example-config` with your configuration directory path:

```yaml
services:
  # ... other services here ...
  frugalvox:
    image: frugalvox:latest
    container_name: frugalvox
    restart: on-failure:10
    volumes:
      - "$PWD/example-config:/opt/config"
```

Then, on the next `docker compose up -d` run, the FrugalVox container should be up. Note that you can attach this service to any network you already created in Compose file, as long as it allows the containers to have Internet access. 

## Typical FrugalVox workflow

Without auth:

1. User calls the IVR.
2. User is prompted for the command.
3. User enters the DTMF command in the form `[action ID]*[param1]*[param2]*...#`.
4. The IVR checks the action ID. If it exists, the corresponding action script is run. If it doesn't, an error message is played back to the user.
5. User is prompted for the next command, and so on.

With auth (recommended):

1. User calls the IVR.
2. User is prompted for the PIN (internal user ID) followed by `#` key.
3. The IVR checks the PIN. If it doesn't exist in the user list, the caller is warned and the call is terminated. Otherwise, go to the next step.
4. User is prompted for the command.
5. User enters the DTMF command in the form `[action ID]*[param1]*[param2]*...#`.
6. The IVR checks the action ID. If it exists in the list of actions allowed for the user, the corresponding action script is run. If it doesn't, an error message is played back to the user.
7. User is prompted for the next command, and so on.

## Configuration

All FrugalVox configuration is done in a single YAML file that's passed to the kernel on the start. If no file is passed, FrugalVox will look for `config.yaml` file in the current working directory.

The entire config is done in four different sections of the YAML file: `sip`, `tts`, `clips` and `ivr`.

### SIP client configuration: `sip`

This section lets you configure which SIP server FrugalVox will connect to in order to start receiving incoming calls. The fields are:

- `sip.host`: your SIP provider hostname or IP address
- `sip.port`: your SIP provider port number (usually 5060)
- `sip.transport`: optional, not used for now, added here for the forward compatibility with future versions (the only supported transport is now `udp`)
- `sip.username`: your SIP account auth username (only the username itself, no domain or URI parts)
- `sip.password`: your SIP account auth password
- `sip.rtpPortLow` and `sip.rtpPortHigh`: your UDP port range for RTP communication, usually the default of 10000 and 20000 is fine

All the fields in this section, except `transport`, are currently mandatory. If unsure about `rtpPortLow` and `rtpPortHigh`, just leave the values provided in the example config.

### Text-to-speech engine settings: `tts`

This section allows you to configure your TTS engine, for FrugalVox to be able to generate audio clips from your text. The fields are:

- `tts.cmd`: the TTS synth command template, please just leave the default values there unless you want to switch to a different TTS engine other than eSpeakNG
- `tts.phrases`: a dictionary where every key is the clip name and the value is the phrase text to be rendered to that clip on the kernel start

### Static audio clips list: `clips`

This section determines which static audio clips are to be loaded into memory in addition to the synthesized voice. The clips must be in the unsigned 8-bit 8KHz PCM WAV format. The fields are:

- `clips.dir`: path to the directory (relative to the configuration file directory) containing the audio clips to load
- `clips.files`: a dictionary mapping the clip names to the `.wav` file names in the `clips.dir` directory 

Both fields are required to fill, but if you're not planning on using any static audio, just set `clips.dir` value to `'.'` and `clips.files` to `{}`.

When naming the clips, a single limitation holds: a clip must not be named `dtmf`. Because when the reference is passed to action scripts, the `clips.dtmf` object will hold the audio clips generated for all 16 DTMF digits.

### IVR configuration: `ivr`

This section lets you set up PIN-based authentication, access control and, most importantly, IVR actions themselves and the scripts that implement them.

These two fields are mandatory to fill (although can be left as empty arrays):

- `ivr.cmdpromptclips`: an array with a sequence of the clip names to play back to prompt the caller for a command
- `ivr.cmdfailclips`: an array with a sequence of the clip names to play back to alert the caller about an invalid command 

Note that any clip name in this section can refer to both static and synthesized voice audio clips, they all are populated at the same place at this point.

To turn the authentication part on and off, use the `ivr.auth` field. If and only if this field is set to `true`, the following fields are required:

- `ivr.authpromptclips`: an array with a sequence of the clip names to play back to prompt for the caller's PIN
- `ivr.authfailclips`: an array with a sequence of the clip names to play back to alert the caller about the invalid PIN before hanging up the call
- `ivr.users`: a dictionary that maps valid user IDs (PINs) to the lists (arrays) of action IDs they are authorized to run, or `'*'` string if the user is authorized to run all registered actions on this instance

Also, if the user is authenticated but not authorized to run a particular action, the same "invalid command" message sequence from `ivr.cmdfailclips` will be played back as if the command was not found. This is implemented by design as a security measure. FrugalVox itself will log a different message to the console though.

Finally, all the action mapping is done in the mandatory `ivr.actions` dictionary. The key is the action ID (without parameters, i.e. commands `22*5#` and `22*44*99#` both mean an action with ID 22, just with different parameter lists) and the value is the path to the action script file, relative to the configuration file directory.

## Action scripts

An action script is a regular Python module file referenced in the `ivr.actions` section of the configuration YAML file. A single script may implement one or more actions based on the action ID. The module must implement the `run_action` call in order to work as an action script, as follows:

```
def run_action(action_id, params, call_obj, user_id, config, clips, calls):
    ...
```

where:

- `action_id` is a string action identifier,
- `params` is an array of string parameters to the action,
- `call_obj` is an instance of `pyVoIP.VoIP.VoIPCall` class passed from the main FrugalVox call processing loop,
- `user_id` is the ID (PIN) string of the user running the action (if authentication is turned off, it's always `0000`),
- `config` is the dictionary containing the entire FrugalVox configuration object (as specified in the YAML),
- `clips` is the object containing all in-memory audio clips (in the unsigned 8-bit 8KHz PCM format) ready to be fed into the `write_audio` method of the `call_obj` (with `clips['dtmf']` being a dictionary with the pre-rendered DTMF digits),
- `calls` is a dictionary with all currently active calls on the instance (keyed with the `call_obj.call_id` value).

_Protip:_ if we use `*` as parameter separator and `#` as command terminator, why are `action_id`, `user_id` and all the action parameters still treated as strings as opposed to numbers? Because `A`, `B`, `C` and `D` still are valid DTMF digits and can be legitimately used in the actions or their parameters. Of course, if you target normal phone users, you should avoid using the "extended" digits, but there still is a possibility to do so. If you need to treat your action parameters or any IDs as numbers only, please do this yourself in your action script code.

The action script may import any other Python modules at your disposal, including the main `fvx.py` kernel to use its helper methods, and all the modules available in the configuration file directory (in case it differs from the default one). An example action script that implements three demonstration actions, `32` for echo test, `24` for caller ID readback and `22*[times]` for beep, is shipped in this repo at `example-config/actions/echobeep.py`.

### Useful methods, variables and objects exposed by the `fvx` kernel module

- `fvx.load_yaml(filename)`: a wrapper method to read a YAML file contents into a Python variable (useful if your action scripts have their own configuration files)
- `fvx.load_audio(filename)`: a method to read a WAV PCM file into the audio buffer in memory, automatically resampling it if necessary
- `fvx.logevent(msg)`: a drop-in replacement for Python's `print` function that outputs a formatted log message with the timestamp
- `fvx.audio_buf_len`: the recommended length (in bytes) of a raw audio buffer to be sent to or received from the call object the action is operating on
- `fvx.emptybuf`: a buffer of empty audio data, `fvx.audio_buf_len` bytes long
- `fvx.detect_dtmf(buf)`: a method to detect a DTMF digit in the audio data buffer (see `example-config/actions/echobeep.py` for an example of how to use it correctly)
- `fvx.tts_to_buf(text, ttsconfig)`: a method to directly render your text into an audio data buffer (pass `config['tts']` as the second parameter if you don't want to change anything in the TTS settings)
- `fvx.tts_to_file(text, filename, ttsconfig)`: same as `fvx.tts_to_buf` method but writes the result to a WAV PCM file
- `fvx.get_caller_addr(call_obj)`: a method to extract the caller's SIP address from a `VoIPCall` object (e.g. the one passed to the action)
- `fvx.get_callee_addr(call_obj)`: a method to extract the destination SIP address from a `VoIPCall` object (e.g. the one passed to the action)
- `fvx.flush_input_audio(call_obj)`: a method to ensure any excessive audio is not collected in the call audio buffer, recommended to use at the start of any actions that perform incoming audio processing
- `fvx.playbuf(buf, call_obj)`: a method to properly play back any audio buffer to the call's line
- `fvx.kernelroot`: a string that contains the FrugalVox kernel directory path
- `fvx.configroot`: a string that contains the config file directory path

## FAQ

**How was this created?**

Initially, FrugalVox was created to answer a simple question: "given a VoIP provider with a DID number I pay for monthly anyway, and a cheap privacy-centric VPS already filled with other stuff, how can I combine these two things together to control various things on the Internet from a Nokia 1280 class feature phone without the Internet access?"

**Why not Asterisk/FreeSWITCH/etc then? What's wrong with existing solutions?**

Nothing wrong at the first glance, but... Asterisk's code base was, as of November 2016, as large as 1139039 SLOC. If you don't see a problem with that, I envy your innocence. Anyway, I doubt that any of those would be able to comfortably run on that cheap VPS or on my Orange Pi with 256 MB RAM. For my goals, it would be like hunting sparrows with ballistic missiles.

FrugalVox kernel, on the other hand, is around 270 SLOC in 2023. Despite being written in Python, it is really frugal in terms of resource consumption, both while running and while writing and debugging its code. Yet, thanks to full exposure of the action scripts to the Python runtime, it can be as flexible as you want it to be. Not to mention that such a small piece of code is much easier to audit and discover and promptly mitigate any subtle errors or security vulnerabilities.

**So, is it a PBX or just a scriptable IVR system?**

I'd rather think of FrugalVox not as a turnkey solution, but as a framework. If you look at the `fvx.py` kernel alone, you'll see nothing but a scriptable IVR with user authentication and TTS integration. However, its the action scripts that give such a system its meaning. FrugalVox, along with the underlying pyVoIP library, exposes all the tooling you need to create your own interactive menus, connect and bridge calls, dial into other FrugalVox instances or other services, and so on. It's a relatively simple building block that, while being useful alone, can also be used to build VoIP systems of arbitrary complexity when properly combined with other similar blocks.

**If it's meant to be flexible, why hardcode the top level command format?**

Because such a format is the only format that allows to run actions with any amount of parameters more or less efficiently using a simple phone keypad. The goal here isn't to replace something like VoiceXML, but to give the caller ability to get to the action as quickly as possible. The `PIN#` and then `action_id*param1*param2*..#` sequence is as complex as it should be. Multi-level voice menus waste the caller's time, but you can implement them as well if you really need to.

**Does FrugalVox offer a way to fully replace DTMF commands with speech recognition?**

Currently, there is no such way, but you surely can integrate speech recognition into your action scripts. It is not an easy thing to do even in Python, and in no way frugal on computing resource consumption, but definitely is possible, see [SpeechRecognition](https://pypi.org/project/SpeechRecognition/) module reference for more information.

**Why do you need a patched pyVoIP version instead of a vanilla one?**

Because vanilla pyVoIP 1.6.4 has a bug its maintainers don't even seem to recognize as a bug. Its `RTPClient` instance creates two sockets to communicate with the same host and port. As a result, when the client is behind a NAT and tries exchanging audio data using both `read_audio` and `write_audio` methods, only the latter works correctly because it's sending datagrams out to the server. Patching `RTPClient` to only use the single socket made things work the way they should.

**I understand the importance of eSpeakNG but it sounds terrible even with MBROLA. Which else open source TTS engines can you recommend to use with FrugalVox?**

The first obvious choice would be ~~Festival~~ [Flite](https://github.com/festvox/flite). With an externally downloaded `.flitevox` voice, of course. It has a number of limitations: only English and Indic languages support, no way to adjust the volume, but the output quality is definitely a bit better. If you use the Docker image of FrugalVox, Flite is also included but you have to ship your own `.flitevox` files located somewhere inside your config directory.

The second obvious choice would be [Pico TTS](https://github.com/naggety/picotts) which is (or was) used as a built-in offline TTS engine in Android. It supports more European languages (besides two variants of English, there also are Spanish, German, French and Italian) but has a single voice per language and absolutely no parameters to configure. Also, it requires autotools to build but the process looks straightforward: `./autogen.sh && ./configure && make && sudo make install`. After this, we're interested in the `pico2wave` command. Please note that its current version has some bug retrieving the text from the command line, so we use an "echo to the pipe" approach. For your convenience, this engine also comes pre-installed in the FrugalVox Docker image.

The third (not so obvious) choice **might** be [Mimic 1](https://github.com/MycroftAI/mimic1) which is basically Flite on steroids. That's why, unlike Mimic 2 and 3, it still is pretty lightweight and suitable for our IVR purposes. It supports all the `.flitevox` voice files as well as the `.htsvoice` format. However, there is a "small" issue: currently, Mimic 1 still only supports sideloading `.flitevox` and not `.htsvoice` files by specifying the arbitrary path into the `-voice` option, all HTS voices must be either compiled in or put into the `$prefix/share/mimic/voices` (where `$prefix` usually is `/usr` or `/usr/local`) or the current working directory, and then referenced in the `-voice` option without the `.htsvoice` suffix. For me, this inconsistency kinda rules Mimic 1 out of the recommended options.

Another approach to the same problem would be to build the HTS Engine API and then a version of Flite 2.0 with its support, both sources taken from [this project page](https://hts-engine.sourceforge.net/). The build process is not so straightforward but you should be left with a `flite_hts_engine` binary with a set of command line options totally different from the usual Flite or Mimic 1. If you understand how FrugalVox is configured to use Pico TTS, then you'll have no issues configuring it for `flite_hts_engine`. The voice output quality is debatable compared to the usual `.flitevox` packages, so I wouldn't include this into my recommended list either.

Alas, that looks like it. The great triad of lightweight and FOSS TTS engines consists of eSpeakNG, Flite with variations and Pico TTS. All other engines, not counting the online APIs, are too heavy to fit into the scenario. Of course, nothing prevents you from integrating them as well if you have enough resources. In that case, I'd recommend [Mimic 3](https://github.com/MycroftAI/mimic3) but that definitely is out of this FAQ's scope.

Note that for both Flite and Mimic 1 the output voice must support a sample rate that is divisible by 8000 Hz in order to sound correctly. Since version 0.0.2, FrugalVox uses an internal resampler that has this limitation. A way to mitigate this in the future versions is being investigated.

To recap, here are all the example TTS configurations for all the reviewed engines:

eSpeakNG + MBROLA:

```yaml
tts:
  cmd: 'espeak -v us-mbrola-2 -a 70 -p 60 -s 130 -w %s "%s"' # parameter order: filename, text
  ...
```

Flite/Mimic 1:

```yaml
tts:
  cmd: 'flite -voice tts/cmu_us_rms.flitevox --setf int_f0_target_mean=100 --setf duration_stretch=1 -o %s -t "%s"' # parameter order: filename, text
  ...
```

Pico TTS:

```yaml
tts:
  cmd: OUTF=%s sh -c 'echo "%s" | pico2wave -l en-US -w $OUTF' # parameter order: filename, text
  ...
```

## Version history

- 0.0.2 (2023-02-28, current): fully got rid of SoX dependency, simplified TTS configuration
- 0.0.1 (2023-02-26): initial release

## Credits

Created by Luxferre in 2023.

Made in Ukraine.
