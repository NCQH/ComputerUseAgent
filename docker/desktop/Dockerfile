# docker/desktop/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc fluxbox scrot python3-tk python3-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyautogui pillow

WORKDIR /app
COPY agent.py /app/agent.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV DISPLAY=:99
EXPOSE 8000 5900

CMD ["/app/entrypoint.sh"]
