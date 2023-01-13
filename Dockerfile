FROM python:3.9.16
MAINTAINER Gabriell Vig <gabriell.vig@sesam.io>


RUN mkdir -p /service/

WORKDIR /service

ADD ./requirements.txt /service
RUN pip install --upgrade pip; pip install -r requirements.txt

ADD service/deployer.py /service
ADD service/Vaulter.py /service
ADD service/gitter.py /service
ADD service/Node.py /service
ADD service/config_creator.py /service

EXPOSE 5000/tcp

CMD ["python", "deployer.py"]