# syntax=docker/dockerfile:1
# Built from the repository root (docker-compose.yml: context ..), so the format checker can be copied in.
FROM python:3.12-slim
WORKDIR /app
COPY review/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY review/VERSION review/app.py /app/
COPY review/static /app/static
COPY schema/check_submission.py schema/submission.schema.json /app/schema/
USER nobody
CMD ["python", "app.py"]
