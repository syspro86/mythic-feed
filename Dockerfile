FROM python:3.10.1

WORKDIR /app
COPY main.py /app/
COPY startup.sh /app/
RUN chmod +x /app/startup.sh

ENTRYPOINT ["/bin/bash", "/app/startup.sh"]
