FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY . /app
WORKDIR /app/backend
ENV AQUAFLOW_DB=/app/data/aquaflow.db
RUN mkdir -p /app/data
EXPOSE 8799
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8799"]
