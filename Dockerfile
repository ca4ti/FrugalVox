FROM python:3.10-slim-bullseye
USER root
WORKDIR /usr/src/app
RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list
RUN apt-get update -y && apt-get install -y libttspico-utils espeak-ng espeak-ng-data espeak-ng-espeak flite sox
COPY requirements.txt ./
COPY pyVoIP-1.6.4.patched-py3-none-any.whl ./
RUN pip install --no-cache-dir -r requirements.txt
COPY fvx.py ./
VOLUME /opt/config
WORKDIR /opt/config
ENTRYPOINT ["python", "-u", "/usr/src/app/fvx.py", "/opt/config/config.yaml"]
