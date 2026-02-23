FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY contracts ./contracts
COPY scripts ./scripts
COPY .semgrep.yml ./.semgrep.yml
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "app.cli", "--hello", "docker"]
