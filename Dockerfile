FROM python:3.6
MAINTAINER Gabriell Vig <gabriell.vig@sesam.io>


RUN apt-get update \
    && apt-get -y install git \
    && mkdir -p /service/

ADD ./requirements.txt /service
ADD service/deployer.py /service
ADD ./service/Vaulter.py /service

WORKDIR /service
RUN mkdir master

RUN pip install -r requirements.txt

EXPOSE 5000/tcp

CMD ["python", "deployer.py"]
