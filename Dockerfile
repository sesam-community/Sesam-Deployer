FROM python:3.6
MAINTAINER Gabriell Vig <gabriell.vig@sesam.io>


RUN mkdir -p /service/

ADD ./requirements.txt /service
ADD service/deployer.py /service
ADD service/Vaulter.py /service
ADD ./sesam-master-node-config/ /service/sesam-master-node-config

WORKDIR /service

RUN pip install -r requirements.txt

EXPOSE 5000/tcp

CMD ["python", "deployer.py"]
