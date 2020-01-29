FROM python:3.6
MAINTAINER Gabriell Vig <gabriell.vig@sesam.io>


RUN mkdir -p /service/

ADD ./requirements.txt /service
ADD service/deployer.py /service
ADD service/Vaulter.py /service
ADD service/gitter.py /service
ADD service/Node.py /service
ADD service/config_creator.py /service
ADD ./$NODE_FOLDER /service/$NODE_FOLDER

WORKDIR /service

RUN pip install -r requirements.txt

EXPOSE 5000/tcp

CMD ["python", "deployer.py"]