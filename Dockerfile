FROM python:3.10.1

WORKDIR /app

COPY requirements.txt /app/
# RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY main.py /app/
COPY startup.sh /app/
RUN chmod +x /app/startup.sh

ENTRYPOINT ["/bin/bash", "/app/startup.sh"]
