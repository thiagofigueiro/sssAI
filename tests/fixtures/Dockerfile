FROM alpine:latest

RUN apk add curl py-pip py3-setuptools python3-dev libffi-dev openssl-dev \
    bash gcc libc-dev rust cargo make \
    tiff-dev jpeg-dev openjpeg-dev zlib-dev freetype-dev lcms2-dev \
    libwebp-dev tcl-dev tk-dev harfbuzz-dev fribidi-dev libimagequant-dev \
    libxcb-dev libpng-dev

COPY *requirements.txt /
RUN pip3 install -r dev-requirements.txt -r /requirements.txt
